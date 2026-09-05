"""Offline, hash-bound review of saved stage-0 samples and observation baselines."""
import hashlib
import json
from pathlib import Path
from stockreal.schema_diff import explain
from stockreal.evidence_consistency import trade_consistency,funding_consistency
from stockreal.stage0 import load,save

def checked_sample(root,relative,expected):
    root=Path(root).resolve();path=(root/relative).resolve()
    if not path.is_relative_to(root/'data/stage0'):raise ValueError('sample outside stage0 evidence')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('sample hash mismatch')
    return json.loads(raw)

def review(root):
    root=Path(root);evidence=load(root/'docs/stage0/field-evidence.json')
    refs={x['endpoint_code']:x for x in load(root/'contracts/sample-index.json')['samples']}
    reports=[];consistency=[]
    for result in evidence['results']:
        if not result.get('sample_path'):continue
        code=result['endpoint_code'];reference=refs[code]
        original=checked_sample(root,reference['path'],reference['sha256'])
        schema=load(root/reference['schema_path'])
        # Validate the observation schema against its own immutable original.
        if not explain(original,schema)['observed_match']:raise ValueError('baseline is inconsistent with pinned sample')
        payload=checked_sample(root,result['sample_path'],result['sample_sha256'])
        source=reference['source_id']
        if source in (41,81):
            consistency.append({'source_id':source,'overrides':result['overrides'],
                'observation':funding_consistency(payload['list' if source==41 else 'List'],source)})
        reports.append({'endpoint_code':code,'overrides':result['overrides'],
            'sample_sha256':result['sample_sha256'],'baseline_sha256':hashlib.sha256((root/reference['schema_path']).read_bytes()).hexdigest(),
            'business_status':result.get('business_status'),'review':explain(payload,schema)})
    trade=refs['LHV-DOC-013']
    trade_payload=checked_sample(root,trade['path'],trade['sha256'])
    consistency.append({'source_id':13,'sample_sha256':trade['sha256'],'observation':trade_consistency(trade_payload['List'])})
    return {'mode':'OFFLINE_CONTRACT_REVIEW','upstream_requests':0,'contract_pass':0,
        'automatic_collection_enabled':False,'directional_signals_enabled':False,'results':reports,'cross_field_observations':consistency}

if __name__=='__main__':
    root=Path('/workspace');report=review(root);save(root/'docs/stage0/contract-review.json',report)
    print(json.dumps({'samples':len(report['results']),'differences':[{'endpoint':r['endpoint_code'],'params':r['overrides'],'count':r['review']['difference_count'],'first':r['review']['differences'][:4]} for r in report['results']],'contract_pass':0},ensure_ascii=False))
