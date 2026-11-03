"""Cross-check packed audit against the frozen independent scalar evaluator."""
import copy,json,unittest
from pathlib import Path
from scripts.audit_burst_long42 import exact_check
from scripts.verify_record42_independent import verify_bytes

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/fixtures'

class PackedAuditControls(unittest.TestCase):
    def source(self):
        p=FIXTURES/'native_campaign42_rank93.json'
        return json.loads(p.read_bytes())
    def compare(self,candidate):
        raw=json.dumps(candidate).encode();terms,packed=exact_check(raw);scalar=verify_bytes(raw)
        for key in ['valid','record_eligible','essential_rank','mismatch_count','exact_entries_checked','basis_input_pairs_checked','observed_one_bits','expected_one_bits','zero_input_products','duplicate_products_cancelled']:
            self.assertEqual(packed[key],scalar[key],key)
        return packed
    def test_valid_and_corrupt_tensor_controls(self):
        source=self.source();self.assertTrue(self.compare(source)['valid'])
        corrupt=copy.deepcopy(source);corrupt['terms'][0]['u'][0]^=1;self.assertFalse(self.compare(corrupt)['valid'])
        transpose=copy.deepcopy(source)
        for term in transpose['terms']:term['w']=[term['w'][j*5+i] for i in range(5) for j in range(5)]
        self.assertFalse(self.compare(transpose)['valid'])
        zero=copy.deepcopy(source);zero['terms']=[{'u':[0]*25,'v':[0]*25,'w':[0]*25}]
        self.assertFalse(self.compare(zero)['valid'])
        empty=copy.deepcopy(source);empty['terms']=[];self.assertFalse(self.compare(empty)['valid'])
    def test_parity_zero_removal_and_false_record(self):
        source=self.source();duplicate=copy.deepcopy(source)
        duplicate['terms']+=copy.deepcopy(source['terms'][:1])*2
        duplicate['terms'].append({'u':[0]*25,'v':[1]*25,'w':[1]*25})
        report=self.compare(duplicate);self.assertTrue(report['valid']);self.assertEqual(report['essential_rank'],93)
        false=copy.deepcopy(source);false['terms']=false['terms'][:92];self.assertFalse(self.compare(false)['record_eligible'])
    def test_strict_types_fields_and_duplicate_json_keys(self):
        for kind in ['bool','float','ring','dimension','short','nonbinary']:
            candidate=self.source()
            if kind=='bool':candidate['terms'][0]['u'][0]=True
            if kind=='float':candidate['terms'][0]['u'][0]=1.0
            if kind=='ring':candidate['field']=3
            if kind=='dimension':candidate['dimension']=2
            if kind=='short':candidate['terms'][0]['u'].pop()
            if kind=='nonbinary':candidate['terms'][0]['u'][0]=2
            raw=json.dumps(candidate).encode()
            with self.subTest(kind=kind),self.assertRaises(ValueError):exact_check(raw)
            self.assertFalse(verify_bytes(raw)['valid'])
        raw=json.dumps(self.source()).replace('"field": 2','"field": 2, "field": 2').encode()
        with self.assertRaises(ValueError):exact_check(raw)
        self.assertFalse(verify_bytes(raw)['valid'])
    def test_exported_higher_rank_snapshot(self):
        p=FIXTURES/'native_campaign42_rank96.json'
        report=self.compare(json.loads(p.read_bytes()));self.assertTrue(report['valid']);self.assertGreater(report['essential_rank'],93)

if __name__=='__main__':unittest.main()
