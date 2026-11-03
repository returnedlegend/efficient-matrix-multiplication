import json,tempfile,unittest
from pathlib import Path
from functools import reduce
from mmsearch.search import naive_terms,encode_candidate
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.compact_eight43 import packed_tensor
from mmsearch.compact_coset43 import expand_products
from mmsearch.compact_rank2_edges43 import solve_core
from scripts.run_c3_mixed15_exact7 import run_case,reviewed_solver
from tests.test_run_c3_mixed9_pilot7 import Guard

def planted(root,k):
    allterms=list(naive_terms(4));latin=[(1<<(i*4+j),1<<(j*4+((i+j)%4)),1<<(((i+j)%4)*4+i)) for i in range(4) for j in range(4)]
    selected=latin[:k];packet=[]
    for i,term in enumerate(selected):
        if i<15-k:
            w=selected[(i+4)%k][2];packet.extend([(term[0],term[1],term[2]^w),(term[0],term[1],w)])
        else:packet.append(term)
    source=encode_candidate([t for t in allterms if t not in selected]+packet,4);(root/'source.json').write_text(json.dumps(source));terms=factor_masks(source)
    return dict(id='n4-d'+str(k),source='source.json',source_products=len(terms),source_local_products=15,source_indices=sorted(terms.index(t) for t in packet),target_local_products=14,shape=[k]*3,mode_rank=k,free_axis=0)

class Mixed15Controls(unittest.TestCase):
    def test_matching_d13_d14_full_matrix_gates(self):
        for d in (13,14):
            with self.subTest(d=d),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);case=planted(root,d);r=run_case(SourceCache(root),case,root/'out',Guard(),control_expected_rank=64)
                self.assertEqual(r['status'],'SMALL_CONTROL_PASSED',r);self.assertEqual(r['primary']['exact_entries_checked'],4096);self.assertEqual(r['independent']['exact_entries_checked'],4096)
    def test_true_d13_plus_one_gadget(self):
        d=13;terms=[(1,1,1),(1,2,2),(2,1,2),(2,2,1)]+[(1<<i,1<<i,1<<i) for i in range(2,d)]
        packed=reduce(int.__xor__,(packed_tensor(t,d) for t in terms));core=[(packed>>i)&1 for i in range(d**3)]
        self.assertEqual(solve_core(core,[d]*3,d,max_vectors=65535)['status'],'LOCAL_UNSAT')
        r=reviewed_solver(core,[d]*3,14,cancelled=lambda:False);self.assertEqual(r['status'],'SAT');self.assertEqual(len(r['products']),14);self.assertEqual(expand_products(r['products'],[d]*3),core)
    def test_late_d13_positive_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);case=planted(root,13);g=Guard()
            def late(*a,**kw):
                r=reviewed_solver(*a,**kw);g.now=21;return r
            r=run_case(SourceCache(root),case,root/'out',g,solver=late,control_expected_rank=64)
            self.assertEqual(r['status'],'UNKNOWN');self.assertFalse((root/'out/records').exists());self.assertTrue(list((root/'out/.raw-returns').glob('*.raw')))

if __name__=='__main__':unittest.main()
