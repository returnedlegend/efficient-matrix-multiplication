import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import subprocess
import sys
import unittest
from unittest.mock import patch

from mmsearch import hyperplane_rankone42 as hp
from mmsearch.search import encode_candidate,naive_terms
from mmsearch.verify import verify_candidate
from scripts.campaign_hyperplane_rankone42 import run_family,load_state

POSITIVE=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]


def ordered(terms,n=2):
    return dict(field=2,dimension=n,terms=[encode_candidate([term],n)['terms'][0]for term in terms])


def positive(rotation=0):
    terms=[term[rotation:]+term[:rotation]for term in POSITIVE]
    return hp.build_family(hp.prepare_source(ordered(terms),(2-rotation)%3),7)


def slow_worker(*args):time.sleep(.3)
def failed_worker(*args):os._exit(17)


class HyperplaneTests(unittest.TestCase):
    def test_mandatory_positive_two_points_and_full_decode_all_axes(self):
        for rotation in range(3):
            family=positive(rotation);self.assertEqual(family['source']['A_rank'],8)
            self.assertEqual(len(family['initial_coefficients']),5)
            with tempfile.TemporaryDirectory() as directory:
                state=run_family(family,directory,oracle_seconds=2,memory_mb=256,seed=429051)
                self.assertEqual(state['status'],'WINNER',state);self.assertEqual(len(state['points']),2)
                candidate,report=hp.decode_containment(family,state['points'])
                self.assertEqual((report['rank'],report['exact_entries_checked']),(7,64))
                self.assertTrue(verify_candidate(candidate,random_trials=8)['valid'])
                def forbidden(*args,**kwargs):raise AssertionError('terminal winner reran oracle')
                self.assertEqual(run_family(family,directory,oracle=forbidden)['status'],'WINNER')
        family=positive();points=[dict(a=12,b=1,c=5),dict(a=1,b=10,c=6)]
        self.assertEqual(hp.decode_containment(family,points)[1]['rank'],7)

    def test_schoolbook_negative_is_local_despite_global_strassen7(self):
        source=hp.prepare_source(ordered(naive_terms(2)),2)
        selected=[i for i,w in enumerate(source['W_rows'])if w==1]
        family=hp.build_family(source,sum(1<<i for i in selected));self.assertEqual(len(selected),2)
        with tempfile.TemporaryDirectory() as directory:
            state=run_family(family,directory,oracle_seconds=2,memory_mb=256)
            self.assertEqual(state['status'],'HYPERPLANE_SPAN_UNSAT');self.assertEqual(state['points'],[])
            self.assertIn('not unrestricted tensor rank',state['scope'])
            self.assertFalse((Path(directory)/'WINNER.json').exists())
            self.assertEqual(load_state(directory,family)['status'],'HYPERPLANE_SPAN_UNSAT')
            path=Path(directory)/'checkpoint.json';saved=json.loads(path.read_text())
            saved['history'][-1]['formula_sha256']='0'*64;saved.pop('checkpoint_sha256')
            saved['checkpoint_sha256']=hp.digest(saved);path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError,'formula/U provenance'):load_state(directory,family)
        strassen=[(12,1,10),(1,10,12),*POSITIVE[3:]]
        self.assertEqual(len(strassen),7);self.assertTrue(verify_candidate(ordered(strassen),random_trials=8)['valid'])

    def test_generic_tiny_oracle_span_matches_bruteforce(self):
        pairs=[(1,1),(1,2),(2,1),(2,2)]
        for lam in range(1,16):
            target=hp.nullspace([lam],4)[:2]
            free=[sum(((c>>r)&1)<<j for j,c in enumerate(target))for r in range(4)]
            source=hp.prepare_linear(pairs,free,2);family=hp.build_family(source,lam)
            brute=[]
            for a in range(1,4):
                for b in range(1,4):
                    c=hp.coordinates(source['A_columns'],hp.pair_column(a,b,2))
                    if (c&lam).bit_count()%2==0:brute.append(c)
            expected=hp.contained(family,brute)
            with tempfile.TemporaryDirectory() as directory:
                state=run_family(family,directory,oracle_seconds=1,memory_mb=256)
                self.assertEqual(state['status']=='SPANNED_CONTROL',expected,(lam,state))
                self.assertIn(state['status'],{'SPANNED_CONTROL','HYPERPLANE_SPAN_UNSAT'})
                self.assertFalse((Path(directory)/'WINNER.json').exists())

    def test_point_formula_corruption_rank_increase_and_dependent_A(self):
        family=positive();problem=hp.build_oracle(family);point=dict(a=12,b=1,c=5)
        assignment=hp.witness_assignment(problem,point)
        self.assertEqual(hp.validate_decode(problem,assignment)[0],point)
        bad=list(assignment);bad[problem['gates'][0]]=not bad[problem['gates'][0]]
        with self.assertRaises(AssertionError):hp.validate_decode(problem,bad)
        bad=list(assignment);bad[1]=1
        with self.assertRaises(AssertionError):hp.validate_decode(problem,bad)
        with self.assertRaises(ValueError):hp.validate_point(family,family['initial_coefficients'],dict(a=12,b=1,c=6))
        with self.assertRaises(ValueError):hp.validate_point(family,[*family['initial_coefficients'],5],point)
        with self.assertRaises(ValueError):hp.build_family(family['source'],1)
        dependent=[(13,1,2),(13,1,8),*POSITIVE[1:]]
        self.assertTrue(verify_candidate(ordered(dependent),random_trials=0)['valid'])
        with self.assertRaisesRegex(ValueError,'full column rank'):hp.prepare_source(ordered(dependent),2)

    def test_unknown_points_resume_error_terminal_and_corrupt_checkpoints(self):
        family=positive();calls=[]
        def partial(problem,**kwargs):
            calls.append(1)
            return dict(status='SAT',point=dict(a=12,b=1,c=5))if len(calls)==1 else dict(status='UNKNOWN')
        with tempfile.TemporaryDirectory() as directory:
            first=run_family(family,directory,oracle=partial)
            self.assertEqual((first['status'],len(first['points'])),('UNKNOWN',1))
            second=run_family(family,directory,oracle_seconds=2,memory_mb=256)
            self.assertEqual((second['status'],second['oracle_attempts']),('WINNER',3))
            path=Path(directory)/'checkpoint.json';state=json.loads(path.read_text());state['points'][0]['c']=6
            state.pop('checkpoint_sha256');state['checkpoint_sha256']=hp.digest(state);path.write_text(json.dumps(state))
            with self.assertRaises(ValueError):load_state(directory,family)
        with tempfile.TemporaryDirectory() as directory:
            def error(*args,**kwargs):return dict(status='ERROR',error='planted worker error')
            self.assertEqual(run_family(family,directory,oracle=error)['status'],'ERROR')
            def forbidden(*args,**kwargs):raise AssertionError('terminal ERROR retried')
            self.assertEqual(run_family(family,directory,oracle=forbidden)['status'],'ERROR')

    def test_timeout_worker_error_and_physical_H_dedup(self):
        problem=hp.build_oracle(positive())
        with patch('mmsearch.local_eliminated42sat._worker',slow_worker):
            result=hp.solve_oracle(problem,seconds=.01,memory_mb=256)
        self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped'])
        with patch('mmsearch.local_eliminated42sat._worker',failed_worker):
            result=hp.solve_oracle(problem,seconds=1,memory_mb=256)
        self.assertEqual(result['status'],'ERROR');self.assertEqual(result['worker_exitcode'],17)
        self.assertTrue(result['worker_reaped'])
        a=hp.prepare_linear([(1,1),(1,2),(2,1),(2,2)],[1,2,3,0],2)
        b=hp.prepare_linear(list(reversed(a['pairs'])),list(reversed(a['W_rows'])),2)
        self.assertEqual(hp.build_family(a,7)['physical_H_sha256'],hp.build_family(b,14)['physical_H_sha256'])

    def test_actual_large_proposed_cli_seed_and_terminal_error_exit(self):
        requested=2026110342905;family=positive();candidate=ordered(POSITIVE)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.json';source.write_text(json.dumps(candidate))
            cases=root/'cases';cases.mkdir()
            spec=dict(source_path=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      free_axis=2,lambda_mask=7,physical_H_sha256=family['physical_H_sha256'])
            (cases/'case-00.json').write_text(json.dumps(spec))
            script=Path(__file__).resolve().parents[1]/'scripts/campaign_hyperplane_rankone42.py'
            base=[sys.executable,str(script),'--cases-dir',str(cases),'--seconds','10',
                  '--oracle-seconds','2','--memory-mb','256','--seed',str(requested)]
            output=root/'positive'
            done=subprocess.run([*base,'--output-dir',str(output)],capture_output=True,text=True,timeout=5)
            self.assertEqual(done.returncode,0,done.stderr)
            summary=json.loads((output/'summary.json').read_text())
            self.assertEqual((summary['status'],summary['error_count']),('WINNER',0))
            for index in range(2):
                result=json.loads((output/f'case-00/oracle-{index:03d}/result.json').read_text())
                self.assertEqual(result['requested_seed'],requested+index)
                self.assertEqual(result['solver_seed'],(requested+index)%2147483647)
                self.assertEqual(result['solver_options']['seed'],str(result['solver_seed']))
                self.assertEqual(result['status'],'SAT')
            failed=root/'failed';failed.mkdir()
            run_family(family,failed/'case-00',oracle=lambda *args,**kwargs:dict(status='ERROR',error='planted terminal worker failure'))
            done=subprocess.run([*base,'--output-dir',str(failed)],capture_output=True,text=True,timeout=5)
            self.assertEqual(done.returncode,2,done.stderr)
            summary=json.loads((failed/'summary.json').read_text())
            self.assertEqual((summary['status'],summary['error_count'],summary['hyperplane_only_unsat_count']),('ERROR',1,0))


if __name__=='__main__':unittest.main()
