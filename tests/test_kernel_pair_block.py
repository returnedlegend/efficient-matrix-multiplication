import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel import decode_checked,native_input
from mmsearch.free_factor_sat import build_system,satisfies
from mmsearch.kernel_pair_block import apply_pair,optimize_pair,single_optimum,validate_pair_solution
from mmsearch.search import encode_candidate,naive_terms
from scripts.campaign_kernel_pair_block import cursor_ordinal

ROOT=Path(__file__).resolve().parents[1];BINARY=ROOT/'native/free_factor_pair_block_worker'


def planted():
    terms=set(naive_terms(2));terms.remove((1,1,1));terms.remove((1,2,4))
    terms.update({(1,4,5),(1,5,1),(1,6,4)})
    baseline=encode_candidate(terms,2)
    system=build_system(list(terms)+[(1,1,0),(1,2,0)],2,'uv',baseline)
    ids={tuple(pair):g for g,pair in enumerate(system['pairs'])}
    first=[ids[1,4],ids[1,1],ids[1,5]];second=[ids[1,4],ids[1,2],ids[1,6]]
    return system,[dict(class_id=0,support=first),dict(class_id=0,support=second),
                   dict(class_id=2,support=sorted(set(first)^set(second)))]


class PairBlockTests(unittest.TestCase):
    def test_reference_matches_all_16_squared_masks_with_zeros_and_empty_categories(self):
        rng=random.Random(91)
        for _ in range(50):
            values=[rng.randrange(16) for _ in range(10)]
            s1=rng.sample(range(10),rng.randrange(1,9));s2=rng.sample(range(10),rng.randrange(1,9))
            result=optimize_pair(values,s1,s2);before=sum(bool(w) for w in values)
            brute=min(sum(bool(w) for w in apply_pair(values,s1,s2,d,e)) for d,e in itertools.product(range(16),repeat=2))
            self.assertEqual(before+result['delta'],brute)
        result=optimize_pair([3,0,1,0,2],[0,1,2],[0,3,4])
        self.assertEqual(result['delta'],-1)

    def test_planted_two_steps_preserve_tensor_but_no_single_strict_reduction(self):
        system,circuits=planted();vectors=system['baseline_vectors'];s1,s2=[c['support'] for c in circuits[:2]]
        self.assertEqual(single_optimum(vectors,s1)['delta'],0);self.assertEqual(single_optimum(vectors,s2)['delta'],0)
        optimum=optimize_pair(vectors,s1,s2);self.assertEqual(optimum['delta'],-1)
        first=apply_pair(vectors,s1,[],optimum['d'],0);self.assertTrue(satisfies(system,first))
        moved=apply_pair(vectors,s1,s2,optimum['d'],optimum['e']);self.assertTrue(satisfies(system,moved))
        self.assertEqual(decode_checked(system,moved)[1]['rank'],8)

    @unittest.skipUnless(BINARY.exists(),'native block worker not built')
    def test_native_joint_positive_and_timeout_resume_cursor(self):
        system,circuits=planted()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input';source.write_bytes(native_input(system,circuits))
            def run(name,*extra):
                prefix=root/name
                completed=subprocess.run([str(BINARY),'--input',str(source),'--output',str(prefix),
                                          '--target','8','--seconds','1',*extra],capture_output=True,text=True,timeout=2)
                self.assertEqual(completed.returncode,0,completed.stderr)
                return prefix,json.loads(prefix.with_suffix('.stats.json').read_text())
            prefix,stats=run('positive')
            self.assertEqual(stats['status'],'MODEL_FOUND')
            model,candidate,report=validate_pair_solution(system,circuits,json.loads(prefix.with_suffix('.solution.json').read_text()))
            self.assertTrue(report['valid']);self.assertEqual(report['rank'],8)
            prefix,first=run('partial','--target','0','--max-pairs','1')
            self.assertEqual(first['status'],'UNKNOWN');self.assertEqual(first['pairs_considered'],1)
            prefix,last=run('resumed','--target','0','--start-i',str(first['next_i']),'--start-j',str(first['next_j']))
            self.assertEqual(last['status'],'NO_TARGET');self.assertEqual(last['pairs_considered'],2)
            self.assertEqual(cursor_ordinal(3,last['next_i'],last['next_j']),3)
            prefix,zero=run('zero','--seconds','0')
            self.assertEqual(zero['status'],'UNKNOWN');self.assertEqual(zero['pairs_considered'],0)

    @unittest.skipUnless(BINARY.exists(),'native block worker not built')
    def test_native_rejects_nonkernel_and_matches_reference_on_changed_labels(self):
        system,circuits=planted();rng=random.Random(15)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for trial in range(8):
                changed=dict(system);changed['baseline_vectors']=apply_pair(system['baseline_vectors'],circuits[0]['support'],circuits[1]['support'],rng.randrange(16),rng.randrange(16))
                optimum=optimize_pair(changed['baseline_vectors'],circuits[0]['support'],circuits[1]['support'])
                best=sum(bool(w) for w in changed['baseline_vectors'])+optimum['delta']
                source=root/f'input-{trial}';source.write_bytes(native_input(changed,circuits[:2]));prefix=root/f'out-{trial}'
                done=subprocess.run([str(BINARY),'--input',str(source),'--output',str(prefix),'--target',str(best),'--seconds','1'],capture_output=True,text=True,timeout=2)
                self.assertEqual(done.returncode,0,done.stderr)
                stats=json.loads(prefix.with_suffix('.stats.json').read_text());self.assertEqual(stats['best_rank'],best)
                if prefix.with_suffix('.solution.json').exists():validate_pair_solution(changed,circuits[:2],json.loads(prefix.with_suffix('.solution.json').read_text()))
            source=root/'bad';lines=native_input(system,circuits[:1]).decode().splitlines()
            support=list(circuits[0]['support']);support[0]=next(i for i in range(len(system['pairs'])) if i not in support)
            lines[-1]=' '.join(map(str,[0,3,*support]));source.write_text('\n'.join(lines)+'\n')
            done=subprocess.run([str(BINARY),'--input',str(source),'--output',str(root/'bad-out')],capture_output=True,text=True,timeout=2)
            self.assertNotEqual(done.returncode,0);self.assertIn('nonkernel',done.stderr)


if __name__=='__main__':unittest.main()
