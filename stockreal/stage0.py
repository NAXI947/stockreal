"""Manual R3.5 intake and bounded probes. No background collection or signals."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo
from stockreal.response_validation import assess

ROOT = Path('/workspace')
SECRET_NAMES = {'token', 'key', 'apisecret', 'userid', 'deviceid', 'authorization', 'password', 'secret', 'access_token', 'refresh_token'}
HOSTS = {'apphq.longhuvip.com', 'apphwhq.longhuvip.com', 'apphwshhq.longhuvip.com', 'flash-api.xuangubao.com.cn'}
TARGETS = [9, 8, 13, 75, 41, 81, 36, 38, 103, 108, 90]
SINGLE = {8, 9, 13, 14, 75}
LIMIT = 4 * 1024 * 1024

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def scrub(value, secrets=()):
    if isinstance(value, dict):
        return {str(k): '<REDACTED>' if str(k).lower() in SECRET_NAMES else scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secrets) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)([?&](?:token|key|apisecret|userid|deviceid|access_token)=)[^&\s"<>]*', r'\1<REDACTED>', value)
        for secret in sorted(set(secrets), key=len, reverse=True):
            if secret and secret not in {'0', 'null', 'none'}:
                value = value.replace(secret, '<REDACTED>')
        return value
    if value is not None and str(value) in secrets and str(value) != '0':
        return '<REDACTED>'
    return value

def intake(catalog, source_credentials):
    result, profiles, seen = [], {}, set()
    for item in catalog:
        doc = int(item['id'])
        if doc in seen:
            raise ValueError('duplicate endpoint id')
        seen.add(doc)
        endpoint = f'LHV-DOC-{doc:03d}'
        parts = urlsplit(item.get('api_url', ''))
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        raw_profile = source_credentials.get(str(doc), {})
        credentials = raw_profile.get('credentials', {})
        source_parts = urlsplit(raw_profile.get('full_url', ''))
        source_pairs = dict(parse_qsl(source_parts.query, keep_blank_values=True))
        if raw_profile and (source_parts.hostname != parts.hostname or source_parts.path != parts.path or any(source_pairs.get(k) != dict(pairs).get(k) for k in ('a', 'c', 'apiv'))):
            raise ValueError('credential endpoint binding mismatch')
        profile, safe_pairs = {}, []
        for key, value in pairs:
            if key.lower() in SECRET_NAMES:
                actual = credentials.get(key, source_pairs.get(key, ''))
                if actual and not str(actual).startswith('<'):
                    profile[key] = str(actual)
                safe_pairs.append([key, '<CREDENTIAL>'])
            else:
                safe_pairs.append([key, value])
        profiles[endpoint] = profile
        result.append({'endpoint_code': endpoint, 'source_id': doc, 'contract_version': 'R3.5-candidate-1',
            'config_version': 'R3.5', 'method': 'GET', 'method_status': 'CANDIDATE',
            'origin': urlunsplit((parts.scheme, parts.netloc, parts.path, '', '')),
            'query_template': safe_pairs, 'route_key': dict(pairs).get('apiv', ''), 'credential_profile': endpoint,
            'supports_batch': False if doc in SINGLE else None,
            'contract_status': 'UNVERIFIED', 'field_mapping': None})
    return result, profiles

def request_url(contract, profile):
    parts = urlsplit(contract['origin'])
    if parts.hostname not in HOSTS or parts.scheme != 'https' or parts.port not in (None, 443) or parts.username:
        raise ValueError('host or transport not allowed')
    if contract['source_id'] in SINGLE:
        symbols = [v for k, v in contract['query_template'] if k == 'StockID']
        if len(symbols) != 1 or not isinstance(symbols[0], str) or not re.fullmatch(r'[0-9]{6}', symbols[0]):
            raise ValueError('exactly one canonical StockID required')
        if any(k.lower().startswith('stockid') and k != 'StockID' for k, _ in contract['query_template']):
            raise ValueError('array or alias stock parameter forbidden')
    pairs = []
    for key, value in contract['query_template']:
        if key.lower() in SECRET_NAMES:
            value = profile.get(key)
            if value is None or str(value).startswith('<'):
                raise ValueError('missing credential')
        if contract['source_id'] == 13 and key == 'st':
            value = '100'
        if '<' in str(value) or '>' in str(value):
            raise ValueError('unresolved parameter')
        pairs.append((key, value))
    return contract['origin'] + '?' + urlencode(pairs)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def shape(obj, depth=0):
    if depth > 4:
        return type(obj).__name__
    if isinstance(obj, dict):
        return {k: shape(v, depth+1) for k, v in obj.items()}
    if isinstance(obj, list):
        return {'type': 'array', 'count': len(obj), 'first_item': shape(obj[0], depth+1) if obj else None,
                'row_lengths': sorted({len(row) for row in obj if isinstance(row, list)})}
    return type(obj).__name__

def probe(contract, profile, outdir):
    start = time.monotonic()
    result = {'endpoint_code': contract['endpoint_code'], 'observed_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'context': 'MANUAL_SAMPLE_UNCLASSIFIED', 'contract_status': 'UNVERIFIED', 'business_status': 'NOT_EVALUATED',
              'parameter_policy': 'original_catalog_parameters; DOC-013 st=100; dates and symbols not rewritten'}
    try:
        req = Request(request_url(contract, profile), headers={'User-Agent': 'StockReal-Stage0/0.1', 'Accept': 'application/json'})
        with build_opener(NoRedirect).open(req, timeout=20) as response:
            raw = response.read(LIMIT+1)
            result['http_status'] = response.status
        if len(raw) > LIMIT:
            raise ValueError('response size limit')
        payload = json.loads(raw)
        cleaned = scrub(payload, tuple(profile.values()))
        result['transport_status'] = 'JSON_RECEIVED'
        result['raw_payload_hash'] = hashlib.sha256(raw).hexdigest()
        result['shape'] = shape(cleaned)
        schema_path = ROOT/'contracts/observed-schemas'/(contract['endpoint_code']+'.json')
        baseline = load(schema_path) if schema_path.exists() else None
        result.update(assess(contract['source_id'], cleaned, result['http_status'], baseline))
        result['business_markers'] = {k: cleaned[k] for k in ('code', 'errcode', 'error', 'success', 'status') if isinstance(cleaned, dict) and k in cleaned}
        save(Path(outdir) / (contract['endpoint_code'] + '.sample.json'), cleaned)
    except HTTPError as exc:
        result.update(transport_status='HTTP_ERROR', http_status=exc.code)
    except Exception as exc:
        result.update(transport_status='FAILED', error_type=type(exc).__name__)
    result['elapsed_ms'] = round((time.monotonic()-start)*1000)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['import', 'probe'])
    args = parser.parse_args()
    if args.action == 'import':
        catalog, profiles = intake(load(ROOT/'.secrets/catalog-source.json'), load(ROOT/'.secrets/credential-source.json'))
        save(ROOT/'contracts/endpoints.json', catalog)
        save(ROOT/'.secrets/runtime-profiles.json', profiles)
        (ROOT/'.secrets/runtime-profiles.json').chmod(0o600)
        print(json.dumps({'imported': len(catalog), 'contract_pass': 0, 'config_version': 'R3.5'}))
    else:
        catalog, profiles = load(ROOT/'contracts/endpoints.json'), load(ROOT/'.secrets/runtime-profiles.json')
        run = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S')
        outdir, results = ROOT/'data/stage0'/run, []
        for doc in TARGETS:
            contract = next(c for c in catalog if c['source_id'] == doc)
            result = probe(contract, profiles[contract['credential_profile']], outdir)
            results.append(result)
            print(json.dumps({k: result[k] for k in ('endpoint_code', 'transport_status', 'contract_status')}), flush=True)
            time.sleep(1)
        report = {'config_version': 'R3.5', 'automatic_collection_enabled': False,
                  'directional_signals_enabled': False, 'contract_pass': 0, 'results': results}
        save(outdir/'report.json', report)
        save(ROOT/'data/stage0/latest.json', report)

if __name__ == '__main__':
    main()
