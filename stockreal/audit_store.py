"""Single-process, single-writer SQLite diagnostics. No signal production or sender."""
import asyncio
import hashlib
import json
import sqlite3
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
PRAGMA user_version=1;
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
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,isolation_level=None,timeout=5)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            if db.execute('PRAGMA user_version').fetchone()[0] not in (0,1):
                raise RuntimeError('unsupported database version')
            db.executescript(SCHEMA)
        except BaseException:
            db.close();raise
        self._connection=db
        self._worker=asyncio.create_task(self._run())
        return self
    async def _run(self):
        while True:
            item=await self._queue.get()
            try:
                if item is None:return
                operation,future=item
                try:
                    result=operation(self._connection)
                except Exception as error:
                    if self._connection.in_transaction:self._connection.rollback()
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
            self._connection.close();self._connection=None
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
