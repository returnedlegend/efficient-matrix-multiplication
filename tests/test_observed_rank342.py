import copy
import itertools
import random
import time
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from mmsearch.observed_rank342 import decode_rank3,prepare_space,lift_space,decode_space_hit,validate_space
from mmsearch.observed_rank3_bounded42 import search_bounded
from mmsearch.observed_rank3_checkpoint42 import append_checkpoint,load_checkpoint,save_checkpoint,atomic_json
from mmsearch.free_factor_sat import build_system
from mmsearch.search import encode_candidate
from mmsearch.recombine import digest


def brute_weight(columns,targets,maximum=5):
    def spans(chosen):
        pivots={}
        for value in chosen:
            while value:
                bit=value.bit_length()-1
                if bit in pivots:value^=pivots[bit]
                else:pivots[bit]=value;break
        for target in targets:
            while target:
                bit=target.bit_length()-1
                if bit not in pivots:return False
                target^=pivots[bit]
        return True
    for count in range(min(maximum,len(columns))+1):
        for support in itertools.combinations(range(len(columns)),count):
            if spans([columns[i] for i in support]):return count
    return 99


def small_MM():
    original=[(9,9,9),(12,1,10),(1,10,12),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
    split=original[1:]+[(1,9,9),(8,9,9)]
    return build_system(split+[(9,9,0)],2,'uv',encode_candidate(split,2))


class Rank3Tests(unittest.TestCase):
    def test_exhaustive_small_families_against_subset_oracle(self):
        checked=0
        for count in range(5):
            for columns in itertools.combinations_with_replacement(range(16),count):
                minimum=brute_weight(columns,[1,2,4])
                for bound in (3,4,5):
                    result=decode_rank3(columns,[1,2,4],bound,seconds=1)
                    self.assertEqual(result['status']=='HIT',minimum<=bound,(columns,bound,result))
                checked+=1
        self.assertEqual(checked,4845)
        rng=random.Random(424701);weight5=0
        for _ in range(350):
            columns=[rng.randrange(64) for _ in range(rng.randint(5,8))];targets=[3,12,21]
            minimum=brute_weight(columns,targets);result=decode_rank3(columns,targets,5,1)
            self.assertEqual(result['status']=='HIT',minimum<=5,(columns,result,minimum))
            if minimum==5:weight5+=1
        self.assertGreater(weight5,0)

    def test_inside_pair_branches_and_do_not_combine_distinct_cosets(self):
        for columns,targets,kind in [([1,2,4,8,16],[1,6,24],'inside_contraction_rank2_weight4'),
                                     ([0,1,1,2,4,8,16],[3,12,21],'pair_contraction_rank2_weight3')]:
            self.assertEqual(decode_rank3(columns,targets,4,1)['status'],'NO_WEIGHT_LE4')
            result=decode_rank3(columns,targets,5,1)
            self.assertEqual((result['status'],result['weight'],result['case']),('HIT',5,kind))
        negative=[8,9,16,18,32,36]
        self.assertEqual(brute_weight(negative,[1,2,4]),99)
        self.assertEqual(decode_rank3(negative,[1,2,4],4,1)['status'],'NO_WEIGHT_LE4')
        self.assertEqual(decode_rank3(negative,[1,2,4],5,1)['status'],'NO_WEIGHT_LE5')

    def test_resume_prefix_corruption_timeout_and_unsupported_bound(self):
        columns=[1,2,4,8,16,32];targets=[3,12,48];cursor=None
        for expected in (1,2):
            result=decode_rank3(columns,targets,5,1,cursor,max_branches=1)
            self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(result['cursor']['next_branch'],expected)
            cursor=result['cursor']
        result=decode_rank3(columns,targets,5,1,cursor,max_branches=1)
        self.assertEqual(result['status'],'NO_WEIGHT_LE5');self.assertEqual(result['cursor']['next_branch'],3)
        corrupted=copy.deepcopy(cursor);corrupted['next_branch']+=1
        with self.assertRaises(AssertionError):decode_rank3(columns,targets,5,1,corrupted)
        corrupted=copy.deepcopy(cursor);corrupted['input_sha256']='bad'
        with self.assertRaises(AssertionError):decode_rank3(columns,targets,5,1,corrupted)
        self.assertEqual(decode_rank3(columns,targets,5,1e-12)['status'],'UNKNOWN')
        partial=decode_rank3(columns,targets,6,1)
        self.assertFalse(partial['complete_for_requested_bound']);self.assertEqual(partial['searched_bound'],5)

    def test_true_weight5_full_MM_and_three_coordinate_lift(self):
        system=small_MM();q=prepare_space(system,[9,10,12]);self.assertEqual((q['k'],q['target_rank'],q['weight_bound']),(6,3,5))
        h=[int(x,16) for x in q['column_syndromes_hex']];targets=[int(x,16) for x in q['targets_hex']]
        self.assertEqual(brute_weight(h,targets),5)
        result=decode_rank3(h,targets,5,1);answer=decode_space_hit(system,q,result['entries'])
        self.assertEqual((answer['verification']['rank'],answer['verification']['exact_entries_checked']),(7,64))
        self.assertEqual(answer['lift']['original_kernel_coordinates_verified'],3)
        control=lift_space(system,q,[[i,value] for i,value in enumerate(q['old_coordinates']) if value],require_gain=False)
        self.assertEqual(control['coordinate_kernel_masks_hex'],['0x0']*3)
        broken=copy.deepcopy(q);broken['column_neutral_lifts_hex'][0]=hex(int(broken['column_neutral_lifts_hex'][0],16)^1)
        broken['quotient_sha256']=digest({k:v for k,v in broken.items() if k!='quotient_sha256'})
        with self.assertRaises(AssertionError):validate_space(system,broken)
        entries=copy.deepcopy(result['entries']);entries[0][1]^=1
        with self.assertRaises(AssertionError):lift_space(system,q,entries)

    def test_durable_branch_ledger_resume_and_corruption(self):
        q=dict(column_syndromes_hex=list(map(hex,[1,2,4,8,16,32])),targets_hex=list(map(hex,[3,12,48])),
               weight_bound=5,quotient_sha256='ledger-control')
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);cursor=None
            for expected in (1,2,3):
                result=search_bounded(q,seconds=1,memory_mb=256,cursor=cursor,branch_budget=1,
                    on_progress=lambda record,state:append_checkpoint(directory,q['quotient_sha256'],record,state))
                save_checkpoint(directory,q['quotient_sha256'],result.get('cursor'))
                cursor=load_checkpoint(directory,q['quotient_sha256'])
                self.assertEqual(cursor['next_branch'],expected)
                self.assertEqual(result['status'],'UNKNOWN' if expected<3 else 'NO_ONE_SUBSPACE_GAIN')
            with self.assertRaises(AssertionError):load_checkpoint(directory,'changed-source')
            bad={key:value for key,value in cursor.items() if key!='completed_prefix'};bad['next_branch']+=1
            atomic_json(directory/'decoder-state.json',dict(quotient_sha256=q['quotient_sha256'],cursor=bad))
            with self.assertRaises(AssertionError):load_checkpoint(directory,q['quotient_sha256'])

    def test_bounded_worker_reaping_progress_and_memory(self):
        q=dict(column_syndromes_hex=list(map(hex,[1,2,4,8,16,32])),targets_hex=list(map(hex,[3,12,48])),
               weight_bound=5,quotient_sha256='tiny-input')
        progress=[];result=search_bounded(q,seconds=1,memory_mb=256,branch_budget=1,on_progress=lambda record,cursor:progress.append(record))
        self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped']);self.assertEqual(len(progress),1)
        self.assertEqual(result['worker_stats']['address_space_limit_bytes'],256*1024**2)
        def stall(*args):time.sleep(2)
        with patch('mmsearch.observed_rank3_bounded42._worker',stall):result=search_bounded(q,seconds=.02,memory_mb=256)
        self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped'])
        with self.assertRaises(ValueError):search_bounded(q,seconds=1,memory_mb=127)


if __name__=='__main__':unittest.main()
