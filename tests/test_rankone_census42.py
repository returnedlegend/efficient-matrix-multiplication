import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mmsearch import hyperplane_rankone42 as hp
from mmsearch import rankone_census42 as rc
from mmsearch.search import encode_candidate,naive_terms
from scripts.prototype_rankone_census42 import run_census,load_state


def ordered(terms):return dict(dimension=2,field=2,terms=[encode_candidate([t],2)['terms'][0]for t in terms])


def brute_pairs(source):
    # Exhaust2^8 coefficient combinations independently of SAT/elimination.
    columns=source['A_columns'];images={}
    for c in range(1,1<<len(columns)):
        value=0
        for i,col in enumerate(columns):
            if c>>i&1:value^=col
        assert value not in images;images[value]=c
    points=[]
    for a in range(1,16):
        for b in range(1,16):
            matrix=0
            for i in range(4):
                for j in range(4):matrix|=int(bool(a>>i&1)and bool(b>>j&1))<<(i*4+j)
            if matrix in images:points.append(dict(a=a,b=b,c=images[matrix]))
    return points


class RankOneCensusTests(unittest.TestCase):
    def schoolbook(self):return hp.prepare_source(ordered(naive_terms(2)),2)

    def test_schoolbook_exactly18_rankone_points_and_complete_oracle(self):
        source=self.schoolbook();brute=brute_pairs(source);self.assertEqual(len(brute),18)
        points,closure=rc.common_factor_closure(source,rc.initial_points(source))
        self.assertEqual(len(points),18);self.assertFalse(closure['census_complete'])
        self.assertEqual({p['c']for p in points},{p['c']for p in brute})
        result=rc.solve_oracle(rc.build_oracle(source,points),seconds=2,memory_mb=512,options={'seed':'2026110343201'})
        self.assertEqual(result['status'],'CENSUS_COMPLETE_UNSAT');self.assertTrue(result['worker_reaped'])
        self.assertEqual(result['requested_seed'],2026110343201)

    def test_individual_blocks_allow_dependent_new_points_and_reject_corruption(self):
        source=self.schoolbook();points=rc.initial_points(source);extra=next(p for p in brute_pairs(source)if p['c'].bit_count()>1)
        problem=rc.build_oracle(source,points);assignment=rc.witness_assignment(problem,extra)
        self.assertEqual(rc.validate_decode(problem,assignment)[0],extra)
        self.assertIsNotNone(hp.coordinates([p['c']for p in points],extra['c']))
        self.assertFalse(problem['metadata']['outside_span_constraint']);self.assertFalse(problem['metadata']['lambda_constraint'])
        blocked=rc.build_oracle(source,[*points,extra])
        with self.assertRaises(AssertionError):rc.validate_decode(blocked,rc.witness_assignment(blocked,extra))
        bad=list(assignment);bad[problem['gates'][0]]=not bad[problem['gates'][0]]
        with self.assertRaises(AssertionError):rc.validate_decode(problem,bad)
        with self.assertRaises(ValueError):rc.validate_points(source,[*points,points[0]])
        wrong=dict(extra,c=extra['c']^1)
        with self.assertRaises(ValueError):rc.validate_point(source,wrong)

    def test_saturated_common_factor_closure_can_still_be_incomplete(self):
        positive=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
        source=hp.prepare_source(ordered(positive),2)
        points,closure=rc.common_factor_closure(source,rc.initial_points(source))
        self.assertTrue(closure['closure_saturated']);self.assertFalse(closure['census_complete'])
        self.assertEqual((len(points),len(brute_pairs(source))),(10,11))
        result=rc.solve_oracle(rc.build_oracle(source,points),seconds=2,memory_mb=512)
        self.assertEqual(result['status'],'SAT');self.assertEqual(result['point'],dict(a=2,b=4,c=188))
        complete=rc.solve_oracle(rc.build_oracle(source,[*points,result['point']]),seconds=2,memory_mb=512)
        self.assertEqual(complete['status'],'CENSUS_COMPLETE_UNSAT')

    def test_full_enumeration_terminal_resume_unknown_cap_and_checkpoint_corruption(self):
        source=self.schoolbook()
        with tempfile.TemporaryDirectory() as directory:
            state=run_census(source,directory,seconds=10,oracle_seconds=2)
            self.assertEqual(state['status'],'CENSUS_COMPLETE');self.assertEqual(len(state['points']),18)
            self.assertEqual(state['oracle_attempts'],11)
            def forbidden(*args,**kwargs):raise AssertionError('complete census resubmitted')
            self.assertEqual(run_census(source,directory,oracle=forbidden)['status'],'CENSUS_COMPLETE')
            path=Path(directory)/'checkpoint.json';bad=json.loads(path.read_text());bad['points'][-1]['a']^=1
            bad.pop('checkpoint_sha256');bad['checkpoint_sha256']=hp.digest(bad);path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):load_state(directory,source,4096)
        with tempfile.TemporaryDirectory() as directory:
            unknown=run_census(source,directory,oracle=lambda *args,**kwargs:dict(status='UNKNOWN'))
            self.assertFalse(unknown['census_complete']);self.assertEqual(len(unknown['points']),8)
            resumed=run_census(source,directory,seconds=10,oracle_seconds=2,closure_rounds=3)
            self.assertTrue(resumed['census_complete']);self.assertEqual(len(resumed['points']),18)
        with tempfile.TemporaryDirectory() as directory:
            capped=run_census(source,directory,cap=8)
            self.assertEqual(capped['status'],'POINT_CAP');self.assertFalse(capped['census_complete'])

    def test_exact5x5_dispatch_is_disabled_and_nonfull_A_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'full column rank'):
            hp.prepare_linear([(1,1),(1,1)],[1,1],4)
        source=self.schoolbook();bad=copy.deepcopy(source);bad['A_rank']=7
        with self.assertRaises(ValueError):rc.initial_points(bad)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sourcefile=root/'n5.json'
            # An exact old93 reference is accepted for prepare-only, never for
            # this prototype's solver-dispatch CLI without small-control mode.
            original=Path(__file__).resolve().parents[1]/'artifacts/km93_f2.json';sourcefile.write_bytes(original.read_bytes())
            script=Path(__file__).resolve().parents[1]/'scripts/prototype_rankone_census42.py'
            result=subprocess.run([sys.executable,str(script),'--source',str(sourcefile),'--output-dir',str(root/'out')],capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,2);self.assertIn('does not dispatch n5 SAT',result.stderr)


if __name__=='__main__':unittest.main()
