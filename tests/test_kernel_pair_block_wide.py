import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel_wide import native_input,validate_circuit
from mmsearch.free_factor_kernel import pair_column
from mmsearch.free_factor_sat import build_system,satisfies
from mmsearch.kernel_pair_block_wide import apply_pair,optimize_pair,single_optimum,validate_pair_solution
from mmsearch.search import encode_candidate,naive_terms

ROOT=Path(__file__).resolve().parents[1];BINARY=ROOT/'native/free_factor_pair_block_worker_wide'


def planted_wide():
    terms=list(naive_terms(2))+[(3,b,1) for b in (2,3,4,5)]
    padding=[(5,b,0) for b in (1,2,4,8,15)]
    system=build_system(terms+[(3,6,0),(3,7,0)]+padding,2,'uv',encode_candidate(terms,2))
    ids={tuple(pair):g for g,pair in enumerate(system['pairs'])}
    shared=[ids[3,6],ids[3,7],*[ids[5,b] for b in (1,2,4,8,15)]]
    s1=[ids[3,2],ids[3,3],*shared];s2=[ids[3,4],ids[3,5],*shared]
    return system,[dict(class_id=2,support=s1),dict(class_id=2,support=s2)]


class WidePairBlockTests(unittest.TestCase):
    def test_wide_objective_matches_full16_squared_enumeration(self):
        rng=random.Random(128)
        for _ in range(25):
            values=[rng.randrange(16) for _ in range(24)]
            a=rng.sample(range(24),rng.randrange(9,17));b=rng.sample(range(24),rng.randrange(9,17))
            result=optimize_pair(values,a,b);before=sum(bool(w) for w in values)
            brute=min(sum(bool(w) for w in apply_pair(values,a,b,d,e)) for d,e in itertools.product(range(16),repeat=2))
            self.assertEqual(before+result['delta'],brute)

    def test_nine_support_planted_barrier_joint12_to8(self):
        system,circuits=planted_wide();v=system['baseline_vectors'];a,b=[c['support'] for c in circuits]
        self.assertEqual((len(a),len(b)),(9,9))
        self.assertEqual(single_optimum(v,a)['delta'],0);self.assertEqual(single_optimum(v,b)['delta'],0)
        best=optimize_pair(v,a,b);self.assertEqual(best['delta'],-4)
        first=apply_pair(v,a,[],best['d'],0);self.assertTrue(satisfies(system,first))
        self.assertGreater(sum(bool(w) for w in first),12)
        self.assertTrue(satisfies(system,apply_pair(v,a,b,best['d'],best['e'])))

    @unittest.skipUnless(BINARY.exists(),'wide block worker not built')
    def test_native_wide_positive_changed_labels_and129_nonkernel_rejection(self):
        system,circuits=planted_wide();rng=random.Random(67)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for trial in range(5):
                current=dict(system)
                current['baseline_vectors']=apply_pair(system['baseline_vectors'],circuits[0]['support'],circuits[1]['support'],rng.randrange(16),rng.randrange(16))
                source=root/f'input-{trial}';source.write_bytes(native_input(current,circuits));prefix=root/f'out-{trial}'
                done=subprocess.run([str(BINARY),'--input',str(source),'--output',str(prefix),'--target','8','--seconds','1'],capture_output=True,text=True,timeout=2)
                self.assertEqual(done.returncode,0,done.stderr)
                record=json.loads(prefix.with_suffix('.solution.json').read_text())
                moved,candidate,report=validate_pair_solution(current,circuits,record)
                self.assertTrue(report['valid']);self.assertEqual(report['rank'],8)
            columns=[pair_column(pair,4) for pair in system['pairs']]
            bad=list(circuits[0]['support']);bad[0]=next(g for g in range(len(columns)) if g not in bad)
            with self.assertRaises(ValueError):validate_circuit(columns,bad)
            raw=native_input(system,circuits[:1]).decode().splitlines();raw[-1]=' '.join(map(str,[2,9,*bad]))
            source=root/'bad';source.write_text('\n'.join(raw)+'\n')
            done=subprocess.run([str(BINARY),'--input',str(source),'--output',str(root/'bad-out')],capture_output=True,text=True,timeout=2)
            self.assertNotEqual(done.returncode,0);self.assertIn('nonkernel',done.stderr)
            large=build_system([(a,b,0) for a in range(1,16) for b in range(1,16)],2,'uv',encode_candidate(naive_terms(2),2))
            with self.assertRaises(ValueError):validate_circuit([pair_column(pair,4) for pair in large['pairs']],list(range(129)))
            raw=native_input(large,[]).decode().splitlines();raw[1]=raw[1].rsplit(' ',1)[0]+' 1';raw.append(' '.join(map(str,[2,129,*range(129)])))
            source.write_text('\n'.join(raw)+'\n')
            done=subprocess.run([str(BINARY),'--input',str(source),'--output',str(root/'bad129')],capture_output=True,text=True,timeout=2)
            self.assertNotEqual(done.returncode,0)


if __name__=='__main__':unittest.main()
