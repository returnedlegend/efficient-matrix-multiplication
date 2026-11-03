import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.search import encode_candidate,naive_terms
from scripts.freeze_campaign_dictionary import freeze_dictionary


class DictionaryFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.candidate=self.root/'baseline.json'
        self.candidate.write_text(json.dumps(encode_candidate(naive_terms(5),5)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_deterministic_union_raw_provenance_and_baseline(self):
        extra=self.root/'extra.json';extra.write_text('[[3,5,7],[3,5,7],[1,1,1]]')
        first=freeze_dictionary(candidates=[self.candidate],extra_dictionary=extra,output_dir=self.root/'one')
        second=freeze_dictionary(candidates=[self.candidate],extra_dictionary=extra,output_dir=self.root/'two')
        self.assertEqual(first['dictionary_sha256'],second['dictionary_sha256'])
        for name in ('dictionary.json','pool.json','checksums.json'):
            self.assertEqual((self.root/'one'/name).read_bytes(),(self.root/'two'/name).read_bytes())
        pool=json.loads((self.root/'one/pool.json').read_text())
        self.assertEqual(pool['sources'][0]['raw_sha256'],hashlib.sha256(self.candidate.read_bytes()).hexdigest())
        self.assertEqual(pool['sources'][0]['exact_entries_checked'],15625)
        self.assertEqual(pool['extra_dictionary']['validated_distinct_columns'],2)
        self.assertIn('no complete-algorithm',pool['extra_dictionary']['policy'])
        dictionary=json.loads((self.root/'one/dictionary.json').read_text())
        self.assertEqual(dictionary,sorted(dictionary))
        self.assertEqual(len(dictionary),len(set(map(tuple,dictionary))))
        self.assertFalse((self.root/'one/pool.json').stat().st_mode & 0o222)
        self.assertTrue(json.loads((self.root/'one/baseline.verification.json').read_text())['valid'])

    def test_immediate_directory_inputs_only_and_reject_bad_certificate(self):
        directory=self.root/'selected';directory.mkdir()
        (directory/'valid.json').write_bytes(self.candidate.read_bytes())
        nested=directory/'nested';nested.mkdir();(nested/'bad.json').write_text('{}')
        result=freeze_dictionary(candidate_dirs=[directory],output_dir=self.root/'good')
        self.assertEqual(result['certificates'],1)
        (directory/'bad.json').write_text('{}')
        with self.assertRaises(ValueError):
            freeze_dictionary(candidate_dirs=[directory],output_dir=self.root/'bad-output')
        self.assertFalse((self.root/'bad-output').exists())

    def test_reject_missing_baseline_extra_corruption_and_inexact_tensor(self):
        with self.assertRaises(ValueError):
            freeze_dictionary(output_dir=self.root/'empty')
        for index,triple in enumerate(([0,1,1],[True,1,1],[1.0,1,1],[1<<25,1,1],[1,1])):
            extra=self.root/f'extra-{index}.json';extra.write_text(json.dumps([triple]))
            with self.subTest(triple=triple),self.assertRaises(ValueError):
                freeze_dictionary(candidates=[self.candidate],extra_dictionary=extra,output_dir=self.root/f'out-{index}')
        value=json.loads(self.candidate.read_text());value['terms'].pop()
        bad=self.root/'inexact.json';bad.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'exhaustive'):
            freeze_dictionary(candidates=[bad],output_dir=self.root/'inexact-output')

    def test_duplicate_and_zero_terms_canonicalize_without_padding_rank(self):
        value=json.loads(self.candidate.read_text())
        value['terms'] += [copy.deepcopy(value['terms'][0])]*2
        value['terms'].append(dict(u=[0]*25,v=[1]*25,w=[1]*25))
        self.candidate.write_text(json.dumps(value))
        result=freeze_dictionary(candidates=[self.candidate],output_dir=self.root/'canonical')
        self.assertEqual(result['baseline_rank'],125)
        self.assertEqual(result['dictionary_size'],125)
        with self.assertRaises(ValueError):
            freeze_dictionary(candidates=[self.candidate],output_dir=self.root/'canonical')

    def test_minimum_rank_verified_source_is_baseline_and_inputs_remain_distinct(self):
        km=Path(__file__).resolve().parents[1]/'artifacts/km93_f2.json'
        result=freeze_dictionary(candidates=[self.candidate,km],output_dir=self.root/'mixed')
        self.assertEqual(result['baseline_rank'],93)
        self.assertEqual(result['certificates'],2)
        self.assertEqual(result['distinct_algorithms'],2)
        pool=json.loads((self.root/'mixed/pool.json').read_text())
        self.assertEqual(pool['baseline']['source_path'],str(km.resolve()))
        self.assertTrue((self.root/'mixed/code/scripts/freeze_campaign_dictionary.py').exists())


if __name__=='__main__':
    unittest.main()
