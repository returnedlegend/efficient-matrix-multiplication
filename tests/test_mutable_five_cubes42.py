import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.cube_polarization import conjugate_terms
from mmsearch.native_bridge import canonical_terms
from mmsearch.search import encode_candidate,naive_terms,_rotations
from mmsearch.verify import verify_candidate
from scripts.campaign_mutable_five_cubes42 import (DEFAULT_BINARY,EXPECTED_BINARY_SHA256,
            split_source,inspect_export,load_parent,choose_parent,prune_frontier)
from scripts.freeze_campaign_dictionary import read_json
from tests.test_native_fixed_cubes import inflated_naive

ROOT=Path(__file__).resolve().parents[1]


class MutableFiveCubeTests(unittest.TestCase):
    def source113(self):
        fixture=ROOT/'tests/fixtures/held_inventory42_rank113.txt'
        return encode_candidate([tuple(map(int,line.split())) for line in fixture.read_text().splitlines()],5)

    def native(self,root,terms,n,target,maximum,fixed,steps=0):
        source=root/'input.txt';prefix=root/'native_walk'
        source.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(terms)))
        command=[str(DEFAULT_BINARY),'--input',str(source),'--output',str(prefix),'--n',str(n),
                 '--target',str(target),'--max-rank',str(maximum),'--seed','19','--steps',str(steps),
                 '--seconds','.1','--cyclic','--fixed-cubes',str(fixed),'--archive-size','8','--archive-every','1']
        done=subprocess.run(command,capture_output=True,text=True,timeout=2)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertNotIn('--allow-arbitrary',command)
        return prefix

    def test_accepts_non_singleton_five_cube_factors_and_rejects_wrong_counts(self):
        original=canonical_terms(self.source113());conjugate=conjugate_terms(original,5,0,1)
        cubes,noncubes,report=split_source(encode_candidate(conjugate,5))
        self.assertEqual(len(cubes),5);self.assertEqual(len(cubes)+len(noncubes),113)
        self.assertNotEqual(cubes,{(1<<(i*5+i),)*3 for i in range(5)})
        self.assertEqual(report['canonical']['exact_entries_checked'],15625)
        with self.assertRaises(ValueError):split_source(json.loads((ROOT/'artifacts/km93_f2.json').read_text()))
        with self.assertRaises(ValueError):split_source(dict(self.source113(),field=0))
        for value in [3,True]:
            bad=copy.deepcopy(self.source113());bad['terms'][0]['u'][0]=value
            with self.assertRaises(ValueError):split_source(bad)
        with self.assertRaises(ValueError):read_json(b'{"field":2,"field":0}')

    def test_full_native_zero_step_nontrivial_five_cubes_and_independent_export(self):
        self.assertEqual(hashlib.sha256(DEFAULT_BINARY.read_bytes()).hexdigest(),EXPECTED_BINARY_SHA256)
        terms=conjugate_terms(canonical_terms(self.source113()),5,0,1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=self.native(root,terms,5,92,119,5)
            before=prefix.with_suffix('.stats.json').read_bytes()
            result=inspect_export(prefix,root,{'native_seed':19},max_rank=119,final=True)
            self.assertFalse(result['winner'])
            stats=result['adjusted_stats'];self.assertEqual(stats['best_rank'],113)
            self.assertEqual(stats['target_rank'],92);self.assertTrue(stats['cube_values_mutable'])
            self.assertTrue(stats['global_best_verification']['valid'])
            self.assertEqual(prefix.with_suffix('.stats.json').read_bytes(),before)
            self.assertEqual(len((root/'walk.best.txt').read_text().splitlines()),113)

    def test_generic_two_cube_positive_control_and_corrupt_orbit_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=self.native(root,inflated_naive(),2,8,20,2,steps=100)
            result=inspect_export(prefix,root,{},n=2,target=8,max_rank=20,fixed_cubes=2,final=True)
            self.assertTrue(result['winner']);self.assertEqual(result['adjusted_stats']['best_rank'],8)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=self.native(root,naive_terms(5),5,92,131,5)
            terms=[tuple(map(int,line.split())) for line in prefix.with_suffix('.best.txt').read_text().splitlines()]
            remove=set(_rotations(next(t for t in terms if len(set(t))>1)))
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms if (a,b,c) not in remove))
            with self.assertRaisesRegex(RuntimeError,'independent matrix tensor'):
                inspect_export(prefix,root,{},max_rank=131,final=True)
            self.assertFalse((root/'WINNER.json').exists());self.assertFalse((root/'walk.stats.json').exists())

    def test_zero_step_cli_resume_allows_distinct_cube_profiles_in_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pool=root/'pool';pool.mkdir()
            source=pool/'original.json';source.write_text(json.dumps(self.source113()))
            moved=pool/'conjugated.json';moved.write_text(json.dumps(encode_candidate(
                    conjugate_terms(canonical_terms(self.source113()),5,0,1),5)))
            base=['python3',str(ROOT/'scripts/campaign_mutable_five_cubes42.py'),'--seconds','4',
                  '--phase-seconds','1','--step-limit','0','--phase-limit','1']
            first=root/'first';second=root/'second'
            done=subprocess.run([*base,'--input',str(source),'--pool',str(pool),'--output-dir',str(first),'--seed','5678'],
                                capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertEqual(done.returncode,0,done.stderr)
            checkpoint=json.loads((first/'checkpoint.json').read_text());self.assertEqual(len(checkpoint['frontier']),2)
            done=subprocess.run([*base,'--resume',str(first/'checkpoint.json'),'--output-dir',str(second),'--headroom','12'],
                                capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertEqual(done.returncode,0,done.stderr)
            meta=json.loads((second/'phase-000/manifest.json').read_text())
            self.assertEqual(meta['initial_global_rank'],113);self.assertEqual(meta['max_rank'],125)
            self.assertNotIn('--allow-arbitrary',meta['command'])
            self.assertEqual(meta['global_phase'],1)
            self.assertEqual(json.loads((second/'phase-000/walk.stats.json').read_text())['steps'],0)


if __name__=='__main__':unittest.main()
