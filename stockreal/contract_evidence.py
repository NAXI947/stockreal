"""Bounded manual stage-0 evidence. Never grants production eligibility."""
import argparse
import asyncio
import copy
import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from stockreal.audit_store import AuditStore
from stockreal.stage0 import load,save,probe,request_url

def diagnostic_contract(contract,overrides):
    allowed={41:{'Index'},75:{'Time'},81:{'DStart','DEnd','Index'}}
    source=contract['source_id']
    if not overrides.keys()<=allowed.get(source,set()):raise ValueError('unsupported override')
    for key,value in overrides.items():
        if not isinstance(value,str):raise ValueError('string parameter required')
        if key in {'Index','Time'} and (not value.isascii() or not value.isdigit() or len(value)>10):raise ValueError('invalid cursor')
        if key in {'DStart','DEnd'}:
            if datetime.strptime(value,'%Y-%m-%d').strftime('%Y-%m-%d')!=value:raise ValueError('invalid date')
    result=copy.deepcopy(contract)
    keys=[k for k,v in result['query_template']]
    if any(keys.count(k)!=1 for k in overrides):raise ValueError('missing or duplicate override key')
    result['query_template']=[[k,overrides.get(k,v)] for k,v in result['query_template']]
    if source==81:
        params=dict(result['query_template'])
        if params['DStart']>params['DEnd']:raise ValueError('reversed dates')
    return result

def pagination_evidence(pages):
    """Count and identity checks are necessary, but not proof of an atomic snapshot."""
    flags=set();codes=[];counts=[];days=[];widths=set()
    for payload in pages:
        if not isinstance(payload,dict):flags.add('INVALID_ENVELOPE');continue
        count=payload.get('Count');rows=payload.get('list')
        if type(count) is not int or count<0:flags.add('INVALID_COUNT')
        else:counts.append(count)
        days.append(payload.get('Day'))
        if not isinstance(rows,list):flags.add('INVALID_ROWS');continue
        for row in rows:
            if not isinstance(row,list) or not row or not isinstance(row[0],str):flags.add('INVALID_ROW');continue
            widths.add(len(row));codes.append(row[0])
    if len(set(counts))!=1:flags.add('COUNT_CHANGED_OR_MISSING')
    if not days or any(d!=days[0] or not d for d in days):flags.add('DAY_CHANGED_OR_MISSING')
    if len(codes)!=len(set(codes)):flags.add('DUPLICATE_CODE')
    if widths!={19}:flags.add('ROW_WIDTH_UNVERIFIED')
    expected=counts[0] if counts else None
    if expected is None or len(set(codes))!=expected:flags.add('INCOMPLETE_OR_EXCESS_ROWS')
    if expected==0:flags.add('EMPTY_UNIVERSE')
    return {'page_count':len(pages),'row_count':len(codes),'unique_codes':len(set(codes)),
        'declared_count':expected,'row_widths':sorted(widths),'flags':sorted(flags),
        'observed_coverage_complete':not flags,'atomic_snapshot_verified':False,
        'breadth_available':False,'contract_status':'UNVERIFIED','production_eligible':False,
        'disabled_metrics':['Breadth','SectorHeatScore','DivergenceBaseScore','DivergenceScore'],
        'reason':'No verified batch N_up/N_valid or constituent net inflow; pagination alone does not establish breadth.'}

async def collect(root):
    root=Path(root);catalog={x['source_id']:x for x in load(root/'contracts/endpoints.json')}
    profiles=load(root/'.secrets/runtime-profiles.json')
    index=load(root/'contracts/sample-index.json')['samples']
    quote_ref=next(x for x in index if x['source_id']==9)
    raw=(root/quote_ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=quote_ref['sha256']:raise ValueError('quote reference hash mismatch')
    quote=load(root/quote_ref['path']);day=datetime.strptime(str(quote['day']),'%Y%m%d').strftime('%Y-%m-%d')
    # At most seven individual requests. Board indexes are offsets under test,
    # not accepted provider pagination semantics. Never fan out to constituents.
    plan=[(75,{'Time':'0'}),(81,{'DStart':day,'DEnd':day})]+[(41,{'Index':str(i)}) for i in (0,60,120,180,240)]
    prepared=[]
    for source,overrides in plan:
        contract=diagnostic_contract(catalog[source],overrides)
        request_url(contract,profiles[contract['credential_profile']]) # fail before claiming any budget
        prepared.append((source,overrides,contract))
    stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S%f')
    out=root/'data/stage0'/('evidence-'+stamp);results=[];pages=[]
    store=await AuditStore(root/'data/stockreal.db').start()
    try:
        for seq,(source,overrides,contract) in enumerate(prepared):
            today=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
            claim=await store.claim_budget(today)
            if not claim['allowed']:break
            folder=out/str(seq)
            result=await asyncio.to_thread(probe,contract,profiles[contract['credential_profile']],folder)
            result['parameter_policy']='BOUNDED_MANUAL_OVERRIDE_UNVERIFIED'
            result['overrides']=overrides
            sample=folder/(contract['endpoint_code']+'.sample.json')
            if sample.exists():
                result['sample_path']=str(sample.relative_to(root));result['sample_sha256']=hashlib.sha256(sample.read_bytes()).hexdigest()
                payload=load(sample)
                if source==41:pages.append(payload)
                if isinstance(payload,dict):
                    result['row_count']=len(payload.get('list',payload.get('List',payload.get('dadanjinge',[]))))
            results.append(result)
            save(out/'partial-report.json',{'results':results,'automatic_collection_enabled':False})
            if result.get('http_status') in (401,403,429):break
            await asyncio.sleep(1)
        report={'observed_at':stamp,'context':'MANUAL_NON_TRADING_SESSION_UNCLASSIFIED',
            'reference_quote_day':day,'reference_quote_hash':quote_ref['sha256'],
            'automatic_collection_enabled':False,'directional_signals_enabled':False,
            'contract_pass':0,'max_attempts':7,'attempts':len(results),'results':results,
            'board':pagination_evidence(pages),'budget':await store.budget_status(today)}
        save(out/'report.json',report);save(root/'docs/stage0/field-evidence.json',report)
        return {k:v for k,v in report.items() if k!='results'}
    finally:await store.close()

if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser();parser.add_argument('--manual',action='store_true',required=True)
    parser.parse_args();print(json.dumps(asyncio.run(collect('/workspace')),ensure_ascii=False))
