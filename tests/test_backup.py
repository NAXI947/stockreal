import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from stockreal.audit_store import AuditStore
from stockreal.backup import verify_restore

class BackupTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_restart_restore_and_no_overwrite(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);store=await AuditStore(root/'live.db').start()
            try:
                await store.claim_budget('2026-09-05')
                await store.replace_holdings([{'symbol':'000001.SZ','reference_cost':'12.34','observation_level':'测试'}],expected_revision=0)
                path=root/'backup.db';report=await store.backup(path)
                await store.claim_budget('2026-09-05')
                with self.assertRaises(FileExistsError):await store.backup(path)
                restored=verify_restore(path,report['sha256'])
                self.assertTrue(restored['restore_verified']);self.assertEqual(restored['database']['budget']['2026-09-05'],1)
                self.assertEqual(restored['database']['holdings_revision'],1)
                self.assertEqual((await store.budget_status('2026-09-05'))['used'],2)
                self.assertFalse(restored['production_database_overwritten'])
                with path.open('ab') as stream:stream.write(b'tampered')
                with self.assertRaises(ValueError):verify_restore(path,report['sha256'])
            finally:await store.close()
