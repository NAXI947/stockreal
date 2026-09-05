"""Single-process, single-writer SQLite diagnostics. No signal production or sender."""
import asyncio
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from stockreal.stage0 import load
from stockreal.replay import replay

SCHEMA='''
CREATE TABLE IF NOT EXISTS endpoint_contract (
 endpoint_code TEXT PRIMARY KEY,
 contract_version TEXT NOT NULL,
 config_version TEXT NOT NULL CHECK(config_version='R3.5'),
 contract_status TEXT NOT NULL,
 metadata_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_run (
 run_id TEXT PRIMARY KEY,
 kind TEXT NOT NULL CHECK(kind='OFFLINE_REPLAY'),
 config_version TEXT NOT NULL CHECK(config_version='R3.5'),
 recorded_at TEXT NOT NULL,
 report_sha256 TEXT NOT NULL UNIQUE,
 result_count INTEGER NOT NULL CHECK(result_count>=0)
);
CREATE TABLE IF NOT EXISTS data_quality_event (
 run_id TEXT NOT NULL REFERENCES job_run(run_id),
 endpoint_code TEXT NOT NULL REFERENCES endpoint_contract(endpoint_code),
 sample_sha256 TEXT,
 business_status TEXT NOT NULL,
 data_status TEXT NOT NULL,
 schema_status TEXT NOT NULL,
 integrity_status TEXT NOT NULL,
 quality_flags_json TEXT NOT NULL,
 PRIMARY KEY(run_id,endpoint_code)
);
CREATE TABLE IF NOT EXISTS api_daily_budget (
 trade_date TEXT PRIMARY KEY,
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 80000)
);
CREATE TABLE IF NOT EXISTS holdings_revision (
 revision INTEGER PRIMARY KEY CHECK(revision>=0),
 recorded_at TEXT NOT NULL,
 holdings_json TEXT NOT NULL,
 content_sha256 TEXT NOT NULL
);
INSERT OR IGNORE INTO holdings_revision VALUES (0,'INITIAL','[]','4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945');
PRAGMA user_version=3;
'''

def canonical(obj):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'))

class AuditStore:
    def __init__(self,path):
        self.path=Path(path)
        self._queue=asyncio.Queue(maxsize=256)
        self._lock=asyncio.Lock()
        self._worker=None
        self._closing=False
        self._connection=None
    async def start(self):
        if self._worker is not None or self._closing:raise RuntimeError('store lifecycle invalid')
        self._executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='stockreal-sqlite')
        try:
            self._connection=await asyncio.get_running_loop().run_in_executor(self._executor,self._open)
        except BaseException:
            self._executor.shutdown(wait=True)
            self._closing=True
            raise
        self._worker=asyncio.create_task(self._run())
        return self
    def _open(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,isolation_level=None,timeout=5)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            if db.execute('PRAGMA user_version').fetchone()[0] not in (0,1,2,3):
                raise RuntimeError('unsupported database version')
            db.executescript('BEGIN IMMEDIATE;'+SCHEMA+'COMMIT;')
            return db
        except BaseException:
            db.close();raise
    def _execute(self,operation):
        try:return operation(self._connection)
        except Exception:
            if self._connection.in_transaction:self._connection.rollback()
            raise
    async def _run(self):
        while True:
            item=await self._queue.get()
            try:
                if item is None:return
                operation,future=item
                try:
                    result=await asyncio.get_running_loop().run_in_executor(self._executor,self._execute,operation)
                except Exception as error:
                    # Do not share the live worker traceback with consumers.
                    if not future.done():future.set_exception(error.with_traceback(None))
                else:
                    if not future.done():future.set_result(result)
            finally:
                self._queue.task_done()
                # Let other application tasks run between committed batches.
                await asyncio.sleep(0)
    async def _submit(self,operation):
        async with self._lock:
            if self._worker is None or self._closing:raise RuntimeError('store is not open')
            future=asyncio.get_running_loop().create_future()
            await self._queue.put((operation,future))
        return await future
    async def close(self):
        async with self._lock:
            if self._worker is None:return
            if not self._closing:
                self._closing=True
                await self._queue.put(None)
        await self._worker
        if self._connection is not None:
            await asyncio.get_running_loop().run_in_executor(self._executor,self._connection.close)
            self._connection=None
            self._executor.shutdown(wait=True)
    async def write_replay(self,contracts,report):
        # Copy at submission: queued work must not observe caller mutation.
        contracts=json.loads(canonical(contracts));report=json.loads(canonical(report))
        if report.get('mode')!='OFFLINE_REPLAY' or report.get('config_version')!='R3.5':
            raise ValueError('unsupported audit report')
        digest=hashlib.sha256(canonical(report).encode()).hexdigest()
        run_id='replay-'+digest
        recorded_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
        def operation(db):
            db.execute('BEGIN IMMEDIATE')
            for c in contracts:
                db.execute('INSERT INTO endpoint_contract VALUES (?,?,?,?,?) ON CONFLICT(endpoint_code) DO UPDATE SET contract_version=excluded.contract_version,config_version=excluded.config_version,contract_status=excluded.contract_status,metadata_sha256=excluded.metadata_sha256',
                    (c['endpoint_code'],c['contract_version'],c['config_version'],c['contract_status'],hashlib.sha256(canonical(c).encode()).hexdigest()))
            changed=db.execute('INSERT OR IGNORE INTO job_run VALUES (?,?,?,?,?,?)',
                (run_id,'OFFLINE_REPLAY','R3.5',recorded_at,digest,len(report['results']))).rowcount
            if changed:
                for r in report['results']:
                    db.execute('INSERT INTO data_quality_event VALUES (?,?,?,?,?,?,?,?)',
                        (run_id,r['endpoint_code'],r.get('sample_sha256'),r.get('business_status','NOT_EVALUATED'),
                         r.get('data_status','NOT_EVALUATED'),r.get('schema_status','NOT_EVALUATED'),r['integrity_status'],
                         canonical(r.get('quality_flags',[]))))
            db.commit()
            return {'run_id':run_id,'inserted':bool(changed)}
        return await self._submit(operation)
    async def claim_budget(self,trade_date,*,allow_reserve=False):
        if type(allow_reserve) is not bool:raise ValueError('invalid reserve flag')
        if date.fromisoformat(trade_date).isoformat()!=trade_date:raise ValueError('invalid trade date')
        def operation(db):
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO api_daily_budget(trade_date) VALUES (?)',(trade_date,))
            used=db.execute('SELECT attempts FROM api_daily_budget WHERE trade_date=?',(trade_date,)).fetchone()[0]
            limit=80000 if allow_reserve else 60000
            if used>=limit:
                db.commit()
                return {'allowed':False,'used':used,'reason':'HARD_CAP' if used>=80000 else 'NORMAL_BUDGET_EXHAUSTED'}
            db.execute('UPDATE api_daily_budget SET attempts=attempts+1 WHERE trade_date=?',(trade_date,))
            db.commit()
            return {'allowed':True,'used':used+1,'reason':'RESERVE' if used>=60000 else 'NORMAL'}
        return await self._submit(operation)
    async def budget_status(self,trade_date):
        def operation(db):
            row=db.execute('SELECT attempts FROM api_daily_budget WHERE trade_date=?',(trade_date,)).fetchone()
            used=row[0] if row else 0
            return {'used':used,'normal_remaining':max(0,60000-used),'reserve_used':max(0,used-60000),'hard_remaining':80000-used}
        return await self._submit(operation)
    async def holdings(self):
        def operation(db):
            row=db.execute('SELECT revision,recorded_at,holdings_json,content_sha256 FROM holdings_revision ORDER BY revision DESC LIMIT 1').fetchone()
            return {'revision':row[0],'recorded_at':row[1],'holdings':json.loads(row[2]),'content_sha256':row[3],
                    'automatic_execution':False,'production_eligible':False}
        return await self._submit(operation)
    async def replace_holdings(self,holdings,*,expected_revision):
        from stockreal.holdings import validate_holdings
        if type(expected_revision) is not int or expected_revision<0:raise ValueError('invalid revision')
        cleaned=validate_holdings(holdings);payload=canonical(cleaned)
        digest=hashlib.sha256(payload.encode()).hexdigest()
        def operation(db):
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision,holdings_json FROM holdings_revision ORDER BY revision DESC LIMIT 1').fetchone()
            if row[0]!=expected_revision:raise ValueError('holdings revision conflict; reload before saving')
            if row[1]==payload:
                db.execute('COMMIT');return {'revision':row[0],'changed':False}
            revision=row[0]+1
            db.execute('INSERT INTO holdings_revision VALUES (?,?,?,?)',
                       (revision,datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),payload,digest))
            db.execute('COMMIT');return {'revision':revision,'changed':True}
        return await self._submit(operation)
    async def backup(self,destination):
        import os
        import uuid
        destination=Path(destination)
        def operation(db):
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists():raise FileExistsError('backup destination exists')
            temp=destination.parent/(destination.name+'.'+uuid.uuid4().hex+'.partial')
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
            try:
                target=sqlite3.connect(temp)
                try:
                    db.backup(target,pages=128)
                    if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('backup integrity failed')
                    target.execute('PRAGMA journal_mode=DELETE');target.commit()
                finally:target.close()
                with temp.open('rb') as stream:os.fsync(stream.fileno())
                os.link(temp,destination) # atomic publication without overwriting an existing backup
                with destination.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                return {'file':destination.name,'sha256':digest}
            finally:temp.unlink(missing_ok=True)
        return await self._submit(operation)
    async def summary(self):
        def operation(db):
            return {'journal_mode':db.execute('PRAGMA journal_mode').fetchone()[0],
                    'contracts':db.execute('SELECT count(*) FROM endpoint_contract').fetchone()[0],
                    'runs':db.execute('SELECT count(*) FROM job_run').fetchone()[0],
                    'events':db.execute('SELECT count(*) FROM data_quality_event').fetchone()[0]}
        return await self._submit(operation)

async def main():
    root=Path('/workspace')
    store=await AuditStore(root/'data/stockreal.db').start()
    try:
        result=await store.write_replay(load(root/'contracts/endpoints.json'),replay(root))
        result.update(await store.summary())
        print(json.dumps(result))
    finally:await store.close()

if __name__=='__main__':asyncio.run(main())
