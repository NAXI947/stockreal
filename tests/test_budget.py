import asyncio
import sqlite3
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from stockreal.audit_store import AuditStore

class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db'
        self.store=await AuditStore(self.path).start();self.day='2026-09-05'
    async def asyncTearDown(self):
        await self.store.close();self.tmp.cleanup()
    async def seed(self,count):
        await self.store._submit(lambda db:db.execute('INSERT INTO api_daily_budget VALUES (?,?)',(self.day,count)).rowcount)
    async def test_normal_and_reserve_boundaries(self):
        await self.seed(59999)
        self.assertTrue((await self.store.claim_budget(self.day))['allowed'])
        self.assertFalse((await self.store.claim_budget(self.day))['allowed'])
        self.assertEqual((await self.store.claim_budget(self.day,allow_reserve=True))['reason'],'RESERVE')
        self.assertEqual((await self.store.budget_status(self.day))['reserve_used'],1)
    async def test_concurrent_hard_cap(self):
        await self.seed(79999)
        results=await asyncio.gather(*(self.store.claim_budget(self.day,allow_reserve=True) for _ in range(20)))
        self.assertEqual(sum(r['allowed'] for r in results),1)
        self.assertEqual((await self.store.budget_status(self.day))['hard_remaining'],0)
    async def test_restart_and_day_boundary(self):
        await self.seed(60000);await self.store.close();self.store=await AuditStore(self.path).start()
        self.assertFalse((await self.store.claim_budget(self.day))['allowed'])
        self.assertTrue((await self.store.claim_budget('2026-09-06'))['allowed'])
        self.assertFalse((await self.store.claim_budget(self.day))['allowed'])
    async def test_slow_disk_does_not_block_loop(self):
        entered=threading.Event();release=threading.Event()
        def slow(db):
            entered.set();release.wait(2);return 1
        task=asyncio.create_task(self.store._submit(slow))
        try:
            for _ in range(100):
                if entered.is_set():break
                await asyncio.sleep(.01)
            self.assertTrue(entered.is_set())
            self.assertFalse(task.done())
            # Loop is still running while the single writer is waiting on disk.
            await asyncio.wait_for(asyncio.sleep(.02),.5)
        finally:release.set()
        self.assertEqual(await task,1)
    async def test_cancelled_consumer_does_not_break_writer(self):
        entered=threading.Event();release=threading.Event()
        def slow(db):entered.set();release.wait(2);return 1
        task=asyncio.create_task(self.store._submit(slow))
        while not entered.is_set():await asyncio.sleep(.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        release.set()
        self.assertEqual((await self.store.summary())['journal_mode'],'wal')
    async def test_v1_migration_preserves_audit(self):
        await self.store.close()
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TABLE api_daily_budget');db.execute('PRAGMA user_version=1')
            db.execute("INSERT INTO endpoint_contract VALUES ('keep','v1','R3.5','UNVERIFIED','hash')")
        self.store=await AuditStore(self.path).start()
        self.assertEqual((await self.store.summary())['contracts'],1)
        self.assertTrue((await self.store.claim_budget(self.day))['allowed'])

if __name__=='__main__':unittest.main()
