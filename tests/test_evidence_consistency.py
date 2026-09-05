import unittest
from stockreal.evidence_consistency import trade_consistency,funding_consistency

class ConsistencyTests(unittest.TestCase):
    def test_agreement_does_not_verify_units(self):
        row=['2','1788505200','1687','1059436','6.28','2026-09-04 15:00:00']
        report=trade_consistency([row])
        self.assertEqual(report['timestamp_text_agree'],1)
        self.assertEqual(report['amount_volume_price_ratio_near_100'],1)
        self.assertFalse(report['unit_contract_verified'])
        self.assertFalse(report['production_eligible'])
    def test_bad_time_and_nan_are_not_valid_samples(self):
        rows=[['2','1788505200','1','1','1','wrong'],['2','NaN','1','1','1','x']]
        report=trade_consistency(rows)
        self.assertEqual(report['timestamp_text_agree'],0);self.assertEqual(report['invalid_rows'],1)
    def test_signed_sell_mapping_and_nulls(self):
        row=['x']+[0]*18;row[7]=100;row[8]=-60;row[6]=40
        self.assertEqual(funding_consistency([row],41)['buy_plus_signed_sell_agrees_with_net'],1)
        row[8]=None;self.assertEqual(funding_consistency([row],41)['invalid_rows'],1)
        row[8]=60;self.assertEqual(funding_consistency([row],41)['buy_plus_signed_sell_agrees_with_net'],0)
    def test_unsupported_and_shapes(self):
        with self.assertRaises(ValueError):funding_consistency([],75)
        self.assertEqual(funding_consistency([[]],81)['invalid_rows'],1)
        self.assertEqual(trade_consistency([[]])['invalid_rows'],1)
