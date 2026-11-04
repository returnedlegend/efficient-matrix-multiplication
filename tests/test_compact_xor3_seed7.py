"""Tiny exact controls for crossover/reduction; no N5 native search."""
import itertools
import unittest
from mmsearch.compact_xor3_seed7 import canonical,xor_three,reduce_shared_two
from mmsearch.tensor_code7 import atom_column

def tensor(terms,n):
    answer=0
    for term in terms:answer^=atom_column(term,n)
    return answer

class ExactReductionTests(unittest.TestCase):
    def test_three_parent_odd_tensor_identity_and_duplicates(self):
        parents=[[(1,1,1)],[(1,1,1)],[(1,1,1)]]
        self.assertEqual(xor_three(parents),((1,1,1),));self.assertEqual(canonical([(0,1,1),(1,1,1),(1,1,1)]),())
        with self.assertRaises(ValueError):xor_three(parents[:2])

    def test_merge_all_free_axes_and_existing_cancellation(self):
        for free in range(3):
            left=[1,1,1];right=[1,1,1];right[free]=2
            before=[tuple(left),tuple(right)];after,moves=reduce_shared_two(before)
            self.assertEqual(len(after),1);self.assertEqual(tensor(before,2),tensor(after,2));self.assertEqual(moves[0]['free_axis'],free)
            before.append(after[0]);empty,moves=reduce_shared_two(before)
            self.assertEqual(empty,());self.assertEqual(tensor(before,2),0)

    def test_deterministic_fixpoint_and_exhaustive_small_fullcolumns(self):
        atoms=list(itertools.product(range(1,4),repeat=3))
        for indices in itertools.combinations(range(len(atoms)),3):
            before=[atoms[i]for i in indices];after,moves=reduce_shared_two(before)
            self.assertEqual(tensor(before,2),tensor(after,2))
            self.assertEqual((after,moves),reduce_shared_two(reversed(before)))
            self.assertEqual(reduce_shared_two(after),(after,[]))

if __name__=='__main__':unittest.main()
