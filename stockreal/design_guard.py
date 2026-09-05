"""Check immutable R3.5 inputs and phase-0 contract metadata before development."""
import hashlib
from pathlib import Path
from stockreal.stage0 import load, SINGLE

def check(root):
    baseline=load(root/'docs/design-baseline.json')
    errors=[]
    for entry in baseline['sources']:
        candidates=[p for p in (root/entry['name'],root/'docs/source'/entry['name']) if p.exists()]
        if not candidates:
            errors.append('MISSING_DESIGN:'+entry['name'])
        for path in candidates:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
                errors.append('DESIGN_CHANGED:'+entry['name'])
    policy=load(root/'config/runtime-policy.json')
    if policy.get('config_version')!='R3.5': errors.append('POLICY_VERSION_DRIFT')
    for field in ('automatic_collection_enabled','directional_signals_enabled'):
        if policy.get(field) is not False: errors.append('UNAPPROVED_ENABLE:'+field)
    required={'TurnoverRate','TrendScore','AdjustedReturnSeries','TPlusNEvaluation','ChipDistribution','AIChat','AutoTrading'}
    if not required.issubset(policy.get('disabled_phase1_features',[])): errors.append('PHASE1_SCOPE_DRIFT')
    contracts=load(root/'contracts/endpoints.json')
    for c in contracts:
        if c['config_version']!='R3.5': errors.append('VERSION_DRIFT:'+c['endpoint_code'])
        if c['source_id'] in SINGLE and c['supports_batch'] is not False:
            errors.append('BATCH_DRIFT:'+c['endpoint_code'])
    if not (root/'docs/PROGRESS.md').exists(): errors.append('MISSING_PROGRESS')
    return errors

if __name__=='__main__':
    errors=check(Path('/workspace'))
    for error in errors: print(error)
    print('DESIGN_BASELINE_PASS' if not errors else 'DESIGN_BASELINE_FAILED')
    raise SystemExit(bool(errors))
