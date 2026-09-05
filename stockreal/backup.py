"""SQLite snapshot and isolated restore verification. Never overwrites the live DB."""
import argparse
import asyncio
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo
from stockreal.audit_store import AuditStore

def inspect_database(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('backup integrity failed')
        if db.execute('PRAGMA user_version').fetchone()[0]!=3:raise ValueError('unsupported backup version')
        if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('foreign key integrity failed')
        revision=db.execute('SELECT max(revision) FROM holdings_revision').fetchone()[0]
        return {'schema_version':3,'holdings_revision':revision,
            'counts':{table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('endpoint_contract','job_run','data_quality_event','api_daily_budget','holdings_revision')},
            'budget':dict(db.execute('SELECT trade_date,attempts FROM api_daily_budget'))}
    finally:db.close()

def verify_restore(path,expected_sha256):
    path=Path(path)
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=expected_sha256:raise ValueError('backup hash mismatch')
    original=inspect_database(path)
    with TemporaryDirectory(prefix='restore-check-',dir=path.parent) as folder:
        restored=Path(folder)/'restored.db';shutil.copyfile(path,restored)
        result=inspect_database(restored)
        if result!=original:raise ValueError('restore verification mismatch')
    return {'restore_verified':True,'production_database_overwritten':False,'database':result}

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['create','verify'])
    parser.add_argument('--file',type=Path);args=parser.parse_args()
    if args.action=='create':
        stamp=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%dT%H%M%S%f')
        path=Path('/workspace/data/backups')/('stockreal-'+stamp+'.db')
        store=await AuditStore('/workspace/data/stockreal.db').start()
        try:report=await store.backup(path)
        finally:await store.close()
        report.update(await asyncio.to_thread(verify_restore,path,report['sha256']))
        with path.with_suffix('.manifest.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
        print(json.dumps(report,ensure_ascii=False))
    else:
        if not args.file:parser.error('verify requires --file')
        manifest=json.loads(args.file.with_suffix('.manifest.json').read_text())
        print(json.dumps(await asyncio.to_thread(verify_restore,args.file,manifest['sha256']),ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
