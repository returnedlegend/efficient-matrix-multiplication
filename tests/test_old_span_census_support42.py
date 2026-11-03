import copy
from pathlib import Path
import tempfile
import time
import unittest

from mmsearch import hyperplane_rankone42 as hp,rankone_census42 as rc,old_span_support42 as support
from scripts.prepare_rankone_census42 import ordered,brute
from scripts.campaign_old_span_census_support42 import run_case,census,save_problem,ArtifactHold
from scripts.prototype_rankone_census42 import checkpoint,load_state

POS=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]


class Resources:
    def __init__(self,paused=False):self.deadline=time.monotonic()+10;self.reason=None;self.paused=paused
    def sample(self):self.reason='TEST_HOLD'if self.paused else None;return self.reason
    def cancelled(self):return bool(self.reason)


def points_for(source):
    points=rc.initial_points(source);known={p['c']for p in points}
    return points+[p for p in brute(source)if p['c']not in known]


class OldSpanControls(unittest.TestCase):
    def test_all_axes_support_and_corruption(self):
        candidate=ordered(POS)
        for axis in range(3):
            source=hp.prepare_source(candidate,axis);points=points_for(source)
            problem=support.build_problem(candidate,source,points,7)
            answer=support.solve(problem,seconds=2,memory_mb=512,options={'seed':'2026110343301'})
            self.assertEqual(answer['status'],'SAT');self.assertEqual(answer['verification']['rank'],7)
            self.assertEqual(answer['solver_seed'],2026110343301%2147483647)
            bad=copy.deepcopy(problem);bad['coefficient_system']['W_rows'][0]^=1
            with self.assertRaises(AssertionError):support.validate_decode(bad,answer['complete_assignment'])
            assignment=list(answer['complete_assignment']);assignment[1]=not assignment[1]
            with self.assertRaises(AssertionError):support.validate_decode(problem,assignment)
            badpoint=copy.deepcopy(points);badpoint[-1]['c']^=1
            with self.assertRaises(ValueError):support.build_problem(candidate,source,badpoint,7)

    def test_partial_support_scope_and_resume(self):
        candidate=ordered(POS);source=hp.prepare_source(candidate,2)
        with tempfile.TemporaryDirectory()as tmp:
            out=Path(tmp);state=dict(status='PARTIAL',points=rc.initial_points(source),oracle_attempts=0,history=[],census_complete=False)
            (out/'census').mkdir();checkpoint(out/'census',source,state)
            a=run_case(candidate,source,out,Resources(),target=7,skip_census=True)
            self.assertEqual(a['status'],'PARTIAL_CATALOG_UNSAT');self.assertEqual(a['support_queries'],1)
            a=run_case(candidate,source,out,Resources(),target=7,skip_census=True)
            self.assertEqual(a['support_queries'],0);self.assertTrue(a['support_reused'])
            state['points'],_=rc.common_factor_closure(source,state['points']);checkpoint(out/'census',source,state)
            a=run_case(candidate,source,out,Resources(),target=7,skip_census=True)
            self.assertEqual(a['status'],'WINNER');self.assertFalse(a['census_complete'])
            a=run_case(candidate,source,out,Resources(),target=7,skip_census=True)
            self.assertEqual(a['status'],'WINNER');self.assertEqual(a['support_queries'],0)
            # Simulate a crash after export sidecars but before the final marker.
            (out/'WINNER.json').unlink()
            a=run_case(candidate,source,out,Resources(),target=7,skip_census=True)
            self.assertEqual(a['status'],'WINNER');self.assertEqual(a['support_queries'],0)

    def test_resource_hold_and_checkpoint_corruption(self):
        source=hp.prepare_source(ordered(POS),2)
        with tempfile.TemporaryDirectory()as tmp:
            result=run_case(ordered(POS),source,Path(tmp),Resources(True),target=7)
            self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(result['census_oracle_queries'],0)
            self.assertEqual(result['support_queries'],0)
            path=Path(tmp)/'census/checkpoint.json';path.write_text(path.read_text().replace('UNKNOWN','ERROR'))
            with self.assertRaises(ValueError):load_state(path.parent,source,4096)

    def test_error_unknown_and_artifact_bound(self):
        source=hp.prepare_source(ordered(POS),2)
        def unknown(problem,**kwargs):return dict(status='UNKNOWN',formula_sha256=problem['metadata']['formula_sha256'])
        def error(problem,**kwargs):return dict(status='ERROR',error='planted worker failure',formula_sha256=problem['metadata']['formula_sha256'])
        with tempfile.TemporaryDirectory()as tmp:
            kw=dict(seconds=1,oracle_seconds=1,seed=2026110343301,cap=4096,memory_mb=1536,closure_rounds=0)
            state,count=census(source,Path(tmp)/'unknown',Resources(),oracle=unknown,**kw)
            self.assertEqual((state['status'],count),('UNKNOWN',1));self.assertEqual(len(state['points']),8)
            state,count=census(source,Path(tmp)/'error',Resources(),oracle=error,**kw)
            self.assertEqual((state['status'],count),('ERROR',1))
            state,count=census(source,Path(tmp)/'error',Resources(),oracle=unknown,**kw)
            self.assertEqual((state['status'],count),('ERROR',0))
            with self.assertRaises(ArtifactHold):save_problem(Path(tmp)/'capped.gz',{'test':list(range(1000))},max_bytes=10)


if __name__=='__main__':unittest.main()
