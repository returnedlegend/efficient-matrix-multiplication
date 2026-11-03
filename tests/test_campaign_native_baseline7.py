"""Tiny positive, early return and strict late/independent publication gates."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from mmsearch.search import encode_candidate,decode_candidate,naive_terms
from mmsearch.tensor import strassen_candidate
from scripts import campaign_native_baseline7 as b
ROOT=Path(__file__).resolve().parents[1]
BINARY=Path(os.environ.get('BASELINE7_TEST_BINARY',ROOT/'artifacts/rl_campaign42_20261103T033116Z/plus-burst42-pilot-ready-v1/native/plus-burst-worker'))

class BaselineTests(unittest.TestCase):
    def test_command_is_exact_unrestricted_default_arm(self):
        argv=b.command('worker','input','walk')
        for key,want in {'--seconds':'300','--seed':'20261103132901','--max-rank':'105','--plus-burst':'1','--reduction-dwell':'0','--archive-size':'16','--plus-every':'20000','--restart-every':'50000000'}.items():self.assertEqual(argv[argv.index(key)+1],want)
        self.assertNotIn('--cyclic',argv)
        with self.assertRaises(ValueError):b.command('w','i','o',seconds=301)

    def test_tiny_positive_and_early_child_return_are_drained(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);summary=b.execute(BINARY,naive_terms(2),out,lambda *_:True,seconds=2,seed=3,n=2,target=7,steps=200000)
            self.assertEqual(summary['execution']['exit_code'],0);self.assertEqual(summary['stats']['best_rank'],7)
            self.assertTrue(summary['eligible_target_emitted']);self.assertTrue(list((out/'records').glob('*.json')))
            self.assertEqual(summary['final_full_checks']['best']['independent']['exact_entries_checked'],64)
            self.assertFalse((out/'WINNER.json').exists())

    def test_late_positive_retains_hidden_raw_without_eligible_candidate(self):
        good=encode_candidate(decode_candidate(strassen_candidate(2),2),2)
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fresh(name):calls.append(name);return name!='post_target_strict_independent'
            self.assertFalse(b.retain_target(tmp,good,fresh,target=7));self.assertTrue(list((Path(tmp)/'.raw-native-returns').glob('*.candidate.raw')));self.assertFalse((Path(tmp)/'records').exists())
            self.assertIn('post_target_strict_independent',calls)

    def test_false_n5_even_if_primary_passes_never_hands_off(self):
        bad=encode_candidate([(1,1,1)],5)
        with tempfile.TemporaryDirectory() as tmp,mock.patch.object(b,'verify_candidate',return_value={'valid':True,'exact_entries_checked':15625}):
            with self.assertRaises(ValueError):b.retain_target(tmp,bad,lambda *_:True)
            self.assertFalse((Path(tmp)/'records').exists());self.assertTrue(list((Path(tmp)/'.raw-native-returns').glob('*.candidate.raw')))

if __name__=='__main__':unittest.main()
