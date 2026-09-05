import asyncio
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from stockreal.audit_store import AuditStore
from stockreal.holdings import validate_holdings

def holding(symbol='000001.SZ',cost='12.3400',level='普通观察'):
    return {'symbol':symbol,'reference_cost':cost,'observation_level':level}

class ValidationTests(unittest.TestCase):
    def test_canonical_cost_and_unknown(self):
        rows=validate_holdings([holding(),holding('600000.SH',None)])
        self.assertEqual(rows[0]['reference_cost'],'12.34');self.assertIsNone(rows[1]['reference_cost'])
    def test_invalid_inputs(self):
        invalid=[None,{},[holding()]*2,[holding(str(i).zfill(6)+'.SZ') for i in range(21)],
                 [holding('000001')],[holding('000001xSZ')],[holding(cost=1.2)],[holding(cost='NaN')],[holding(cost='0')],
                 [holding(cost='-1')],[holding(cost='1e2')],[holding(level='')],[holding(level='a\nb')],
                 [dict(holding(),token='secret')]]
        for rows in invalid:
            with self.subTest(rows=rows),self.assertRaises(ValueError):validate_holdings(rows)

class HoldingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.store=await AuditStore(self.path).start()
    async def asyncTearDown(self):
        await self.store.close();self.tmp.cleanup()
    async def test_revision_restart_and_audit(self):
        initial=await self.store.holdings();self.assertEqual(initial['holdings'],[])
        await self.store.claim_budget('2026-09-05')
        self.assertEqual(await self.store.replace_holdings([holding()],expected_revision=0),{'revision':1,'changed':True})
        self.assertFalse((await self.store.replace_holdings([holding(cost='12.34')],expected_revision=1))['changed'])
        await self.store.close();self.store=await AuditStore(self.path).start()
        self.assertEqual((await self.store.holdings())['revision'],1)
        self.assertEqual((await self.store.budget_status('2026-09-05'))['used'],1)
        await self.store.replace_holdings([],expected_revision=1)
        count=await self.store._submit(lambda db:db.execute('SELECT count(*) FROM holdings_revision').fetchone()[0])
        self.assertEqual(count,3);self.assertFalse((await self.store.holdings())['automatic_execution'])
    async def test_concurrent_edit_conflict_and_rollback(self):
        results=await asyncio.gather(*(self.store.replace_holdings([holding(str(i).zfill(6)+'.SZ')],expected_revision=0) for i in range(10)),return_exceptions=True)
        self.assertEqual(sum(isinstance(x,dict) for x in results),1)
        self.assertEqual(sum(isinstance(x,ValueError) for x in results),9)
        await self.store.replace_holdings([],expected_revision=1)
        self.assertEqual((await self.store.holdings())['revision'],2)
    async def test_invalid_never_mutates(self):
        for value in [-1,True,'0']:
            with self.assertRaises(ValueError):await self.store.replace_holdings([],expected_revision=value)
        with self.assertRaises(ValueError):await self.store.replace_holdings([holding(cost='NaN')],expected_revision=0)
        self.assertEqual((await self.store.holdings())['revision'],0)
    async def test_v2_migration_preserves_budget(self):
        await self.store.close()
        db=sqlite3.connect(self.path);db.execute('DROP TABLE holdings_revision');db.execute('PRAGMA user_version=2');db.execute("INSERT INTO api_daily_budget VALUES ('2026-09-05',7)");db.commit();db.close()
        self.store=await AuditStore(self.path).start()
        self.assertEqual((await self.store.budget_status('2026-09-05'))['used'],7)
        self.assertEqual((await self.store.holdings())['holdings'],[])
