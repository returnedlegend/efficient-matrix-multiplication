import hashlib
import importlib.util
import json
import signal
from pathlib import Path
import tempfile
import unittest

from mmsearch.cyclic_orbit_sat import build_repair,solve_patch
from mmsearch.search import _rotations,encode_candidate
from scripts.campaign_cyclic_orbit_sat import run_portfolio


AVAILABLE=importlib.util.find_spec('pycryptosat') is not None or importlib.util.find_spec('pysat') is not None


def planted_parent():
    terms={(1,1,1),(8,8,8)}
    for term in ((9,2,4),(8,2,6),(8,6,2)):
        terms.update(_rotations(term))
    candidate=encode_candidate(terms,2)
    raw=json.dumps(candidate,sort_keys=True).encode()
    return dict(candidate=candidate,raw_sha256=hashlib.sha256(raw).hexdigest())


def control_build(candidate,indices,**kwargs):
    return build_repair(candidate,indices,strict95=False,**kwargs)


class CyclicCampaignTests(unittest.TestCase):
    @unittest.skipUnless(AVAILABLE,'optional SAT backend unavailable')
    def test_real_planted_positive_control_frozen_and_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=run_portfolio([planted_parent()],root,seconds=5,patch_seconds=1,k_min=3,k_max=3,
                                 build_fn=control_build,install_signals=False)
            self.assertEqual(result['status'],'SAT',result)
            report=json.loads((root/'WINNER.verification.json').read_text())
            self.assertTrue(report['valid']);self.assertEqual(report['exact_entries_checked'],64)
            self.assertLessEqual(report['rank'],8)
            self.assertFalse((root/'WINNER.json').stat().st_mode & 0o222)

    def test_unknown_patch_is_cached_across_resume_and_never_retried(self):
        calls=[]
        def unknown(problem,**kwargs):
            calls.append(problem['metadata']['orbit_indices'])
            return dict(status='UNKNOWN',reason='mock conflict limit',elapsed_seconds=.01)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);parents=[planted_parent()]
            first=run_portfolio(parents,root,seconds=5,k_min=3,k_max=3,
                                build_fn=control_build,solver_fn=unknown,install_signals=False)
            self.assertEqual(first['counts']['UNKNOWN'],1)
            self.assertEqual(len(calls),1)
            # Simulate a stale periodic state cursor: event replay must still
            # prevent a second solve of the same unchanged patch.
            state=json.loads((root/'state.json').read_text());state['cursor']=0;state['seen']=[]
            (root/'state.json').write_text(json.dumps(state))
            resumed=run_portfolio(parents,root,seconds=5,k_min=3,k_max=3,resume=True,
                                  build_fn=control_build,solver_fn=unknown,install_signals=False)
            self.assertEqual(len(calls),1)
            self.assertEqual(resumed['cached_patches'],1)
            self.assertEqual(len((root/'events.jsonl').read_text().splitlines()),1)

    def test_cleanup_reserve_prevents_solver_and_saves_restart_state(self):
        def forbidden(*args,**kwargs):
            self.fail('solver must not start within cleanup reserve')
        with tempfile.TemporaryDirectory() as directory:
            result=run_portfolio([planted_parent()],Path(directory),seconds=1,k_min=3,k_max=3,
                                 solver_fn=forbidden,install_signals=False)
            self.assertEqual(result['status'],'WALL_BUDGET')
            self.assertEqual(result['attempts'],0)
            self.assertTrue((Path(directory)/'state.json').exists())

    def test_solver_unsat_and_error_are_logged_with_local_status(self):
        for backend_status,expected in (('UNSAT','LOCAL_UNSAT'),('ERROR','ERROR')):
            with self.subTest(status=backend_status),tempfile.TemporaryDirectory() as directory:
                def solver(problem,**kwargs):
                    return dict(status=backend_status,error='mock backend result')
                root=Path(directory)
                result=run_portfolio([planted_parent()],root,seconds=5,k_min=3,k_max=3,
                                     build_fn=control_build,solver_fn=solver,install_signals=False)
                self.assertEqual(result['counts'][expected],1)
                event=json.loads((root/'events.jsonl').read_text().splitlines()[0])
                self.assertEqual(event['status'],expected)
                self.assertIn('no global UNSAT',json.loads((root/'summary.json').read_text())['scope'])

    def test_sigterm_during_case_records_unknown_and_saves_clean_state(self):
        def interrupted(problem,**kwargs):
            signal.raise_signal(signal.SIGTERM)
            self.fail('signal must unwind the active case')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result=run_portfolio([planted_parent()],root,seconds=5,k_min=3,k_max=3,
                                 build_fn=control_build,solver_fn=interrupted)
            self.assertEqual(result['status'],'STOPPED')
            self.assertEqual(result['counts']['UNKNOWN'],1)
            state=json.loads((root/'state.json').read_text())
            self.assertEqual(state['status'],'STOPPED')
            self.assertEqual(len(state['seen']),1)


if __name__=='__main__':
    unittest.main()
