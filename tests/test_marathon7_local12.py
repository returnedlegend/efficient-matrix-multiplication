import unittest
from unittest.mock import patch
from mmsearch import marathon7_local12 as subject


def scalar_rank(value,a,b):
    space={0}
    for i in range(a):
        row=value>>(i*b)&((1<<b)-1);space|={p^row for p in tuple(space)}
    return len(space).bit_length()-1


class Local12FilterTests(unittest.TestCase):
    def test_classifier_all_4x4_and_rectangular(self):
        for value in range(65536):self.assertEqual(subject.matrix_rank_at_most_three(value,4,4),min(4,scalar_rank(value,4,4)))
        for a,b in [(0,4),(4,0),(2,3),(3,2)]:
            for value in range(1<<(a*b)):self.assertEqual(subject.matrix_rank_at_most_three(value,a,b),min(4,scalar_rank(value,a,b)))

    def test_cp9_diagonal_image_passes_and_rank4_image_excludes(self):
        # Nine original rank-one diagonal slices span a d9 image.
        slices=[1<<(i*9+i) for i in range(9)];core=[v>>j&1 for v in slices for j in range(81)]
        r=subject.rank_three_span(core,[9,9,9],0);self.assertEqual(r['status'],'BOUND_PASSED_NOT_EXISTENCE');self.assertEqual(r['lowrank_span_rank'],9)
        # A d9 image in 4x9 matrices: first eight rank-one points plus a rank4
        # representative, whose complete affine coset keeps rank>=4.
        slices=[1<<(i+1) for i in range(8)]+[(1<<0)|(1<<10)|(1<<20)|(1<<30)]
        core=[v>>j&1 for v in slices for j in range(36)]
        r=subject.rank_three_span(core,[9,4,9],0);self.assertEqual(r['status'],'LOWRANK_SPAN_EXCLUDES');self.assertEqual(r['points_tested'],511);self.assertEqual(r['lowrank_span_rank'],8)

    def test_late_classification_cannot_reject_or_pass(self):
        slices=[1<<(i*9+i) for i in range(9)];core=[v>>j&1 for v in slices for j in range(81)];flag=[False];actual=subject.matrix_rank_at_most_three
        def late(*args):result=actual(*args);flag[0]=True;return result
        with patch.object(subject,'matrix_rank_at_most_three',late):r=subject.rank_three_span(core,[9,9,9],0,cancelled=lambda:flag[0])
        self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(r['complete'])


if __name__=='__main__':unittest.main()
