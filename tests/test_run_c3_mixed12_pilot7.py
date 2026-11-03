import json
from pathlib import Path
import tempfile
import unittest
from mmsearch.search import naive_terms,encode_candidate
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.compact_coset43 import expand_products,mode_slices
from mmsearch.sat_neighborhoods import gf2_rank
from scripts.run_c3_mixed12_pilot7 import reviewed_solver,run_case
from tests.test_run_c3_mixed9_pilot7 import Guard


def planted(root,k,target):
    naive=list(naive_terms(3));latin=[]
    for i in range(3):
        for j in range(3):
            z=(i+j)%3;latin.append((1<<(3*i+j),1<<(3*j+z),1<<(3*z+i)))
    selected=latin[:k];packet=[]
    for i,term in enumerate(selected):
        if i<12-k:
            other=selected[(i+4)%k][2];packet.extend([(term[0],term[1],term[2]^other),(term[0],term[1],other)])
        else:packet.append(term)
    outside=[term for term in naive if term not in selected];source=encode_candidate(outside+packet,3);(root/'source.json').write_text(json.dumps(source));terms=factor_masks(source)
    return {'id':f'whole-n3-d{k}-t{target}','source':'source.json','source_products':len(source['terms']),'source_local_products':12,'source_indices':sorted(terms.index(term) for term in packet),'target_local_products':target,'shape':[k]*3,'mode_rank':k,'free_axis':0}


class Mixed12PilotControls(unittest.TestCase):
    def test_full_n3_positive_cp_d_one_and_two_routes(self):
        for k,target in [(8,8),(8,9),(9,11)]:
            with self.subTest(k=k,target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);case=planted(root,k,target);result=run_case(SourceCache(root),case,root/'out',Guard(),control_expected_rank=27)
                self.assertEqual(result['status'],'SMALL_CONTROL_PASSED',result);self.assertEqual(result['candidate_rank'],27)
                self.assertEqual(result['primary']['exact_entries_checked'],729);self.assertEqual(result['independent']['exact_entries_checked'],729)

    def test_genuine_surplus_two_positive_has_independent_flattening_witness(self):
        values=[33,33792];core=[(value>>i)&1 for value in values for i in range(16)];shape=[2,4,4]
        result=reviewed_solver(core,shape,4,axis=0,cancelled=lambda:False)
        self.assertEqual(result['status'],'SAT');self.assertEqual(result['case'],'repeated_coset_pair_extension')
        self.assertEqual(expand_products(result['products'],shape),core)
        self.assertEqual(max(gf2_rank(mode_slices(core,shape,a)[0]) for a in range(3)),4)

    def test_late_positive_and_error_remain_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);case=planted(root,9,11);guard=Guard()
            def late(*args,**kwargs):
                result=reviewed_solver(*args,**kwargs);guard.now=21;return result
            result=run_case(SourceCache(root),case,root/'late',guard,solver=late,control_expected_rank=27)
            self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete']);self.assertFalse((root/'late/records').exists());self.assertTrue(list((root/'late/.raw-returns').glob('*.raw')))
            def broken(*args,**kwargs):raise RuntimeError('planted error')
            result=run_case(SourceCache(root),case,root/'error',Guard(),solver=broken,control_expected_rank=27)
            self.assertEqual(result['status'],'ERROR');self.assertFalse(result['complete']);self.assertFalse((root/'error/records').exists())

if __name__=='__main__':unittest.main()
