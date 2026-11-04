"""Independent diagonal-code CP bounds and retained-late-witness controls."""
import unittest
from unittest.mock import patch
from mmsearch import conditional_surplus_three7 as subject
from mmsearch.compact_sat import BinaryBasis


def diagonal_code(labels):
    words=[]
    for word in range(1,1<<len(labels)):
        syndrome=0
        for i,label in enumerate(labels):
            if word>>i&1:syndrome^=label
        if not syndrome:words.append(word)
    independent=BinaryBasis(words).vectors;n=len(labels)
    matrices=[sum(((word>>i)&1)<<(i*n+i) for i in range(n)) for word in independent]
    return [0,*matrices,matrices[0],0],n


class ConditionalC3IndependentControls(unittest.TestCase):
    def test_all_seven_repeated_fano_labels_need_true_c3_cover(self):
        for repeated in range(1,8):
            with self.subTest(repeated=repeated):
                raw,n=diagonal_code(list(range(1,8))+[repeated])
                result=subject.solve_pair_image(raw,n,n,8,timeout_seconds=2)
                self.assertEqual(result['status'],'SAT',result)
                self.assertEqual((result['target_rank'],result['inside_rank']),(5,0))
                self.assertEqual(result['case'],'conditional_repeated_pair_extension')
                self.assertEqual(len(result['support']),8)
                for value,coordinates in zip(raw,result['target_coordinates']):
                    rebuilt=0
                    for i,point in enumerate(result['support']):
                        expected=sum(((point['left']>>j)&1)*((point['right']>>k)&1)<<(j*n+k) for j in range(n) for k in range(n))
                        self.assertEqual(point['column'],expected)
                        if coordinates>>i&1:rebuilt^=point['column']
                    self.assertEqual(rebuilt,value)

    def test_exact_diagonal_support_lower_bound_and_missing_bound_scope(self):
        raw,n=diagonal_code(list(range(1,10)))
        # All nine diagonal coordinates are active. The other unfolding has
        # ranknine, and nine coordinate products cover, so exact CP=nine.
        active=0
        for value in raw:
            for i in range(n):active|=((value>>(i*n+i))&1)<<i
        self.assertEqual(active.bit_count(),9)
        result=subject.solve_pair_image(raw,n,n,8,timeout_seconds=2)
        self.assertEqual(result['status'],'LOCAL_UNSAT');self.assertTrue(result['complete'])
        self.assertEqual(result['total_extensions'],0)
        raw=[sum(1<<(i*8+i) for i in indices) for indices in ((0,1),(2,3),(4,5),(6,),(7,))]
        missing=subject.solve_pair_image(raw,8,8,8)
        self.assertEqual(missing['status'],'UNKNOWN');self.assertFalse(missing['complete'])
        self.assertEqual(missing['case'],'conditional_backbone_bound_not_met')

    def test_late_prior_and_true_c3_sat_child_stay_raw_unknown(self):
        raw,n=diagonal_code(list(range(1,8))+[1]);actual=subject.solve_two
        for late_call in (1,2):
            with self.subTest(late_call=late_call):
                stop=[False];calls=[0]
                def delayed(*args,**kwargs):
                    result=actual(*args,**kwargs);calls[0]+=1
                    if calls[0]==late_call:stop[0]=True
                    return result
                with patch.object(subject,'solve_two',delayed):
                    result=subject.solve_pair_image(raw,n,n,8,cancelled=lambda:stop[0])
                self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
                field='last_prior_result' if late_call==1 else 'last_child_result'
                self.assertIn(field,result)
                if late_call==2:
                    self.assertEqual(result[field]['status'],'SAT');self.assertTrue(result[field]['support'])
                    self.assertEqual(result['extension_cursor'],0);self.assertEqual(result['tested_extensions'],[])


if __name__=='__main__':unittest.main()
