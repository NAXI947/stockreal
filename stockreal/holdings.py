"""Personal manually maintained holdings; no broker connection or market execution."""
import argparse
import asyncio
import json
import re
from decimal import Decimal
from pathlib import Path

def validate_holdings(rows):
    if not isinstance(rows,list) or len(rows)>20:raise ValueError('up to 20 holdings required')
    output=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'symbol','reference_cost','observation_level'}:raise ValueError('unexpected holding fields')
        symbol=row['symbol'];cost=row['reference_cost'];level=row['observation_level']
        if not isinstance(symbol,str) or not re.fullmatch(r'[0-9]{6}[.](SH|SZ|BJ)',symbol):raise ValueError('canonical symbol required')
        if symbol in seen:raise ValueError('duplicate holding')
        seen.add(symbol)
        if cost is not None:
            if not isinstance(cost,str) or not re.fullmatch(r'[0-9]{1,12}(?:[.][0-9]{1,4})?',cost) or Decimal(cost)<=0:raise ValueError('positive decimal cost or null required')
            cost=format(Decimal(cost).normalize(),'f')
        # A personal label, not a risk rating or scheduler priority.
        if not isinstance(level,str) or not 1<=len(level.strip())<=32 or any(ord(c)<32 or ord(c)==127 for c in level):raise ValueError('observation label must be 1 to 32 characters')
        output.append({'symbol':symbol,'reference_cost':cost,'observation_level':level.strip()})
    return sorted(output,key=lambda row:row['symbol'])

async def main():
    from stockreal.audit_store import AuditStore
    parser=argparse.ArgumentParser(description='Local personal configuration; never starts collection')
    parser.add_argument('action',choices=['show','replace'])
    parser.add_argument('--file',type=Path);parser.add_argument('--expected-revision',type=int)
    args=parser.parse_args()
    if args.action=='replace' and (args.file is None or args.expected_revision is None):parser.error('replace requires --file and --expected-revision')
    store=await AuditStore('/workspace/data/stockreal.db').start()
    try:
        if args.action=='replace':
            rows=json.loads(args.file.read_text(encoding='utf-8-sig'))
            print(json.dumps(await store.replace_holdings(rows,expected_revision=args.expected_revision),ensure_ascii=False))
        else:print(json.dumps(await store.holdings(),ensure_ascii=False))
    finally:await store.close()

if __name__=='__main__':asyncio.run(main())
