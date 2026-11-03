import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.search import encode_candidate,naive_terms,is_cyclic
from mmsearch.native_bridge import canonical_terms
from mmsearch.verify import verify_candidate
from scripts.campaign_unrestricted_frontier42 import DEFAULT_BINARY,validate_seed,inspect_export
from tests.test_native_fixed_cubes import inflated_naive

ROOT=Path(__file__).resolve().parents[1]


def noncyclic125():
    terms=set(naive_terms(5));terms.remove((1,1,1));terms.remove((1,2,32))
    terms.update([(1,3,1),(1,2,33)])
    return terms


class UnrestrictedFrontierTests(unittest.TestCase):
    def test_accepts_exact125_without_cyclic_or_cube_constraints_and_rejects_range(self):
        terms=noncyclic125();self.assertFalse(is_cyclic(terms))
        accepted,report=validate_seed(encode_candidate(terms,5))
        self.assertEqual(len(accepted),125);self.assertEqual(report['canonical']['exact_entries_checked'],15625)
        def lift(mask):return sum(((mask>>(i*2+j))&1)<<(i*5+j) for i in range(2) for j in range(2))
        too_large=set(naive_terms(5))
        too_large.difference_update(tuple(lift(x) for x in t) for t in naive_terms(2))
        too_large.update(tuple(lift(x) for x in t) for t in inflated_naive())
        self.assertEqual(len(too_large),128)
        with self.assertRaisesRegex(ValueError,'93..125'):validate_seed(encode_candidate(too_large,5))
        with self.assertRaises(ValueError):validate_seed(dict(encode_candidate(terms,5),field=0))
        for value in [3,True]:
            bad=encode_candidate(terms,5);bad['terms'][0]['u'][0]=value
            with self.assertRaises(ValueError):validate_seed(bad)

    def native(self,root,terms,n,target,maximum,steps):
        source=root/'source.txt';prefix=root/'native_walk'
        source.write_text(''.join(f'{u} {v} {w}\n' for u,v,w in sorted(terms)))
        command=[str(DEFAULT_BINARY),'--input',str(source),'--output',str(prefix),'--n',str(n),
                 '--target',str(target),'--max-rank',str(maximum),'--seed','19','--steps',str(steps),
                 '--seconds','.1','--archive-size','8','--archive-every','1']
        run=subprocess.run(command,capture_output=True,text=True,timeout=2)
        self.assertEqual(run.returncode,0,run.stderr)
        meta=dict(native_seed=19,max_rank=maximum,source_essential_rank=len(terms),cyclic=False)
        return prefix,meta

    def test_planted_generic_recovery_and_corrupt_full_tensor_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix,meta=self.native(root,inflated_naive(),2,8,20,100)
            result=inspect_export(prefix,root,meta,n=2,target=8,final=True)
            self.assertTrue(result['winner']);self.assertLessEqual(result['adjusted_stats']['best_rank'],8)
            self.assertFalse(result['adjusted_stats']['cyclic'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix,meta=self.native(root,noncyclic125(),5,92,131,0)
            path=prefix.with_suffix('.best.txt');lines=path.read_text().splitlines();path.write_text('\n'.join(lines[:-1])+'\n')
            with self.assertRaisesRegex(RuntimeError,'full matrix tensor'):
                inspect_export(prefix,root,meta,final=True)
            self.assertFalse((root/'WINNER.json').exists());self.assertFalse((root/'walk.stats.json').exists())

    def test_zero_step_launch_resume_keeps_full_states_and_no_restriction_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.json';source.write_text(json.dumps(encode_candidate(noncyclic125(),5)))
            base=['python3',str(ROOT/'scripts/campaign_unrestricted_frontier42.py'),'--seconds','4',
                  '--phase-seconds','1','--phase-limit','1','--step-limit','0']
            first=root/'first';second=root/'second'
            run=subprocess.run([*base,'--input',str(source),'--output-dir',str(first),'--seed','6789'],
                               capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertEqual(run.returncode,0,run.stderr)
            run=subprocess.run([*base,'--resume',str(first/'checkpoint.json'),'--output-dir',str(second)],
                               capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertEqual(run.returncode,0,run.stderr)
            meta=json.loads((second/'phase-000/manifest.json').read_text())
            self.assertEqual(meta['source_essential_rank'],125);self.assertEqual(meta['max_rank'],131)
            self.assertEqual(meta['global_phase'],1)
            for flag in ['--cyclic','--fixed-cubes','--allow-arbitrary']:self.assertNotIn(flag,meta['command'])
            stats=json.loads((second/'phase-000/walk.stats.json').read_text())
            self.assertEqual(stats['steps'],0);self.assertTrue(stats['independent_full_verification'])
            cp=json.loads((first/'checkpoint.json').read_text());cp['frontier'][0]['source_sha256']='0'*64
            bad=root/'bad.json';bad.write_text(json.dumps(cp))
            run=subprocess.run([*base,'--resume',str(bad),'--output-dir',str(root/'bad')],
                               capture_output=True,text=True,timeout=3,cwd=ROOT)
            self.assertNotEqual(run.returncode,0);self.assertIn('source hash mismatch',run.stderr)


if __name__=='__main__':unittest.main()
