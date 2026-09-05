"""Observational schema gate, never a semantic field contract certification."""
import json
import re

DATA_PATHS={8:'trend',9:'real',13:'List',75:'dadanjinge',41:'list',81:'List',36:'data',38:'data',103:'List',108:'List',90:'List'}

def infer_schema(value, positional=False):
    if isinstance(value,dict):
        return {'type':'dict','fields':{k:infer_schema(v,bool(re.fullmatch(r'[bs]\d+',k))) for k,v in sorted(value.items())}}
    if isinstance(value,list):
        if positional:
            return {'type':'tuple','items':[infer_schema(v) for v in value]}
        variants={json.dumps(infer_schema(v,isinstance(v,list)),sort_keys=True) for v in value}
        return {'type':'list','variants':[json.loads(v) for v in sorted(variants)]}
    return {'type':type(value).__name__}

def matches(value,schema):
    kind=schema['type']
    if kind=='dict':
        return isinstance(value,dict) and value.keys()==schema['fields'].keys() and all(matches(value[k],s) for k,s in schema['fields'].items())
    if kind=='tuple':
        return isinstance(value,list) and len(value)==len(schema['items']) and all(matches(v,s) for v,s in zip(value,schema['items']))
    if kind=='list':
        return isinstance(value,list) and all(any(matches(v,s) for s in schema['variants']) for v in value)
    return type(value).__name__==kind

def assess(doc,payload,http_status=200,schema=None):
    result={'business_status':'NOT_EVALUATED','data_status':'NOT_EVALUATED','schema_status':'NOT_EVALUATED',
            'contract_status':'UNVERIFIED','production_eligible':False,'quality_flags':['FIELD_CONTRACT_UNVERIFIED']}
    if http_status!=200:
        result['quality_flags'].append('HTTP_ERROR')
        return result
    if not isinstance(payload,dict):
        result['quality_flags'].append('INVALID_ENVELOPE')
        return result
    if doc not in DATA_PATHS:
        result['quality_flags'].append('UNSUPPORTED_ENDPOINT')
        return result
    code=payload.get('code') if doc in (36,38) else payload.get('errcode')
    # Stock code and market status are not error codes on LongHuVIP.
    ok=type(code) is int and code==20000 if doc in (36,38) else type(code) in (str,int) and str(code)=='0'
    result['business_status']='CODE_SUCCESS' if ok else 'CODE_ERROR_OR_MISSING'
    if not ok:
        result['quality_flags'].append('UPSTREAM_BUSINESS_ERROR')
        return result
    field=DATA_PATHS[doc]
    expected_type=dict if doc==9 else list
    if field not in payload or not isinstance(payload[field],expected_type):
        result['quality_flags'].append('SCHEMA_DRIFT')
        result['schema_status']='DRIFT'
        return result
    result['data_status']='PRESENT' if payload[field] else 'EMPTY'
    if not payload[field]: result['quality_flags'].append('EMPTY_DATA')
    if schema is None:
        result['schema_status']='NO_BASELINE'
    else:
        valid=matches(payload,schema)
        result['schema_status']='OBSERVED_MATCH' if valid else 'DRIFT'
        if not valid: result['quality_flags'].append('SCHEMA_DRIFT')
    return result
