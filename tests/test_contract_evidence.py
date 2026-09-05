import unittest
from stockreal.contract_evidence import diagnostic_contract,pagination_evidence

class EvidenceTests(unittest.TestCase):
    def contract(self,source=41):
        return {'source_id':source,'query_template':[['Index','0'],['Time','{time_param}'],['DStart','2026-01-01'],['DEnd','2026-01-02']]}
    def page(self,codes,count=2,day=None):
        return {'Count':count,'Day':day or ['2026-09-04'],'list':[[c]+[0]*18 for c in codes]}
    def test_restricted_parameters(self):
        for key in ['StockID','Token','apiv','st','origin']:
            with self.assertRaises(ValueError):diagnostic_contract(self.contract(),{key:'0'})
        for bad in ['-1','1&Token=x','{time_param}','０','99999999999',0]:
            with self.assertRaises(ValueError):diagnostic_contract(self.contract(75),{'Time':bad})
    def test_copy_and_dates(self):
        c=self.contract(75);changed=diagnostic_contract(c,{'Time':'0'})
        self.assertEqual(dict(c['query_template'])['Time'],'{time_param}')
        self.assertEqual(dict(changed['query_template'])['Time'],'0')
        for overrides in [{'DStart':'2026-02-30'},{'DStart':'2026-1-01'},{'DStart':'2027-01-01'}]:
            with self.assertRaises(ValueError):diagnostic_contract(self.contract(81),overrides)
    def test_duplicate_override_rejected(self):
        c=self.contract();c['query_template'].append(['Index','1'])
        with self.assertRaises(ValueError):diagnostic_contract(c,{'Index':'60'})
    def test_complete_coverage_never_means_breadth_or_contract_pass(self):
        result=pagination_evidence([self.page(['a']),self.page(['b'])])
        self.assertTrue(result['observed_coverage_complete']);self.assertFalse(result['breadth_available'])
        self.assertFalse(result['atomic_snapshot_verified']);self.assertFalse(result['production_eligible'])
        self.assertEqual(result['contract_status'],'UNVERIFIED')
    def test_incomplete_duplicate_count_and_day_drift(self):
        self.assertIn('INCOMPLETE_OR_EXCESS_ROWS',pagination_evidence([self.page(['a'])])['flags'])
        self.assertIn('DUPLICATE_CODE',pagination_evidence([self.page(['a']),self.page(['a'])])['flags'])
        self.assertIn('COUNT_CHANGED_OR_MISSING',pagination_evidence([self.page(['a']),self.page(['b'],3)])['flags'])
        self.assertIn('DAY_CHANGED_OR_MISSING',pagination_evidence([self.page(['a']),self.page(['b'],day=['2026-09-03'])])['flags'])
    def test_malformed_empty_and_width_fail_closed(self):
        for pages in [[],[None],[{'Count':True,'list':[]}],[self.page([],0)],[{'Count':1,'Day':['x'],'list':[['a',1]]}]]:
            self.assertFalse(pagination_evidence(pages)['observed_coverage_complete'])
