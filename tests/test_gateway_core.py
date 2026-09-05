import asyncio
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from stockreal.gateway_core import GatewayCore,RequestSpec,Policy,Reply,EndpointHealth,retry_delay

class FakeClock:
    def __init__(self):self.t=0;self.delays=[]
    def monotonic(self):return self.t
    def now(self):return datetime(2026,9,5,1,tzinfo=timezone.utc)+timedelta(seconds=self.t)
    async def sleep(self,t):self.delays.append(t);self.t+=t;await asyncio.sleep(0)

class Budget:
    def __init__(self):self.calls=[];self.allowed=True
    async def claim_budget(self,day,allow_reserve=False):
        self.calls.append((day,allow_reserve));return {'allowed':self.allowed,'reason':'HARD_CAP'}

class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clock=FakeClock();self.budget=Budget();self.calls=0
        self.spec=RequestSpec(9,'apphq.longhuvip.com','profile-9','candidate-1',(('StockID','000001'),),'2026-09-05:AM')
        self.policy=Policy(ttl=10,min_interval=0)
        async def transport(spec,request_id):self.calls+=1;return Reply(200,{'price':10},source_time=self.clock.now())
        self.gw=GatewayCore(transport,self.budget,clock=self.clock,jitter=lambda:0)
    async def asyncTearDown(self):await self.gw.close()
    async def test_singleflight_cache_and_independent_result(self):
        results=await asyncio.gather(*(self.gw.fetch(self.spec,self.policy) for _ in range(30)))
        self.assertEqual(self.calls,1);self.assertEqual(len(self.budget.calls),1)
        results[0]['data']['price']=999
        result=await self.gw.fetch(self.spec,self.policy)
        self.assertEqual(result['data']['price'],10);self.assertTrue(result['cached'])
    async def test_expiry_makes_one_new_request(self):
        await self.gw.fetch(self.spec,self.policy);self.clock.t+=11
        await self.gw.fetch(self.spec,self.policy);self.assertEqual(self.calls,2)
    async def test_identity_isolates_session_account_and_contract(self):
        for spec in (self.spec,replace(self.spec,session_id='PM'),replace(self.spec,credential_profile='other'),replace(self.spec,contract_version='v2')):
            await self.gw.fetch(spec,self.policy)
        self.assertEqual(self.calls,4)
    async def test_cancelled_consumer_does_not_cancel_shared_fetch(self):
        started=asyncio.Event();release=asyncio.Event()
        async def transport(spec,rid):started.set();await release.wait();return Reply(200,1)
        self.gw.transport=transport
        a=asyncio.create_task(self.gw.fetch(self.spec,self.policy));await started.wait()
        b=asyncio.create_task(self.gw.fetch(self.spec,self.policy));await asyncio.sleep(0)
        a.cancel()
        with self.assertRaises(asyncio.CancelledError):await a
        release.set();self.assertEqual((await b)['data'],1);self.assertEqual(len(self.budget.calls),1)
    async def test_401_and_403_are_not_retried(self):
        for code in (401,403):
            self.budget.calls=[]
            async def transport(spec,rid):return Reply(code)
            self.gw.transport=transport
            result=await self.gw.fetch(self.spec,self.policy)
            self.assertIn('HTTP_'+str(code),result['quality_flags']);self.assertEqual(len(self.budget.calls),1)
    async def test_429_then_success_counts_retry_and_obeys_header(self):
        replies=[Reply(429,retry_after='7'),Reply(200,1)]
        async def transport(spec,rid):return replies.pop(0)
        self.gw.transport=transport
        self.assertEqual((await self.gw.fetch(self.spec,self.policy))['data'],1)
        self.assertIn(7,self.clock.delays);self.assertEqual([c[1] for c in self.budget.calls],[False,True])
    async def test_long_retry_after_defers_without_retry(self):
        async def transport(spec,rid):return Reply(429,retry_after='120')
        self.gw.transport=transport
        self.assertIn('RETRY_DEFERRED',(await self.gw.fetch(self.spec,self.policy))['quality_flags'])
        self.assertEqual(len(self.budget.calls),1)
    async def test_5xx_is_bounded(self):
        async def transport(spec,rid):return Reply(503)
        self.gw.transport=transport
        self.assertIn('HTTP_503',(await self.gw.fetch(self.spec,self.policy))['quality_flags'])
        self.assertEqual(len(self.budget.calls),3)
    async def test_timeout_is_bounded(self):
        async def transport(spec,rid):raise TimeoutError('do not expose URL')
        self.gw.transport=transport
        result=await self.gw.fetch(self.spec,self.policy)
        self.assertIn('TIMEOUT',result['quality_flags']);self.assertEqual(len(self.budget.calls),3)
        self.assertNotIn('URL',str(result))
    async def test_business_error_keeps_old_cache_stale(self):
        await self.gw.fetch(self.spec,self.policy);self.clock.t+=11
        async def transport(spec,rid):return Reply(200,{'wrong':1},business_ok=False)
        self.gw.transport=transport
        result=await self.gw.fetch(self.spec,self.policy)
        self.assertEqual(result['data'],{'price':10});self.assertIn('STALE',result['quality_flags']);self.assertFalse(result['production_eligible'])
    async def test_budget_denial_does_not_call_transport(self):
        self.budget.allowed=False
        result=await self.gw.fetch(self.spec,self.policy)
        self.assertIn('HARD_CAP',result['quality_flags']);self.assertEqual(self.calls,0)
    async def test_source_timestamp_is_not_received_timestamp(self):
        async def transport(spec,rid):return Reply(200,1)
        self.gw.transport=transport
        result=await self.gw.fetch(self.spec,self.policy)
        self.assertIsNone(result['source_time']);self.assertIn('NO_SOURCE_TIME',result['quality_flags'])
    async def test_old_source_stale_even_on_cache_hit(self):
        async def transport(spec,rid):return Reply(200,1,source_time=self.clock.now()-timedelta(seconds=100))
        self.gw.transport=transport
        result=await self.gw.fetch(self.spec,self.policy)
        self.assertIn('STALE',result['quality_flags'])
    async def test_per_key_minimum_interval(self):
        p=Policy(ttl=0,min_interval=10)
        await self.gw.fetch(self.spec,p);await self.gw.fetch(self.spec,p)
        self.assertGreaterEqual(self.clock.t,10)
    async def test_host_concurrency_never_exceeds_two(self):
        active=0;peak=0
        async def transport(spec,rid):
            nonlocal active,peak
            active+=1;peak=max(peak,active)
            await asyncio.sleep(.005);active-=1;return Reply(200,1)
        self.gw.transport=transport
        await asyncio.gather(*(self.gw.fetch(replace(self.spec,params=(('StockID',f'{i:06d}'),)),self.policy) for i in range(8)))
        self.assertLessEqual(peak,2)
    async def test_credentials_rejected_from_request_metadata(self):
        with self.assertRaises(ValueError):await self.gw.fetch(replace(self.spec,params=(('Token','secret'),)),self.policy)

class HealthTests(unittest.TestCase):
    def test_error_rate_and_five_success_recovery(self):
        h=EndpointHealth();h.observe(1,False);self.assertTrue(h.degraded)
        for t in range(2,6):h.observe(t,True)
        self.assertTrue(h.degraded);h.observe(6,True);self.assertFalse(h.degraded)
    def test_retry_after_http_date(self):
        now=datetime(2026,9,5,tzinfo=timezone.utc)
        self.assertEqual(retry_delay('Sat, 05 Sep 2026 00:00:10 GMT',now,1),10)

if __name__=='__main__':unittest.main()
