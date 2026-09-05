import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from stockreal.response_validation import infer_schema
from stockreal.schema_diff import explain
from stockreal.contract_review import checked_sample
from stockreal.stage0 import request_url

class DifferenceTests(unittest.TestCase):
    def test_positional_null_and_numeric_change(self):
        report=explain({'list':[['x',None,1.5]]},infer_schema({'list':[['x',1,2]]}))
        self.assertEqual([r['path'] for r in report['differences']],['$.list[0][1]','$.list[0][2]'])
        self.assertEqual(report['differences'][0]['observed'],'NoneType')
        self.assertFalse(report['production_eligible'])
    def test_empty_observation_is_not_an_item_contract(self):
        report=explain({'list':[['a',1]]},infer_schema({'list':[]}))
        self.assertEqual(report['differences'][0]['reason'],'ITEM_SHAPE_NOT_OBSERVED')
        self.assertEqual(report['contract_status'],'UNVERIFIED')
    def test_columns_fields_and_bool(self):
        self.assertEqual(explain([['x']],infer_schema([['x',2]]))['differences'][0]['reason'],'COLUMN_COUNT_CHANGED')
        report=explain({'extra':1},infer_schema({'required':0}))
        self.assertEqual({x['reason'] for x in report['differences']},{'MISSING_FIELD','ADDED_FIELD'})
        self.assertFalse(explain(True,infer_schema(1))['observed_match'])
    def test_union_variants_and_no_values(self):
        baseline=infer_schema([['x',0],['y',None]])
        self.assertTrue(explain([['z',None]],baseline)['observed_match'])
        report=explain([['PRIVATE_VALUE','PRIVATE_TOKEN']],baseline)
        self.assertNotIn('PRIVATE',json.dumps(report))
    def test_limit_and_determinism(self):
        a=explain([1,2,3],infer_schema([]),2)
        self.assertEqual(a['difference_count'],3);self.assertTrue(a['truncated'])
        self.assertEqual(a,explain([1,2,3],infer_schema([]),2))
        with self.assertRaises(ValueError):explain([],infer_schema([]),0)
    def test_value_changes_are_not_drift(self):
        self.assertTrue(explain({'x':4.5},infer_schema({'x':1.2}))['observed_match'])
    def test_sample_hash_and_path_boundary(self):
        import hashlib
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data/stage0').mkdir(parents=True);p=root/'data/stage0/x.json';p.write_text('{}')
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(checked_sample(root,'data/stage0/x.json',digest),{})
            with self.assertRaises(ValueError):checked_sample(root,'data/stage0/x.json','bad')
            with self.assertRaises(ValueError):checked_sample(root,'../outside.json','bad')
    def test_named_placeholder_rejected_before_network(self):
        c={'origin':'https://apphq.longhuvip.com/w1/api/index.php','source_id':75,'query_template':[['StockID','300721'],['Time','{time_param}']]}
        with self.assertRaises(ValueError):request_url(c,{})
        c['query_template'][1][1]='0'
        self.assertIn('Time=0',request_url(c,{}))
