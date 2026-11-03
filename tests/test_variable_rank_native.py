from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.search import decode_candidate,encode_candidate,naive_terms
from mmsearch.tensor import strassen_candidate
from scripts.campaign_variable_rank_native import drain_verified,validate_seed

ROOT=Path(__file__).resolve().parents[1]


class VariableRankNativeTests(unittest.TestCase):
    def test_published96_is_exact_seed_and_bad_or_other_rank_is_rejected(self):
        candidate=json.loads((ROOT/'artifacts/alphatensor_5x5_f2_rank96.json').read_text())
        terms,report=validate_seed(candidate)
        self.assertEqual(len(terms),96);self.assertEqual(report['original']['exact_entries_checked'],15625)
        candidate['terms'].pop()
        with self.assertRaises(ValueError):
            validate_seed(candidate)
        with self.assertRaises(ValueError):
            validate_seed(encode_candidate(naive_terms(5),5))

    def test_real_small_native_fast_success_is_drained_and_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.txt';prefix=root/'walk'
            terms=decode_candidate(strassen_candidate(2),2)
            source.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms))
            result=subprocess.run([str(ROOT/'native/flip_worker_cyclic'),'--input',str(source),
                                   '--output',str(prefix),'--n','2','--target','7','--max-rank','10',
                                   '--steps','50','--seconds','.01'],capture_output=True,text=True,timeout=2)
            self.assertEqual(result.returncode,0,result.stderr)
            drained=drain_verified(prefix,root,{},n=2,target=7,input_rank=8,max_rank=10)
            self.assertTrue(drained['winner'])
            report=json.loads((root/'WINNER.verification.json').read_text())
            self.assertTrue(report['valid']);self.assertEqual(report['rank'],7)
            self.assertFalse((root/'WINNER.json').stat().st_mode & 0o222)

    def test_reduction_is_branch_progress_and_per_rank_retention_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'walk';terms=naive_terms(2)
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms))
            result=drain_verified(prefix,root,{},n=2,target=7,input_rank=9,max_rank=12)
            self.assertFalse(result['winner']);self.assertFalse((root/'WINNER.json').exists())
            value=json.loads(next((root/'verified').glob('*.json')).read_text())
            self.assertEqual(value['metadata']['status'],'branch_progress')
            self.assertFalse(value['metadata']['meets_campaign_target'])
            other=root/'capped';other.mkdir()
            counts=Counter({8:32})
            capped=drain_verified(prefix,other,{},n=2,target=7,input_rank=9,max_rank=12,counts=counts)
            self.assertEqual(capped['verified_portfolio_size'],0)

    def test_invalid_final_low_rank_cannot_be_claimed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'walk'
            prefix.with_suffix('.best.txt').write_text('1 1 1\n')
            with self.assertRaises(RuntimeError):
                drain_verified(prefix,root,{},n=2,target=7,input_rank=8,max_rank=10)
            self.assertFalse((root/'WINNER.json').exists())


if __name__=='__main__':
    unittest.main()
