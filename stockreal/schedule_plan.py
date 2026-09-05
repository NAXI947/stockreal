"""Pure R3.5 task proposals. No scheduler loop, transport, or automatic execution."""
import json
import re
from datetime import datetime,time
from pathlib import Path
from zoneinfo import ZoneInfo
from stockreal.runtime_gate import status

TZ=ZoneInfo('Asia/Shanghai')

def propose(now,holdings,*,calendar_state):
    if now.tzinfo is None:raise ValueError('aware timestamp required')
    now=now.astimezone(TZ);day=now.date().isoformat();t=now.time()
    if len(holdings)>20 or len(set(holdings))!=len(holdings):raise ValueError('up to 20 distinct holdings required')
    if any(not re.fullmatch(r'[0-9]{6}\.(SH|SZ|BJ)',s) for s in holdings):raise ValueError('canonical A-share symbols required')
    result={'trade_date':day,'phase':'DISABLED','tasks':[],'window_features_ready':False,'opening_profile':False,
            'reset_token':None,'candidate_expire_time':day+'T14:56:30+08:00','automatic_execution':False,
            'production_eligible':False,'calendar_status':calendar_state}
    if calendar_state!='OPEN_DAY':return result
    def add(doc,interval,*,symbols=None,purpose='OBSERVATION',priority='NORMAL',once=False):
        for symbol in symbols if symbols is not None else [None]:
            result['tasks'].append({'source_id':doc,'symbol':symbol,'interval_seconds':interval,'purpose':purpose,'priority':priority,
                'once_key':f'{day}:{doc}:{symbol}' if once else None,'requires_contract_pass':True,'execute':False})
    continuous=False
    if time(8,20)<=t<time(9,10):
        result['phase']='PREMARKET'
        for doc in (90,108):add(doc,None,priority='REGULATORY',once=True)
    elif time(9,15)<=t<time(9,25):
        result['phase']='OPEN_AUCTION';add(9,10,symbols=holdings,purpose='SNAPSHOT_ONLY')
    elif time(9,25)<=t<time(9,30):
        result['phase']='PREOPEN_QUIET';result['reset_token']=day+':PREOPEN'
    elif time(9,30)<=t<time(11,30):
        result['phase']='AM';continuous=True;result['reset_token']=day+':AM'
        result['window_features_ready']=t>=time(9,31);result['opening_profile']=t<time(9,45)
    elif time(11,30)<=t<time(13):
        result['phase']='LUNCH'
        for doc in (90,108):add(doc,900,priority='REGULATORY')
    elif time(13)<=t<time(14,57):
        result['phase']='PM';continuous=True;result['reset_token']=day+':PM';result['window_features_ready']=t>=time(13,1)
        if time(14,40)<=t<time(14,56,30):
            result['phase']='CLOSING_CANDIDATES';add(103,30,purpose='INFO_CANDIDATE')
        elif t>=time(14,56,30):result['phase']='CANDIDATES_EXPIRED'
    elif time(14,57)<=t<time(15):
        result['phase']='CLOSE_AUCTION';add(9,10,symbols=holdings,purpose='SNAPSHOT_ONLY')
    elif time(15,10)<=t<time(17,30):
        result['phase']='POSTMARKET';add(106,None,symbols=holdings,purpose='SAME_DAY_AUDIT',once=True)
    else:result['phase']='QUIET'
    if continuous:
        for doc,interval in ((9,10),(13,30),(8,60),(75,60)):
            add(doc,interval,symbols=holdings,purpose='HOLDING_OBSERVATION',priority='HOLDING_RISK')
        add(41,180,purpose='SECTOR_RAW_OBSERVATION')
        for doc in (36,38):add(doc,120,priority='MARKET_RISK')
        for doc in (90,108):add(doc,600,priority='REGULATORY')
    return result

def current_plan(root,now=None,holdings=()):
    now=now or datetime.now(TZ)
    gate=status(root,now)
    result=propose(now,holdings,calendar_state=gate['calendar_status'])
    # Owner explicitly disabled automatic collection: never return executable work.
    result['runtime_blockers']=gate['blockers']
    result['automatic_execution']=False
    return result

if __name__=='__main__':print(json.dumps(current_plan(Path('/workspace')),ensure_ascii=False,indent=2))
