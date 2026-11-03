"""True-c2 rank12 whole-N4 controls, with no N5 decoder inputs."""
import json,tempfile,unittest
from pathlib import Path
from mmsearch.search import naive_terms,encode_candidate
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.compact_eight43 import factor_core,opposite_pair_ranks
from mmsearch.compact_rank2_edges43 import solve_core as lower
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.surplus_two_large7 import solve_core
from scripts.run_c3_mixed15_exact7 import run_case
from tests.test_run_c3_mixed9_pilot7 import Guard

def planted(root):
    block={0,1,4,5};triples=[(i,j,k) for i in range(2) for j in range(2) for k in range(2) if (i,j,k)!=(0,0,0)]
    extras=[(i,j,(i+j)%4) for i in range(4) for j in range(4) if all(x not in block for x in (4*i+j,4*j+(i+j)%4,4*((i+j)%4)+i))]
    if len(extras)<8:raise AssertionError('need8 independent isolated coordinate products')
    triples+=extras[:8];selected=[(1<<(4*i+j),1<<(4*j+k),1<<(4*k+i)) for i,j,k in triples];source=encode_candidate(list(naive_terms(4)),4);terms=factor_masks(source);indices=sorted(terms.index(t) for t in selected);(root/'source.json').write_text(json.dumps(source))
    return source,terms,dict(id='n4-truec2-d12',source='source.json',source_products=64,source_local_products=15,source_indices=indices,target_local_products=14,shape=[12]*3,mode_rank=12,free_axis=0)

def solver(core,shape,target,**kwargs):
    kwargs.pop('max_vectors',None)
    return solve_core(core,shape,target,max_vectors=8191,max_extensions=24573,max_mode_rank=12,timeout_seconds=10,**kwargs)

class LargerModePlantedControls(unittest.TestCase):
    def test_true_c2_whole_n4_d12_lift_and_two_full_verifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,terms,case=planted(root);ids=case['source_indices'];self.assertEqual(opposite_pair_ranks(terms,16),[64]*3);self.assertEqual(opposite_pair_ranks([terms[i] for i in ids],16),[15]*3)
            _,core,shape=factor_core(terms,ids);self.assertEqual(shape,[12]*3);r=lower(core,shape,13,max_vectors=8191);self.assertEqual(r['status'],'LOCAL_UNSAT');self.assertTrue(r['complete'])
            r=run_case(SourceCache(root),case,root/'out',Guard(),solver=solver,control_expected_rank=63)
            self.assertEqual(r['status'],'SMALL_CONTROL_PASSED',r);self.assertEqual(r['decoder_case'],'repeated_coset_pair_extension');self.assertEqual(r['candidate_rank'],63);self.assertEqual(r['primary']['exact_entries_checked'],4096);self.assertEqual(r['independent']['exact_entries_checked'],4096)
    def test_caps_and_late_d12_positive_are_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,terms,case=planted(root);_,core,shape=factor_core(terms,case['source_indices'])
            for kwargs in [dict(max_vectors=4094),dict(max_extensions=0),dict(max_mode_rank=11),dict(timeout_seconds=0)]:
                r=solve_core(core,shape,14,**kwargs);self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(r['complete'])
            guard=Guard()
            def late(*a,**kw):
                r=solver(*a,**kw);guard.now=21;return r
            r=run_case(SourceCache(root),case,root/'late',guard,solver=late,control_expected_rank=63)
            self.assertEqual(r['status'],'UNKNOWN');self.assertFalse((root/'late/records').exists());self.assertTrue(list((root/'late/.raw-returns').glob('*.raw')))

if __name__=='__main__':unittest.main()
