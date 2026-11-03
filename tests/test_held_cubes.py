import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.search import _rotations,encode_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_held_cubes import (DEFAULT_BINARY,EXPECTED_BINARY_SHA256,inspect_export,
                                        split_source)
from tests.test_native_fixed_cubes import inflated_naive

ROOT=Path(__file__).resolve().parents[1]


class HeldCubeTests(unittest.TestCase):
    def worker_control(self,root):
        held,residual,report=split_source(encode_candidate(inflated_naive(),2),strict_n5=False)
        self.assertEqual((len(held),len(residual)),(2,9))
        source=root/'residual.txt';prefix=root/'residual_walk'
        source.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(residual)))
        result=subprocess.run([str(DEFAULT_BINARY),'--input',str(source),'--output',str(prefix),
                               '--n','2','--target','6','--max-rank','15','--seed','19','--steps','100',
                               '--seconds','.1','--archive-size','8','--archive-every','1',
                               '--cyclic','--fixed-cubes','0','--allow-arbitrary'],
                              capture_output=True,text=True,timeout=2)
        self.assertEqual(result.returncode,0,result.stderr)
        return held,prefix

    def test_positive_control_full11_to8_and_raw_stats_never_become_global_ranks(self):
        self.assertEqual(hashlib.sha256(DEFAULT_BINARY.read_bytes()).hexdigest(),EXPECTED_BINARY_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);held,prefix=self.worker_control(root)
            raw_before=prefix.with_suffix('.stats.json').read_bytes()
            raw=json.loads(raw_before);self.assertFalse(raw['exact']);self.assertEqual(raw['best_rank'],6)
            result=inspect_export(prefix,root,{'native_seed':19},held,n=2,target=8,max_residual_rank=15,final=True)
            self.assertTrue(result['winner'])
            global_stats=json.loads((root/'walk.stats.json').read_text())
            self.assertEqual(global_stats['best_rank'],8)
            self.assertEqual(global_stats['target_rank'],8)
            self.assertTrue(global_stats['exact']);self.assertTrue(global_stats['independent_full_verification'])
            self.assertEqual(global_stats['raw_residual_best_rank'],6)
            self.assertEqual(global_stats['history'][0]['rank'],11)
            self.assertEqual(prefix.with_suffix('.stats.json').read_bytes(),raw_before)
            self.assertEqual(len((root/'walk.best.txt').read_text().splitlines()),8)
            for path in (root/'verified').glob('*.json'):
                self.assertTrue(verify_candidate(json.loads(path.read_text()),random_trials=0)['valid'])
            self.assertTrue(json.loads((root/'WINNER.verification.json').read_text())['valid'])

    def test_corrupt_complete_orbit_rank_drop_is_rejected_by_full_tensor_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);held,prefix=self.worker_control(root)
            terms=[tuple(map(int,line.split())) for line in prefix.with_suffix('.best.txt').read_text().splitlines()]
            remove=set(_rotations(terms[0]));bad=[term for term in terms if term not in remove]
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in bad))
            with self.assertRaisesRegex(RuntimeError,'full matrix tensor'):
                inspect_export(prefix,root,{},held,n=2,target=8,max_residual_rank=15,final=True)
            self.assertFalse((root/'WINNER.json').exists())

    def test_main_source_split_is_global_exact_but_residual_is_not_a_matrix_algorithm(self):
        source=json.loads((ROOT/'artifacts/km93_f2.json').read_text())
        held,residual,report=split_source(source)
        self.assertEqual((len(held),len(residual)),(3,90))
        self.assertEqual(report['canonical']['exact_entries_checked'],15625)
        self.assertFalse(verify_candidate(encode_candidate(residual,5),random_trials=0)['valid'])
        with self.assertRaises(ValueError):
            split_source(encode_candidate(inflated_naive(),2))


if __name__=='__main__':
    unittest.main()
