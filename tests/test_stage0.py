import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from stockreal.stage0 import intake, request_url, scrub, shape, probe

class Stage0Tests(unittest.TestCase):
    def setUp(self):
        self.url = 'https://apphq.longhuvip.com/w1/api/index.php?a=Data&c=Test&apiv=route&Token=<TOKEN>&UserID=<USER_ID>&st=20&StockID=000001'
        self.catalog = [{'id': 13, 'api_url': self.url}]
        self.creds = {'13': {'full_url': self.url.replace('<TOKEN>', 'demo-secret-abc').replace('<USER_ID>', '123456'),
                             'credentials': {'Token': 'demo-secret-abc', 'UserID': '123456'}}}
    def test_split_and_binding(self):
        contracts, profiles = intake(self.catalog, self.creds)
        self.assertNotIn('demo-secret-abc', str(contracts))
        self.assertEqual(contracts[0]['route_key'], 'route')
        self.assertFalse(contracts[0]['supports_batch'])
        self.assertEqual(contracts[0]['contract_status'], 'UNVERIFIED')
        self.assertIn('st=100', request_url(contracts[0], profiles['LHV-DOC-013']))
    def test_reject_profile_cross_binding(self):
        self.creds['13']['full_url'] = self.creds['13']['full_url'].replace('apiv=route', 'apiv=other')
        with self.assertRaises(ValueError): intake(self.catalog, self.creds)
    def test_missing_credential(self):
        contracts, _ = intake(self.catalog, {})
        with self.assertRaises(ValueError): request_url(contracts[0], {})
    def test_host_allowlist(self):
        contracts, _ = intake(self.catalog, self.creds)
        for origin in ['http://apphq.longhuvip.com/api', 'https://evil.example/api', 'https://apphq.longhuvip.com:444/api']:
            contracts[0]['origin'] = origin
            with self.assertRaises(ValueError): request_url(contracts[0], {'Token':'demo', 'UserID':'123'})
    def test_redact_nested_echoes(self):
        cleaned = str(scrub({'Token':'secret', 'data':['demo-secret-abc', {'url':'https://x/?UserID=123&Token=abc&x=1'}]}, ('demo-secret-abc',)))
        for secret in ('demo-secret-abc', 'Token=abc', 'UserID=123'): self.assertNotIn(secret, cleaned)
    def test_reject_duplicate(self):
        with self.assertRaises(ValueError): intake(self.catalog*2, self.creds)
    def test_shape_keeps_all_row_lengths(self):
        self.assertEqual(shape([[1,2], [1,2,3]])['row_lengths'], [2,3])
    def test_http_failure_never_passes(self):
        contracts, profiles = intake(self.catalog, self.creds)
        with TemporaryDirectory() as tmp, patch('stockreal.stage0.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('https://secret', 429, 'secret', {}, None)
            result = probe(contracts[0], profiles['LHV-DOC-013'], tmp)
        self.assertEqual(result['http_status'], 429)
        self.assertEqual(result['contract_status'], 'UNVERIFIED')
        self.assertNotIn('secret', str(result))

if __name__ == '__main__': unittest.main()
