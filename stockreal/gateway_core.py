"""Offline-tested gateway mechanics. No HTTP adapter or automatic runner is installed."""
import asyncio
import copy
import hashlib
import json
import random
import time
import uuid
from collections import OrderedDict,deque
from dataclasses import dataclass
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from stockreal.stage0 import HOSTS,SECRET_NAMES,SINGLE

class Clock:
    def monotonic(self):return time.monotonic()
    def now(self):return datetime.now(timezone.utc)
    async def sleep(self,seconds):await asyncio.sleep(seconds)

@dataclass(frozen=True)
class RequestSpec:
    source_id:int
    host:str
    credential_profile:str
    contract_version:str
    params:tuple
    session_id:str

@dataclass(frozen=True)
class Policy:
    ttl:float=10
    min_interval:float=10
    max_source_age:float=30
    timeout:float=20
    retries:int=2

@dataclass
class Reply:
    http_status:int
    data:object=None
    business_ok:bool=True
    source_time:datetime|None=None
    retry_after:str|None=None
    quality_flags:tuple=()

class TokenBucket:
    def __init__(self,clock,rate=4,burst=2):
        self.clock=clock;self.rate=rate;self.capacity=burst;self.tokens=float(burst);self.updated=clock.monotonic();self.lock=asyncio.Lock()
    async def take(self):
        async with self.lock:
            while True:
                now=self.clock.monotonic();self.tokens=min(self.capacity,self.tokens+max(0,now-self.updated)*self.rate);self.updated=now
                if self.tokens>=1:self.tokens-=1;return
                await self.clock.sleep((1-self.tokens)/self.rate)

class EndpointHealth:
    def __init__(self):self.samples=deque();self.failures=0;self.successes=0;self.degraded=False
    def observe(self,now,ok):
        self.samples.append((now,ok))
        while self.samples and self.samples[0][0]<now-300:self.samples.popleft()
        if ok:
            self.failures=0;self.successes+=1
            if self.successes>=5:self.degraded=False
        else:
            self.successes=0;self.failures+=1
            if self.failures>=3 or sum(not x[1] for x in self.samples)/len(self.samples)>.05:self.degraded=True

def retry_delay(value,now,fallback):
    if value:
        try:return max(0,float(value))
        except ValueError:
            try:
                parsed=parsedate_to_datetime(value)
                if parsed.tzinfo is not None:return max(0,(parsed-now).total_seconds())
            except (ValueError,TypeError,OverflowError):pass
    return fallback

class GatewayCore:
    def __init__(self,transport,budget,*,clock=None,jitter=None):
        self.transport=transport;self.budget=budget;self.clock=clock or Clock();self.jitter=jitter or (lambda:random.uniform(0,.25))
        self.cache=OrderedDict();self.flights={};self.hosts={};self.endpoints={};self.buckets={};self.health={};self.last_attempt=OrderedDict();self.closed=False
    def key(self,spec,policy):
        if spec.host not in HOSTS or not spec.session_id or type(spec.source_id) is not int:raise ValueError('invalid request identity')
        if not (0<=policy.retries<=2 and policy.ttl>=0 and policy.min_interval>=0 and policy.timeout>0 and policy.max_source_age>=0):raise ValueError('invalid policy')
        pairs=list(spec.params)
        if any(k.lower() in SECRET_NAMES|{'apiv'} for k,v in pairs):raise ValueError('credentials must not enter request keys')
        if len({k for k,v in pairs})!=len(pairs):raise ValueError('duplicate parameters')
        if spec.source_id in SINGLE:
            import re
            symbols=[v for k,v in pairs if k=='StockID']
            if len(symbols)!=1 or not re.fullmatch(r'[0-9]{6}',symbols[0]):raise ValueError('single stock required')
            if any(k.lower().startswith('stockid') and k!='StockID' for k,v in pairs):raise ValueError('stock alias forbidden')
        # A caller cannot share a result across account/contract/session/policy changes.
        raw=(spec.source_id,spec.host,spec.credential_profile,spec.contract_version,sorted(pairs),spec.session_id,policy.__dict__)
        return hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()
    def _view(self,entry,policy,*,cached=False,error=None):
        flags=set(entry['quality_flags'])|{'FIELD_CONTRACT_UNVERIFIED'}
        source=entry['source_time']
        if source is None:flags.add('NO_SOURCE_TIME')
        elif source.tzinfo is None:flags.add('INVALID_SOURCE_TIME')
        else:
            age=(self.clock.now()-source).total_seconds()
            if age<0:flags.add('FUTURE_SOURCE_TIME')
            if age>policy.max_source_age:flags.add('STALE')
        if self.clock.monotonic()-entry['received_tick']>=policy.ttl or error:flags.add('STALE')
        if error:flags.add(error)
        return {'data':copy.deepcopy(entry['data']),'source_time':source.isoformat() if source else None,
                'cached':cached,'quality_flags':sorted(flags),'production_eligible':False,'request_id':entry['request_id']}
    async def fetch(self,spec,policy,*,priority='NORMAL'):
        if self.closed:raise RuntimeError('gateway closed')
        if priority not in ('NORMAL','MARKET_RISK','HOLDING_RISK','REGULATORY','PEAK'):raise ValueError('invalid priority')
        key=self.key(spec,policy)
        entry=self.cache.get(key)
        if entry and self.clock.monotonic()-entry['received_tick']<policy.ttl:
            self.cache.move_to_end(key);return self._view(entry,policy,cached=True)
        if key not in self.flights:
            if len(self.flights)>=256:return {'data':None,'quality_flags':['QUEUE_FULL'],'production_eligible':False}
            task=asyncio.create_task(self._fetch(spec,policy,key,priority))
            self.flights[key]=task
            def done(task):
                if self.flights.get(key) is task:self.flights.pop(key,None)
                if not task.cancelled():task.exception()
            task.add_done_callback(done)
        # One cancelled page/consumer must not cancel the shared request.
        return copy.deepcopy(await asyncio.shield(self.flights[key]))
    async def _fetch(self,spec,policy,key,priority):
        host=self.hosts.setdefault(spec.host,asyncio.Semaphore(2))
        endpoint=(spec.host,spec.source_id)
        sem=self.endpoints.setdefault(endpoint,asyncio.Semaphore(2))
        bucket=self.buckets.setdefault(endpoint,TokenBucket(self.clock))
        health=self.health.setdefault(endpoint,EndpointHealth())
        reason='DATA_UNAVAILABLE'
        await self.clock.sleep(self.jitter())
        for attempt in range(policy.retries+1):
            multiplier=2 if health.degraded else 1
            delay=max(0,self.last_attempt.get(key,-1e30)+policy.min_interval*multiplier-self.clock.monotonic())
            if delay:await self.clock.sleep(delay)
            await bucket.take()
            async with sem,host:
                day=self.clock.now().astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()
                claim=await self.budget.claim_budget(day,allow_reserve=priority!='NORMAL' or attempt>0)
                if not claim['allowed']:reason=claim['reason'];break
                self.last_attempt[key]=self.clock.monotonic();self.last_attempt.move_to_end(key)
                if len(self.last_attempt)>4096:self.last_attempt.popitem(last=False)
                request_id=str(uuid.uuid4())
                try:
                    reply=await asyncio.wait_for(self.transport(spec,request_id),policy.timeout)
                    if not isinstance(reply,Reply):raise TypeError('invalid adapter response')
                except TimeoutError:
                    reply=None;reason='TIMEOUT';can_retry=True
                except Exception:
                    reply=None;reason='TRANSPORT_ERROR';can_retry=False
            ok=reply is not None and reply.http_status==200 and reply.business_ok
            health.observe(self.clock.monotonic(),ok)
            if ok:
                entry={'data':copy.deepcopy(reply.data),'source_time':reply.source_time,'quality_flags':reply.quality_flags,
                       'received_tick':self.clock.monotonic(),'request_id':request_id}
                self.cache[key]=entry;self.cache.move_to_end(key)
                if len(self.cache)>512:self.cache.popitem(last=False)
                return self._view(entry,policy)
            if reply is not None:
                reason='UPSTREAM_BUSINESS_ERROR' if reply.http_status==200 else 'HTTP_'+str(reply.http_status)
                can_retry=reply.http_status==429 or 500<=reply.http_status<600
            if not can_retry or attempt==policy.retries:break
            delay=retry_delay(reply.retry_after if reply else None,self.clock.now(),2**attempt)
            # Do not retry sooner than Retry-After when the server asks for a long pause.
            if delay>60:reason='RETRY_DEFERRED';break
            await self.clock.sleep(delay+self.jitter())
        if key in self.cache:return self._view(self.cache[key],policy,cached=True,error=reason)
        return {'data':None,'quality_flags':[reason,'FIELD_CONTRACT_UNVERIFIED'],'production_eligible':False}
    async def close(self):
        self.closed=True
        await asyncio.gather(*list(self.flights.values()),return_exceptions=True)
