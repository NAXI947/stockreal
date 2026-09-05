import hashlib
import unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from stockreal.runtime_gate import calendar_status,status
from stockreal.stage0 import request_url

class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'calendar.csv'
        self.today=date(2026,9,5)
    def write(self,text):
        self.path.write_text(text)
        return hashlib.sha256(self.path.read_bytes()).hexdigest()
    def full(self,year=2026):
        d=date(year,1,1);rows=['date,is_open']
        while d<date(year+2,1,1):
            rows.append(d.isoformat()+',0');d+=timedelta(days=1)
        return '\n'.join(rows)+'\n'
    def test_missing(self):self.assertEqual(calendar_status(self.path,None,self.today),'CALENDAR_MISSING')
    def test_unreviewed_and_modified(self):
        digest=self.write(self.full())
        self.assertEqual(calendar_status(self.path,None,self.today),'CALENDAR_UNREVIEWED')
        self.path.write_text(self.full()+'\n')
        self.assertEqual(calendar_status(self.path,digest,self.today),'CALENDAR_UNREVIEWED')
    def test_expired(self):
        digest=self.write(self.full(2024))
        self.assertEqual(calendar_status(self.path,digest,self.today),'CALENDAR_EXPIRED')
    def test_incomplete_next_year(self):
        digest=self.write(self.full().replace('2027-12-31,0\n',''))
        self.assertEqual(calendar_status(self.path,digest,self.today),'CALENDAR_INCOMPLETE')
    def test_duplicate_and_bad_value(self):
        for text in (self.full()+'2026-09-05,0\n',self.full().replace('2026-09-05,0','2026-09-05,yes')):
            digest=self.write(text)
            self.assertEqual(calendar_status(self.path,digest,self.today),'CALENDAR_INVALID')
    def test_reviewed_open_and_closed(self):
        digest=self.write(self.full())
        self.assertEqual(calendar_status(self.path,digest,self.today),'CLOSED_DAY')
        digest=self.write(self.full().replace('2026-09-05,0','2026-09-05,1'))
        self.assertEqual(calendar_status(self.path,digest,self.today),'OPEN_DAY')
    def test_leap_day_required(self):
        digest=self.write(self.full(2028).replace('2028-02-29,0\n',''))
        self.assertEqual(calendar_status(self.path,digest,date(2028,6,1)),'CALENDAR_INCOMPLETE')
    def test_real_policy_keeps_jobs_disabled(self):
        r=status(Path('/workspace'),datetime(2026,9,5,tzinfo=timezone.utc))
        self.assertFalse(r['automatic_collection_enabled'])
        self.assertFalse(r['directional_signals_enabled'])
        self.assertEqual(r['calendar_status'],'CALENDAR_MISSING')
        self.assertIn('TrendScore',r['disabled_phase1_features'])

class RequestTests(unittest.TestCase):
    def contract(self,doc,pairs):
        return {'source_id':doc,'origin':'https://apphq.longhuvip.com/w1/api/index.php','query_template':pairs}
    def test_all_single_stock_endpoints_reject_batch(self):
        bad=['000001,600000','["000001","600000"]','000001|600000','000001;600000','000001.SZ','000001&StockID=600000']
        for doc in (8,9,13,14,75):
            for value in bad:
                with self.subTest(doc=doc,value=value),self.assertRaises(ValueError):
                    request_url(self.contract(doc,[['StockID',value]]),{})
    def test_repeated_array_and_missing_parameter(self):
        for pairs in ([['StockID','000001'],['StockID','600000']],[['StockID[]','000001']],[]):
            with self.assertRaises(ValueError):request_url(self.contract(9,pairs),{})
    def test_single_symbol_keeps_leading_zero(self):
        self.assertIn('StockID=000001',request_url(self.contract(9,[['StockID','000001']]),{}))

if __name__=='__main__':unittest.main()
