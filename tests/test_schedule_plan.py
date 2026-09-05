import unittest
from datetime import datetime,timezone
from pathlib import Path
from stockreal.schedule_plan import propose,current_plan,TZ

class ScheduleTests(unittest.TestCase):
    def plan(self,clock,holdings=('000001.SZ',),calendar='OPEN_DAY'):
        return propose(datetime.fromisoformat('2026-09-07T'+clock+'+08:00'),holdings,calendar_state=calendar)
    def test_missing_unreviewed_closed_calendar_has_no_tasks(self):
        for state in ('CALENDAR_MISSING','CALENDAR_UNREVIEWED','CALENDAR_EXPIRED','CLOSED_DAY'):
            p=self.plan('10:00:00',calendar=state);self.assertEqual(p['tasks'],[]);self.assertFalse(p['automatic_execution'])
    def test_real_policy_stays_disabled(self):
        p=current_plan(Path('/workspace'));self.assertFalse(p['automatic_execution']);self.assertEqual(p['tasks'],[])
    def test_continuous_base_frequencies_only_holdings(self):
        p=self.plan('10:00:00');stock=[t for t in p['tasks'] if t['symbol']]
        self.assertEqual({t['source_id']:t['interval_seconds'] for t in stock},{9:10,13:30,8:60,75:60})
        self.assertTrue(all(t['symbol']=='000001.SZ' for t in stock))
        self.assertFalse(any(t['execute'] for t in p['tasks']))
    def test_lunch_stops_high_frequency(self):
        p=self.plan('11:30:00');self.assertEqual(p['phase'],'LUNCH')
        self.assertFalse(any(t['symbol'] for t in p['tasks']))
    def test_am_pm_use_separate_windows_and_warmup(self):
        am=self.plan('09:30:00');pm=self.plan('13:00:00')
        self.assertNotEqual(am['reset_token'],pm['reset_token'])
        self.assertFalse(am['window_features_ready']);self.assertFalse(pm['window_features_ready'])
        self.assertTrue(self.plan('09:31:00')['window_features_ready']);self.assertTrue(self.plan('13:01:00')['window_features_ready'])
    def test_opening_profile_end(self):
        self.assertTrue(self.plan('09:44:59')['opening_profile']);self.assertFalse(self.plan('09:45:00')['opening_profile'])
    def test_candidate_ttl_exact_boundary(self):
        before=self.plan('14:56:29');after=self.plan('14:56:30')
        self.assertIn(103,[t['source_id'] for t in before['tasks']]);self.assertNotIn(103,[t['source_id'] for t in after['tasks']])
        self.assertEqual(before['candidate_expire_time'],'2026-09-07T14:56:30+08:00')
    def test_candidates_do_not_add_stock_l2_and_no_breadth_fanout(self):
        p=self.plan('14:40:00',holdings=())
        self.assertFalse(any(t['source_id'] in (8,9,13,14,75,46) for t in p['tasks']))
        self.assertEqual(next(t for t in p['tasks'] if t['source_id']==103)['purpose'],'INFO_CANDIDATE')
    def test_auction_snapshot_only_and_quiet_clear(self):
        for clock in ('09:15:00','14:57:00'):
            p=self.plan(clock);self.assertFalse(p['window_features_ready']);self.assertTrue(all(t['purpose']=='SNAPSHOT_ONLY' for t in p['tasks']))
        p=self.plan('09:25:00');self.assertEqual(p['tasks'],[]);self.assertIsNotNone(p['reset_token'])
    def test_postmarket_once_id_stable(self):
        a=self.plan('15:10:00');b=self.plan('16:00:00')
        self.assertEqual(a['tasks'],b['tasks']);self.assertTrue(all(t['once_key'] for t in a['tasks']))
        self.assertEqual(self.plan('17:30:00')['tasks'],[])
    def test_capacity_duplicates_and_noncanonical_rejected(self):
        for holdings in ([f'{i:06d}.SZ' for i in range(21)],['000001.SZ']*2,['AAPL'],['000001']):
            with self.assertRaises(ValueError):self.plan('10:00:00',holdings)
    def test_utc_is_converted_and_naive_rejected(self):
        p=propose(datetime(2026,9,7,1,30,tzinfo=timezone.utc),[],calendar_state='OPEN_DAY')
        self.assertEqual(p['phase'],'AM')
        with self.assertRaises(ValueError):propose(datetime(2026,9,7,10),[],calendar_state='OPEN_DAY')

if __name__=='__main__':unittest.main()
