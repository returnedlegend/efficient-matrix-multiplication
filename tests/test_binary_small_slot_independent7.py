"""Independent finite CP oracle and fixed-outside S6 controls, no N5 calls."""
import itertools
import random
import unittest
from unittest.mock import patch
from mmsearch import binary_small_slot_repair7 as subject
from mmsearch.search import naive_terms


def literal(factors,shape):
    return [sum(((a>>i)&1)*((b>>j)&1)*((c>>k)&1) for a,b,c in factors)%2
            for i,j,k in itertools.product(*(range(d) for d in shape))]
def packed(factors,shape):return sum(v<<i for i,v in enumerate(literal(factors,shape)))


class SmallSlotIndependentControls(unittest.TestCase):
    def test_conditional_rank3_decisions_match_finite_literal_cp_oracle(self):
        shape=[3,2,2]
        points={packed([term],shape) for term in itertools.product(range(1,8),range(1,4),range(1,4))}
        reachable={0}
        for _ in range(3):reachable|={a^b for a in tuple(reachable) for b in points}
        factors=[(1,1,1),(2,2,2),(4,3,3),(3,2,1),(5,1,2)]
        selected=[0,2,4];outside=[factors[i] for i in (1,3)];outside_mask=packed(outside,shape)
        rng=random.Random(711036);checks=0
        for target in rng.sample(range(4096),128):
            core=[(target>>i)&1 for i in range(12)]
            result=subject.repair_slots(core,shape,factors,selected,timeout_seconds=2)
            expected=(target^outside_mask) in reachable
            self.assertEqual(result['status']=='RAW_EXACT_COMPACT',expected,(target,result))
            self.assertTrue(result['complete']);self.assertEqual(result['fixed_outside_factors'],[list(t) for t in outside])
            self.assertTrue(result['no_global_cp_negative_claim']);self.assertFalse(result['publication_eligible'])
            if expected:self.assertEqual(literal(result['factors'],shape),core)
            else:self.assertEqual(result['status'],'REPAIR_EXCLUDED')
            checks+=1
        self.assertEqual(checks,128);print('independent_fixed_outside_CP3_oracle_cases',checks)

    def test_all_seven_S6_choices_repair_drop_one_schoolbook_n2(self):
        terms=list(naive_terms(2));core=literal(terms,[4]*3);factors=terms[:-1]
        for slots in itertools.combinations(range(7),6):
            result=subject.repair_slots(core,[4]*3,factors,slots,timeout_seconds=2)
            self.assertEqual(result['status'],'RAW_EXACT_COMPACT')
            self.assertLessEqual(len(result['factors']),7)
            self.assertEqual(literal(result['factors'],[4]*3),core)
            outside=[t for i,t in enumerate(factors) if i not in slots]
            self.assertEqual(result['fixed_outside_factors'],[list(t) for t in outside])

    def test_late_final_scalar_cannot_return_accepted_compact_solution(self):
        stop=[False];scalar=subject.block.scalar_loss
        def late(*args):
            value=scalar(*args);stop[0]=True;return value
        with patch.object(subject.block,'scalar_loss',late):
            result=subject.repair_slots([1]+[0]*7,[2]*3,[(1,1,1)]*3,[0,1,2],cancelled=lambda:stop[0])
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
        self.assertFalse(result['publication_eligible'])


if __name__=='__main__':unittest.main()
