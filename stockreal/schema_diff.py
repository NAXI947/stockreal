"""Explain structural differences without returning response values or granting a contract."""
from stockreal.response_validation import matches

def differences(value,schema,path='$'):
    kind=schema['type'];actual=type(value).__name__
    def issue(reason,expected,observed):
        return [{'path':path,'reason':reason,'expected':expected,'observed':observed}]
    if kind=='dict':
        if not isinstance(value,dict):return issue('TYPE_CHANGED','dict',actual)
        fields=schema['fields'];out=[]
        for key in sorted(fields.keys()-value.keys()):
            out.append({'path':path+'.'+key,'reason':'MISSING_FIELD','expected':fields[key]['type'],'observed':'absent'})
        for key in sorted(value.keys()-fields.keys()):
            out.append({'path':path+'.'+key,'reason':'ADDED_FIELD','expected':'absent','observed':type(value[key]).__name__})
        for key in sorted(value.keys()&fields.keys()):out.extend(differences(value[key],fields[key],path+'.'+key))
        return out
    if kind=='tuple':
        if not isinstance(value,list):return issue('TYPE_CHANGED','positional_array',actual)
        if len(value)!=len(schema['items']):return issue('COLUMN_COUNT_CHANGED',len(schema['items']),len(value))
        return [item for index,(v,s) in enumerate(zip(value,schema['items'])) for item in differences(v,s,path+'['+str(index)+']')]
    if kind=='list':
        if not isinstance(value,list):return issue('TYPE_CHANGED','list',actual)
        out=[]
        for index,item in enumerate(value):
            item_path=path+'['+str(index)+']'
            if any(matches(item,s) for s in schema['variants']):continue
            if not schema['variants']:
                # An empty observed sample has no item contract. Do not call this
                # a verified provider schema change, or silently accept the row.
                out.append({'path':item_path,'reason':'ITEM_SHAPE_NOT_OBSERVED','expected':'no observed item schema','observed':type(item).__name__})
                continue
            candidates=[differences(item,s,item_path) for s in schema['variants']]
            out.extend(min(candidates,key=lambda items:(len(items),str(items))))
        return out
    return [] if actual==kind else issue('TYPE_CHANGED',kind,actual)

def explain(value,schema,limit=50):
    if type(limit) is not int or not 1<=limit<=500:raise ValueError('invalid difference limit')
    result=differences(value,schema)
    return {'observed_match':not result,'difference_count':len(result),'differences':result[:limit],
        'truncated':len(result)>limit,'contract_status':'UNVERIFIED','production_eligible':False}
