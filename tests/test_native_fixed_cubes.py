"""Exact positive controls and atomic fixed-cube-count rejection checks."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from mmsearch.search import _rotations, encode_candidate, is_cyclic, naive_terms
from mmsearch.verify import verify_candidate

ROOT=Path(__file__).resolve().parents[1]


def inflated_naive():
    terms=set(naive_terms(2))
    terms.difference_update(_rotations((1,2,4)))
    terms.update(_rotations((1,2,8)))
    terms.update(_rotations((1,2,12)))
    assert len(terms)==11
    return terms


@unittest.skipUnless(shutil.which('g++'),'C++ compiler unavailable')
class FixedCubeNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory()
        cls.binary=Path(cls.build.name)/'fixed-worker'
        subprocess.run(['g++','-std=c++17','-O3','-DNDEBUG','-Wall','-Wextra','-Wpedantic',
                        str(ROOT/'native/flip_worker_fixed_cubes.cpp'),'-o',str(cls.binary)],
                       check=True,capture_output=True,text=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def run_worker(self,folder,*extra):
        folder=Path(folder);source=folder/'input.txt';prefix=folder/'walk'
        source.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in sorted(inflated_naive())))
        result=subprocess.run([str(self.binary),'--input',str(source),'--output',str(prefix),
                               '--n','2','--target','8','--max-rank','20','--steps','1000',
                               '--seconds','2','--cyclic','--fixed-cubes','2','--archive-size','8',
                               '--archive-every','1','--seed','19',*extra],
                              capture_output=True,text=True,timeout=5)
        return result,prefix

    def verify_file(self,path):
        terms=[tuple(map(int,line.split())) for line in Path(path).read_text().splitlines()]
        self.assertEqual(sum(a==b==c for a,b,c in terms),2)
        self.assertTrue(is_cyclic(terms))
        self.assertTrue(verify_candidate(encode_candidate(terms,2),random_trials=0)['valid'])
        return terms

    def test_rank11_exact_cyclic_control_reduces_to_rank8(self):
        self.assertTrue(verify_candidate(encode_candidate(inflated_naive(),2))['valid'])
        with tempfile.TemporaryDirectory() as directory:
            result,prefix=self.run_worker(directory)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(len(self.verify_file(prefix.with_suffix('.best.txt'))),8)
            stats=json.loads(prefix.with_suffix('.stats.json').read_text())
            self.assertEqual(stats['required_fixed_cubes'],2)
            self.assertEqual(stats['best_fixed_cubes'],2)
            self.assertTrue(stats['exact'])
            for path in [prefix.with_suffix('.current.txt'),*prefix.with_suffix('.archive').glob('*.txt')]:
                self.verify_file(path)

    def test_bad_initial_fixed_count_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result,prefix=self.run_worker(directory,'--fixed-cubes','3')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('initial fixed cube count',result.stderr)
            self.assertFalse(prefix.with_suffix('.best.txt').exists())

    def test_rejected_and_accepted_moves_preserve_exactness_and_count_every_step(self):
        with tempfile.TemporaryDirectory() as directory:
            trace=Path(directory)/'trace.txt'
            result,prefix=self.run_worker(directory,'--target','0','--steps','250',
                                          '--plus-every','1','--restart-every','37','--trace',str(trace))
            self.assertEqual(result.returncode,0,result.stderr)
            accepted=[]
            for line in trace.read_text().splitlines():
                _,_,ok,*fields=line.split();accepted.append(int(ok))
                terms=[tuple(map(int,field.split(','))) for field in fields]
                self.assertEqual(sum(a==b==c for a,b,c in terms),2)
                self.assertTrue(is_cyclic(terms))
                self.assertTrue(verify_candidate(encode_candidate(terms,2),random_trials=0)['valid'])
            self.assertEqual(len(accepted),250)
            self.assertIn(0,accepted)
            self.assertIn(1,accepted)
            for path in [prefix.with_suffix('.best.txt'),prefix.with_suffix('.current.txt'),
                         *prefix.with_suffix('.archive').glob('*.txt')]:
                self.verify_file(path)


if __name__=='__main__':
    unittest.main()
