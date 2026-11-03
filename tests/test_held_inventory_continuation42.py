import hashlib
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.search import _rotations,encode_candidate,naive_terms
from mmsearch.verify import verify_candidate
from scripts.campaign_held_inventory_continuation42 import (DEFAULT_BINARY,EXPECTED_BINARY_SHA256,inspect_export,
                                        split_source,rejoin_verified,choose_parent,prune_frontier,load_parent,save_checkpoint)
from tests.test_native_fixed_cubes import inflated_naive

ROOT=Path(__file__).resolve().parents[1]


class HeldInventoryContinuation42Tests(unittest.TestCase):
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
        source=encode_candidate(naive_terms(5),5)
        held,residual,report=split_source(source)
        self.assertEqual((len(held),len(residual)),(5,120))
        self.assertEqual(report['canonical']['exact_entries_checked'],15625)
        self.assertFalse(verify_candidate(encode_candidate(residual,5),random_trials=0)['valid'])
        with self.assertRaises(ValueError):
            split_source(dict(source,field=0))
        with self.assertRaises(ValueError):
            split_source(json.loads((ROOT/'artifacts/km93_f2.json').read_text()))
        with self.assertRaises(ValueError):
            split_source(encode_candidate(inflated_naive(),2))

    def test_five_cube_zero_step_exports_full125_and_preserves_raw120(self):
        held,residual,_=split_source(encode_candidate(naive_terms(5),5))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'residual.txt';prefix=root/'residual_walk'
            source.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(residual)))
            result=subprocess.run([str(DEFAULT_BINARY),'--input',str(source),'--output',str(prefix),
                                   '--n','5','--target','87','--max-rank','126','--seed','421205',
                                   '--steps','0','--seconds','0','--archive-size','16',
                                   '--cyclic','--fixed-cubes','0','--allow-arbitrary'],
                                  capture_output=True,text=True,timeout=2)
            self.assertEqual(result.returncode,0,result.stderr)
            raw=prefix.with_suffix('.stats.json').read_bytes()
            exported=inspect_export(prefix,root,{'native_seed':421205},held,max_residual_rank=126,final=True)
            stats=exported['adjusted_stats']
            self.assertEqual((stats['best_rank'],stats['raw_residual_best_rank']),(125,120))
            self.assertEqual((stats['target_rank'],stats['raw_residual_target_rank']),(92,87))
            self.assertEqual((stats['max_rank'],stats['raw_residual_max_rank']),(131,126))
            self.assertEqual(stats['history'][0]['rank'],125)
            self.assertEqual(stats['held_cube_count'],5)
            self.assertFalse(exported['winner'])
            self.assertEqual(prefix.with_suffix('.stats.json').read_bytes(),raw)
            pointer=json.loads((root/'best_verified.json').read_text())
            self.assertEqual(pointer['rank'],125)
            self.assertTrue(verify_candidate(json.loads(Path(pointer['path']).read_text()),random_trials=0)['valid'])
            self.assertFalse((root/'WINNER.json').exists())

    def test_changed_held_inventory_or_out_of_range_masks_fail(self):
        held,residual,_=split_source(encode_candidate(naive_terms(2),2),strict_n5=False)
        bad_held=set(held);bad_held.remove((1,1,1));bad_held.add((2,2,2))
        with self.assertRaisesRegex(RuntimeError,'full matrix tensor'):
            rejoin_verified(residual,bad_held,n=2)
        with self.assertRaisesRegex(ValueError,'dimension range'):
            rejoin_verified(residual,{(16,16,16)},n=2)

    def test_fake_residual87_cannot_become_global92_winner(self):
        held,residual,_=split_source(encode_candidate(naive_terms(5),5))
        bad=set(residual)
        for _ in range(11):bad.difference_update(_rotations(min(bad)))
        self.assertEqual(len(bad),87)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'residual_walk'
            raw=dict(dimension=5,exact=False,tensor_invariant_checked=True,cyclic=True,
                     required_fixed_cubes=0,best_fixed_cubes=0,current_fixed_cubes=0,
                     max_rank=126,target_rank=87,best_rank=87,current_rank=87)
            prefix.with_suffix('.stats.json').write_text(json.dumps(raw))
            for label in ['best','current']:
                prefix.with_suffix('.'+label+'.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(bad)))
            with self.assertRaisesRegex(RuntimeError,'full matrix tensor'):
                inspect_export(prefix,root,{},held,max_residual_rank=126,final=True)
            self.assertFalse((root/'WINNER.json').exists())
            self.assertFalse((root/'best_verified.json').exists())
            self.assertFalse((root/'walk.stats.json').exists())

    def fixture113(self):
        path=ROOT/'tests/fixtures/held_inventory42_rank113.txt'
        terms=[tuple(map(int,line.split())) for line in path.read_text().splitlines()]
        return encode_candidate(terms,5)

    def test_variable_rank113_and_duplicate_term_parity_normalization(self):
        candidate=self.fixture113();held,residual,report=split_source(candidate)
        self.assertEqual((len(held),len(residual)),(5,108))
        self.assertEqual(report['canonical']['exact_entries_checked'],15625)
        duplicate=copy.deepcopy(candidate)
        duplicate['terms'].extend([copy.deepcopy(candidate['terms'][0]) for _ in range(2)])
        h2,r2,rep2=split_source(duplicate)
        self.assertEqual((h2,r2),(held,residual));self.assertTrue(rep2['original']['valid'])
        for value in [3,True]:
            corrupt=copy.deepcopy(candidate);corrupt['terms'][0]['u'][0]=value
            with self.assertRaises(ValueError):split_source(corrupt)

    def test_frontier_prefers_progress_and_checkpoint_preserves_sources_and_counts(self):
        from scripts.freeze_campaign_dictionary import read_json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old.json';new=root/'new.json'
            old.write_text(json.dumps(encode_candidate(naive_terms(5),5)))
            new.write_text(json.dumps(self.fixture113()))
            a=load_parent(old,root);b=load_parent(new,root)
            frontier={a['term_set_sha256']:a,b['term_set_sha256']:b}
            uses={b['term_set_sha256']:2}
            self.assertEqual(choose_parent(frontier,uses,0)['term_set_sha256'],b['term_set_sha256'])
            prune_frontier(frontier)
            self.assertEqual(list(frontier),[b['term_set_sha256']])
            save_checkpoint(root,frontier,uses,1234,7,b['held'])
            checkpoint=read_json((root/'checkpoint.json').read_bytes())
            self.assertEqual(checkpoint['completed_phase_count'],7)
            self.assertEqual(checkpoint['selection_counts'],uses)
            restored=load_parent(checkpoint['frontier'][0]['full_source_snapshot'],root)
            self.assertEqual(restored['term_set_sha256'],b['term_set_sha256'])
            self.assertEqual(restored['source_sha256'],checkpoint['frontier'][0]['source_sha256'])
            with self.assertRaises(ValueError):read_json(b'{"field":2,"field":0}')

    def test_cli_zero_step_resume_uses_verified113_not_naive125(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.json';source.write_text(json.dumps(self.fixture113()))
            first=root/'first';second=root/'second'
            base=['python3',str(ROOT/'scripts/campaign_held_inventory_continuation42.py'),
                  '--seconds','4','--phase-seconds','1','--phase-limit','1','--step-limit','0']
            run=subprocess.run([*base,'--input',str(source),'--output-dir',str(first),'--seed','1234'],
                               capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertEqual(run.returncode,0,run.stderr)
            cp=json.loads((first/'checkpoint.json').read_text())
            self.assertEqual(cp['completed_phase_count'],1)
            run=subprocess.run([*base,'--resume',str(first/'checkpoint.json'),'--output-dir',str(second),
                                '--headroom','12'],capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertEqual(run.returncode,0,run.stderr)
            meta=json.loads((second/'phase-000/manifest.json').read_text())
            self.assertEqual(meta['initial_global_rank'],113)
            self.assertEqual(meta['initial_residual_rank'],108)
            self.assertEqual(meta['global_phase'],1)
            self.assertEqual(meta['native_seed'],2243)
            self.assertEqual(meta['max_residual_rank'],120)
            stats=json.loads((second/'phase-000/walk.stats.json').read_text())
            self.assertEqual(stats['best_rank'],113);self.assertEqual(stats['steps'],0)
            self.assertEqual(json.loads((second/'checkpoint.json').read_text())['completed_phase_count'],2)
            cp['frontier'][0]['source_sha256']='0'*64
            corrupt=root/'bad.json';corrupt.write_text(json.dumps(cp))
            bad=subprocess.run([*base,'--resume',str(corrupt),'--output-dir',str(root/'bad')],
                               capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertNotEqual(bad.returncode,0)
            self.assertIn('source hash mismatch',bad.stderr)


if __name__=='__main__':
    unittest.main()
