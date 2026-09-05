import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from stockreal.response_validation import infer_schema,assess
from stockreal.replay import replay
from stockreal.stage0 import probe,intake

class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.payload={'errcode':'0','List':[['2',1720000000,100,200.5,2.0,'10:00:00'],['1',1720000001,100,200.5,2.0,'10:00:01']]}
        self.schema=infer_schema(self.payload)
    def test_success_not_contract_pass(self):
        r=assess(13,self.payload,schema=self.schema)
        self.assertEqual(r['schema_status'],'OBSERVED_MATCH')
        self.assertEqual(r['contract_status'],'UNVERIFIED')
        self.assertFalse(r['production_eligible'])
    def test_200_business_failure(self):
        self.payload['errcode']='1017'
        self.assertIn('UPSTREAM_BUSINESS_ERROR',assess(13,self.payload,schema=self.schema)['quality_flags'])
    def test_stock_code_not_error_code(self):
        r=assess(9,{'errcode':'0','code':'000001','status':86,'real':{'last_px':1}})
        self.assertEqual(r['business_status'],'CODE_SUCCESS')
    def test_flash_code_is_separate(self):
        self.assertEqual(assess(36,{'code':20000,'data':[{'timestamp':1}]})['business_status'],'CODE_SUCCESS')
        self.assertIn('UPSTREAM_BUSINESS_ERROR',assess(36,{'code':0,'data':[]})['quality_flags'])
    def test_empty_is_not_successful_data(self):
        self.payload['List']=[]
        r=assess(13,self.payload,schema=self.schema)
        self.assertEqual(r['data_status'],'EMPTY')
        self.assertIn('EMPTY_DATA',r['quality_flags'])
    def test_every_row_is_checked(self):
        for change in ('add','remove','type'):
            p=copy.deepcopy(self.payload)
            if change=='add': p['List'][1].append(99)
            if change=='remove': p['List'][1].pop()
            if change=='type': p['List'][1][2]='100'
            self.assertEqual(assess(13,p,schema=self.schema)['schema_status'],'DRIFT')
    def test_missing_and_added_named_fields(self):
        for p in ({'errcode':'0'},{**self.payload,'new_field':1}):
            self.assertEqual(assess(13,p,schema=self.schema)['schema_status'],'DRIFT')
    def test_new_values_are_not_schema_drift(self):
        self.payload['List'][0][2]=999
        self.assertEqual(assess(13,self.payload,schema=self.schema)['schema_status'],'OBSERVED_MATCH')
    def test_bool_is_not_integer(self):
        self.payload['List'][0][2]=True
        self.assertEqual(assess(13,self.payload,schema=self.schema)['schema_status'],'DRIFT')
    def test_empty_baseline_cannot_validate_new_rows(self):
        schema=infer_schema({'errcode':'0','List':[]})
        self.assertEqual(assess(13,self.payload,schema=schema)['schema_status'],'DRIFT')
    def test_invalid_envelope_http_and_missing_code(self):
        self.assertIn('INVALID_ENVELOPE',assess(13,[])['quality_flags'])
        self.assertIn('HTTP_ERROR',assess(13,self.payload,429)['quality_flags'])
        self.assertIn('UPSTREAM_BUSINESS_ERROR',assess(13,{'List':[]})['quality_flags'])
    def test_quote_levels_positional(self):
        p={'errcode':'0','real':{'price':1},'weituo':{'b1':[1.0,100]}}
        schema=infer_schema(p)
        p['weituo']['b1'].append(1)
        self.assertEqual(assess(9,p,schema=schema)['schema_status'],'DRIFT')
    def test_probe_integrates_business_gate(self):
        c={'endpoint_code':'LHV-DOC-013','source_id':13,'origin':'https://apphq.longhuvip.com/w1/api/index.php','query_template':[['StockID','000001']]}
        with TemporaryDirectory() as tmp,patch('stockreal.stage0.build_opener') as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.status=200
            response.read.return_value=b'{"errcode":"1017","List":[]}'
            r=probe(c,{},tmp)
        self.assertEqual(r['transport_status'],'JSON_RECEIVED')
        self.assertEqual(r['business_status'],'CODE_ERROR_OR_MISSING')
        self.assertFalse(r['production_eligible'])
    def test_pinned_replay_is_deterministic_and_offline(self):
        root=Path('/workspace')
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network forbidden')):
            a=replay(root);b=replay(root)
        self.assertEqual(a,b)
        self.assertEqual(len(a['results']),11)
        self.assertTrue(all(not r['production_eligible'] for r in a['results']))
    def test_modified_archive_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'contracts').mkdir()
            (root/'sample.json').write_text('{}')
            (root/'contracts/sample-index.json').write_text(json.dumps({'samples':[{'endpoint_code':'test','path':'sample.json','sha256':'wrong'}]}))
            result=replay(root)['results'][0]
        self.assertEqual(result['integrity_status'],'SAMPLE_HASH_MISMATCH')

if __name__=='__main__':unittest.main()
