"""Network-free replay of explicitly pinned, redacted archived responses."""
import hashlib
import json
from pathlib import Path
from stockreal.stage0 import ROOT, load, save
from stockreal.response_validation import infer_schema, assess

def replay(root):
    index=load(root/'contracts/sample-index.json')
    reports=[]
    for entry in index['samples']:
        path=root/entry['path']
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
            reports.append({'endpoint_code':entry['endpoint_code'],'integrity_status':'SAMPLE_HASH_MISMATCH','production_eligible':False})
            continue
        payload=json.loads(raw)
        schema=load(root/entry['schema_path'])
        result=assess(entry['source_id'],payload,schema=schema)
        result.update(endpoint_code=entry['endpoint_code'],integrity_status='MATCH',sample_sha256=entry['sha256'])
        reports.append(result)
    return {'mode':'OFFLINE_REPLAY','config_version':'R3.5','contract_pass':0,'results':reports}

if __name__=='__main__':
    report=replay(ROOT)
    save(ROOT/'docs/stage0/replay-report.json',report)
    for r in report['results']:
        print(json.dumps(r,ensure_ascii=False))
    raise SystemExit(any(r['integrity_status']!='MATCH' or r.get('schema_status')=='DRIFT' for r in report['results']))
