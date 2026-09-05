import asyncio
import copy
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from stockreal.audit_store import AuditStore

class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db'
        self.store=await AuditStore(self.path).start()
        self.contracts=[{'endpoint_code':'LHV-DOC-009','contract_version':'candidate-1','config_version':'R3.5','contract_status':'UNVERIFIED'}]
        self.report={'mode':'OFFLINE_REPLAY','config_version':'R3.5','results':[{'endpoint_code':'LHV-DOC-009','integrity_status':'MATCH','sample_sha256':'sample','quality_flags':['FIELD_CONTRACT_UNVERIFIED']}]}
    async def asyncTearDown(self):
        await self.store.close();self.tmp.cleanup()
    async def test_wal_and_idempotency(self):
        self.assertTrue((await self.store.write_replay(self.contracts,self.report))['inserted'])
        self.assertFalse((await self.store.write_replay(self.contracts,self.report))['inserted'])
        self.assertEqual(await asyncio.wait_for(self.store.summary(),5),{'journal_mode':'wal','contracts':1,'runs':1,'events':1})
    async def test_concurrent_duplicates(self):
        results=await asyncio.gather(*(self.store.write_replay(self.contracts,self.report) for _ in range(100)))
        self.assertEqual(sum(r['inserted'] for r in results),1)
        self.assertEqual((await asyncio.wait_for(self.store.summary(),5))['events'],1)
    async def test_distinct_reports(self):
        reports=[]
        for i in range(25):
            r=copy.deepcopy(self.report);r['results'][0]['sample_sha256']=str(i);reports.append(r)
        await asyncio.gather(*(self.store.write_replay(self.contracts,r) for r in reports))
        self.assertEqual((await asyncio.wait_for(self.store.summary(),5))['events'],25)
    async def test_atomic_rollback_and_worker_recovers(self):
        report=copy.deepcopy(self.report)
        report['results'].append({'endpoint_code':'UNKNOWN','integrity_status':'MATCH'})
        with self.assertRaises(sqlite3.IntegrityError):await self.store.write_replay(self.contracts,report)
        self.assertEqual(await asyncio.wait_for(self.store.summary(),5),{'journal_mode':'wal','contracts':0,'runs':0,'events':0})
        await self.store.write_replay(self.contracts,self.report)
        self.assertEqual((await asyncio.wait_for(self.store.summary(),5))['events'],1)
    async def test_restart_preserves_and_deduplicates(self):
        await self.store.write_replay(self.contracts,self.report)
        await self.store.close()
        self.store=await AuditStore(self.path).start()
        self.assertFalse((await self.store.write_replay(self.contracts,self.report))['inserted'])
        self.assertEqual((await asyncio.wait_for(self.store.summary(),5))['events'],1)
    async def test_closed_rejects_new_writes(self):
        await self.store.close()
        with self.assertRaises(RuntimeError):await self.store.write_replay(self.contracts,self.report)
    async def test_writer_yields_between_batches(self):
        ticks=0
        done=False
        async def heartbeat():
            nonlocal ticks
            while not done:
                ticks+=1
                await asyncio.sleep(0)
        task=asyncio.create_task(heartbeat())
        try:
            await asyncio.gather(*(self.store.write_replay(self.contracts,self.report) for _ in range(20)))
        finally:
            done=True
            await task
        self.assertGreater(ticks,5)
    async def test_wrong_config_is_rejected(self):
        self.contracts[0]['config_version']='R3.1'
        with self.assertRaises(sqlite3.IntegrityError):await self.store.write_replay(self.contracts,self.report)
        self.assertEqual((await asyncio.wait_for(self.store.summary(),5))['runs'],0)

if __name__=='__main__':unittest.main()
