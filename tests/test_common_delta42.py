import copy
import itertools
import signal
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from mmsearch.common_delta42 import (columns_from_rows,decode_hit,lift_hit,low_weight_search,
    multiply,prepare_quotient,search_bounded,validate_quotient)
from mmsearch.free_factor_sat import build_system
from mmsearch.recombine import canonical_terms,digest,encode
from mmsearch.tensor import strassen_candidate
from mmsearch.verify import verify_candidate
from scripts.campaign_common_delta42 import SOURCE_FILES


def planted_split():
    planted = strassen_candidate(2)
    terms = canonical_terms(planted)
    for t,(u,v,w) in enumerate(terms):
        for a in range(1,16):
            b = u^a
            if not b:continue
            split = list(terms[:t])+list(terms[t+1:])+[(a,v,w),(b,v,w)]
            if len({(z,x) for x,y,z in split})!=8:continue
            baseline = encode(split,2)
            if not verify_candidate(baseline,random_trials=0)['valid']:continue
            dictionary = sorted(set(split)|set(terms))
            return build_system(dictionary,2,'wu',baseline),v
    raise AssertionError('could not construct split Strassen control')


class CommonDelta42Tests(unittest.TestCase):
    def test_planted_split_eight_to_seven_and_baseline_weight_k_control(self):
        system,delta = planted_split()
        q = prepare_quotient(system,delta)
        baseline_y = [i for i,g in enumerate(q['relevant_groups']) if g in q['delta_groups']]
        control = lift_hit(system,q,baseline_y)
        self.assertEqual(control['z_hex'],'0x0')
        self.assertEqual(control['rank_after'],8)
        result = search_bounded(q,seconds=1,memory_mb=256,max_work_mb=64)
        self.assertEqual(result['status'],'HIT')
        answer = decode_hit(system,q,result['y_indices'])
        self.assertEqual(answer['status'],'SAT')
        self.assertLessEqual(answer['verification']['rank'],7)
        self.assertEqual(answer['verification']['exact_entries_checked'],64)
        self.assertTrue(result['worker_reaped'])
        self.assertEqual(result['worker_stats']['address_space_limit_bytes'],256*1024**2)

    def test_source_snapshot_covers_all_local_imports(self):
        root=Path(__file__).resolve().parents[1]
        for relative in SOURCE_FILES:
            parts=list(Path(relative).with_suffix('').parts)
            for node in ast.walk(ast.parse((root/relative).read_text())):
                if not isinstance(node,ast.ImportFrom):continue
                module=(parts[:-node.level] if node.level else [])+(node.module.split('.') if node.module else [])
                if module and module[0] in ['mmsearch','scripts']:
                    self.assertIn('/'.join(module)+'.py',SOURCE_FILES)

    def test_every_tiny_quotient_assignment_matches_neutral_existence(self):
        columns = [1,2,3,3,4,5]
        vectors = [1,1,2,3,0,0]
        rows = [sum(1<<g for g,c in enumerate(columns) if c>>r&1) for r in range(3)]
        rhs = []
        for row in rows:
            value = 0
            for g in range(len(columns)):
                if row>>g&1:value ^= vectors[g]
            rhs.append(value)
        system = dict(coefficients=rows,right_sides=rhs,baseline_vectors=vectors,
            metadata=dict(width=2),pairs=[(1,1)]*len(columns))
        q = prepare_quotient(system,1)
        for values in itertools.product([0,1],repeat=len(q['relevant_groups'])):
            indices = [i for i,v in enumerate(values) if v]
            syndrome = 0
            for i in indices:syndrome ^= int(q['column_syndromes_hex'][i],16)
            quotient_ok = syndrome==int(q['target_syndrome_hex'],16)
            relevant_z = sum(1<<g for g in q['delta_groups'])
            for i in indices:relevant_z ^= 1<<q['relevant_groups'][i]
            exists = any(not multiply(columns,relevant_z^sum(v<<g for g,v in zip(q['neutral_groups'],neutral)))
                for neutral in itertools.product([0,1],repeat=len(q['neutral_groups'])))
            self.assertEqual(quotient_ok,exists)
            if quotient_ok:self.assertTrue(lift_hit(system,q,indices)['original_kernel_verified'])

    def test_corrupted_neutral_witness_is_rejected_even_after_rehash(self):
        system,delta = planted_split()
        q = prepare_quotient(system,delta)
        bad = copy.deepcopy(q)
        bad['column_neutral_lifts_hex'][0] = hex(int(bad['column_neutral_lifts_hex'][0],16)^(1<<bad['relevant_groups'][0]))
        bad['quotient_sha256']=digest({k:v for k,v in bad.items() if k!='quotient_sha256'})
        with self.assertRaisesRegex(AssertionError,'witness'):
            validate_quotient(system,bad)

    def test_weight_four_pair_representatives_and_negative_scope(self):
        values = [1,1,2,4,8]
        for target in range(16):
            q=dict(column_syndromes_hex=list(map(hex,values)),target_syndrome_hex=hex(target),
                weight_bound=4,original_row_count=4,scope='tiny synthetic quotient')
            expected = any(len(indices)<=4 and multiply(values,sum(1<<i for i in indices))==target
                for n in range(5) for indices in itertools.combinations(range(5),n))
            result=low_weight_search(q,seconds=1,max_work_mb=8)
            self.assertEqual(result['status']=='HIT',expected)
        q=dict(column_syndromes_hex=list(map(hex,[1,2,4,8,16])),target_syndrome_hex='0x1f',
            weight_bound=5,original_row_count=5,scope='tiny synthetic quotient')
        result=low_weight_search(q,seconds=1,max_work_mb=8)
        self.assertEqual(result['status'],'NO_WEIGHT_LE4')
        self.assertFalse(result['complete_for_requested_gain'])
        q['weight_bound']=4
        self.assertEqual(low_weight_search(q,seconds=1)['status'],'NO_ONE_DELTA_GAIN')

    def test_timeout_memory_and_inherited_signal_cleanup(self):
        q=dict(column_syndromes_hex=list(map(hex,[1,2,4,8,16])),target_syndrome_hex='0x1f',
            weight_bound=4,original_row_count=5,scope='tiny synthetic quotient')
        self.assertEqual(low_weight_search(q,seconds=1e-12)['status'],'UNKNOWN')
        self.assertEqual(low_weight_search(q,seconds=1,max_work_mb=1e-9)['status'],'UNKNOWN')
        system,delta=planted_split();q=prepare_quotient(system,delta)
        def stall(*args):
            self.assertEqual(signal.getsignal(signal.SIGTERM),signal.SIG_DFL)
            time.sleep(10)
        previous=signal.signal(signal.SIGTERM,lambda *_:None)
        try:
            with patch('mmsearch.common_delta42._worker',stall):
                result=search_bounded(q,seconds=.02,memory_mb=256)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertTrue(result['worker_reaped'])
            self.assertLess(result['elapsed_seconds'],.5)
        finally:signal.signal(signal.SIGTERM,previous)


if __name__=='__main__':
    unittest.main()
import ast
