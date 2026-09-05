import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from stockreal.audit_store import AuditStore
from stockreal.dashboard import snapshot

class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_projection_does_not_expose_credentials_or_invent_market_data(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            for d in ['config','contracts','docs/stage0']:(root/d).mkdir(parents=True,exist_ok=True)
            (root/'config/runtime-policy.json').write_text(json.dumps({'calendar_reviewed_sha256':None,'disabled_phase1_features':[]}))
            (root/'contracts/endpoints.json').write_text(json.dumps([{'contract_status':'UNVERIFIED','origin':'SENSITIVE_URL','query_template':[['Token','SENSITIVE_TOKEN']]}]))
            (root/'docs/stage0/field-evidence.json').write_text(json.dumps({'results':[{'endpoint_code':'DOC-041','sample_path':'PRIVATE_PATH','raw':'PRIVATE_DATA'}]}))
            store=await AuditStore(root/'db').start()
            try:
                report=await snapshot(root,store);encoded=json.dumps(report)
                for value in ['SENSITIVE_URL','SENSITIVE_TOKEN','PRIVATE_PATH','PRIVATE_DATA']:self.assertNotIn(value,encoded)
                self.assertFalse(report['automatic_execution']);self.assertFalse(report['production_eligible'])
                self.assertEqual(report['gate']['calendar_status'],'CALENDAR_MISSING')
                self.assertTrue(all(v is None for v in report['metrics'].values()))
                self.assertEqual(report['holdings']['holdings'],[]);self.assertEqual(report['signals'],[])
            finally:await store.close()
