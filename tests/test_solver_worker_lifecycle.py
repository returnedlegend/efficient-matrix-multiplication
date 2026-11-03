from contextlib import contextmanager
import importlib.util
import multiprocessing as mp
import signal
import time
import unittest
from unittest.mock import patch

from mmsearch.free_factor_sat import build_problem,build_system,solve
from mmsearch.tensor import strassen_candidate
from mmsearch.verify import verify_candidate
from mmsearch.xor_sat import build_xor_cnf,solve_local


@contextmanager
def custom_parent_handlers():
    previous={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
    def keep_running(_sig,_frame):
        pass
    for sig in previous:signal.signal(sig,keep_running)
    try:
        yield keep_running
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


class SolverWorkerLifecycleTests(unittest.TestCase):
    def tiny_cases(self):
        # Mock-worker tests need no optional SAT packages or formula construction.
        free=dict(nv=1,metadata=dict(formula_sha256='lifecycle-only',scope='mock timeout control only'))
        yield 'mmsearch.free_factor_sat._worker',lambda:solve(free,seconds=.02,memory_mb=512)
        yield 'mmsearch.xor_sat._worker',lambda:solve_local({},seconds=.02,conflicts=1)

    def test_entry_resets_both_child_signals_without_changing_parent(self):
        def probe(*args):
            connection=args[-1]
            connection.send(dict(status='UNKNOWN',term_default=signal.getsignal(signal.SIGTERM)==signal.SIG_DFL,
                int_default=signal.getsignal(signal.SIGINT)==signal.SIG_DFL))
            connection.close()
        for target,run in self.tiny_cases():
            with self.subTest(worker=target),custom_parent_handlers() as parent:
                with patch(target,probe):result=run()
                self.assertTrue(result['term_default'])
                self.assertTrue(result['int_default'])
                self.assertIs(signal.getsignal(signal.SIGTERM),parent)
                self.assertIs(signal.getsignal(signal.SIGINT),parent)

    def test_hard_timeout_reaps_child_under_inherited_stop_handlers(self):
        def blocked(*_args):time.sleep(5)
        for target,run in self.tiny_cases():
            with self.subTest(worker=target),custom_parent_handlers() as parent:
                before={process.pid for process in mp.active_children()}
                started=time.monotonic()
                with patch(target,blocked):result=run()
                self.assertEqual(result['status'],'UNKNOWN')
                self.assertLess(time.monotonic()-started,.5)
                self.assertFalse({process.pid for process in mp.active_children()}-before)
                self.assertIs(signal.getsignal(signal.SIGTERM),parent)

    @unittest.skipUnless(importlib.util.find_spec('pycryptosat') and importlib.util.find_spec('pysat'),'optional native XOR dependencies')
    def test_real_sat_and_exact_decoding_unchanged_under_custom_handlers(self):
        with custom_parent_handlers() as parent:
            result=solve(build_problem(build_system([(1,1,1)],1),1),seconds=1,memory_mb=512)
            self.assertEqual(result['status'],'SAT')
            self.assertTrue(verify_candidate(result['candidate'])['valid'])
            planted=strassen_candidate(2)
            planted['terms'].append({axis:[0]*4 for axis in ('u','v','w')})
            problem=build_xor_cnf(planted,rank=7,active_terms=[0],drop_term=7)
            result=solve_local(problem,seconds=1,conflicts=10000)
            self.assertEqual(result['status'],'SAT')
            self.assertTrue(verify_candidate(result['candidate'])['valid'])
            self.assertEqual(result['verification']['exact_entries_checked'],64)
            self.assertIs(signal.getsignal(signal.SIGTERM),parent)


if __name__=='__main__':unittest.main()
