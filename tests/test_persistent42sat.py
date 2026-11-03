import importlib.util
import json
import multiprocessing as mp
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

from mmsearch.free_factor_sat import build_system
from mmsearch.local_eliminated42sat import build_problem,solve as fresh_solve
from mmsearch.persistent42sat import solve_staged
from mmsearch.recombine import canonical_terms
from mmsearch.tensor import naive_candidate,strassen_candidate
from scripts.campaign_persistent42sat import SOURCE_FILES

HAVE_SOLVER = bool(importlib.util.find_spec('pycryptosat') and importlib.util.find_spec('pysat'))


class SnapshotClosureTests(unittest.TestCase):
    def test_snapshot_lists_entire_local_import_closure(self):
        root = Path(__file__).resolve().parents[1]
        frozen = set(SOURCE_FILES)
        for relative in frozen:
            source = root/relative
            self.assertTrue(source.exists(),relative)
            module_parts = list(source.relative_to(root).with_suffix('').parts)
            for node in ast.walk(ast.parse(source.read_text())):
                if not isinstance(node,ast.ImportFrom):
                    continue
                if node.level:
                    prefix = module_parts[:-node.level]
                    parts = prefix+(node.module.split('.') if node.module else [])
                else:
                    parts = node.module.split('.') if node.module else []
                if parts and parts[0] in ['mmsearch','scripts']:
                    dependency = '/'.join(parts)+'.py'
                    self.assertIn(dependency,frozen,f'{relative} imports an unfrozen local module')


def planted_problem(rank=7):
    naive,planted = naive_candidate(2),strassen_candidate(2)
    dictionary = sorted(set(canonical_terms(naive))|set(canonical_terms(planted)))
    system = build_system(dictionary,2,'wu',naive)
    other = build_system(dictionary,2,'wu',planted)['baseline_vectors']
    free = [g for g,(a,b) in enumerate(zip(system['baseline_vectors'],other)) if a!=b]
    return build_problem(system,free,rank)


@unittest.skipUnless(HAVE_SOLVER,'optional native XOR backend unavailable')
class Persistent42Tests(unittest.TestCase):
    def test_inherited_hard_limits_are_never_raised(self):
        def under_limits(sender):
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
            resource.setrlimit(resource.RLIMIT_CPU,(5,5))
            result = solve_staged(planted_problem(),[.1,.1,1],conflict_limits=[0,1,100000],
                wall_seconds=2,memory_mb=1024)
            sender.send(result)
            sender.close()
        context = mp.get_context('fork')
        receiver,sender = context.Pipe(duplex=False)
        process = context.Process(target=under_limits,args=(sender,))
        process.start()
        sender.close()
        try:
            self.assertTrue(receiver.poll(3))
            result = receiver.recv()
        finally:
            process.join(timeout=.2)
            if process.is_alive():
                process.kill()
                process.join()
            receiver.close()
        self.assertEqual(result['status'],'SAT')
        self.assertEqual(result['identity']['effective_address_space_limit']['hard'],512*1024**2)
        self.assertEqual(result['identity']['effective_cpu_limit']['hard'],5)

    def test_real_unknown_then_sat_and_unsat_on_same_solver(self):
        for rank,expected in [(7,'SAT'),(6,'LOCAL_UNSAT')]:
            problem = planted_problem(rank)
            with tempfile.TemporaryDirectory() as directory:
                checkpoint = Path(directory)/'checkpoint.json'
                result = solve_staged(problem,[.1,.1,1],conflict_limits=[0,1,100000],
                    memory_mb=512,wall_seconds=2,checkpoint_path=checkpoint)
                self.assertEqual(result['status'],expected)
                self.assertEqual([x['status'] for x in result['slice_history']],['UNKNOWN','UNKNOWN',expected])
                self.assertEqual(len({x['identity']['solver_object_id'] for x in result['slice_history']}),1)
                self.assertEqual(result['formula_load_count'],1)
                self.assertTrue(result['worker_reaped'])
                saved = json.loads(checkpoint.read_text())
                self.assertFalse(saved['saved_solver_internal_state'])
                self.assertEqual(saved['state'],expected)
                fresh = fresh_solve(problem,seconds=2,memory_mb=512)
                self.assertEqual(result['status'],fresh['status'])
                if expected=='SAT':
                    self.assertEqual(result['verification']['rank'],7)
                    self.assertEqual(result['verification']['exact_entries_checked'],64)

    def test_hard_timeout_resets_inherited_stop_handler_and_reaps(self):
        def stall(*args):
            # The entry wrapper must reset this before a patched worker.
            self.assertEqual(signal.getsignal(signal.SIGTERM),signal.SIG_DFL)
            time.sleep(10)
        previous = signal.signal(signal.SIGTERM,lambda *_:None)
        try:
            with patch('mmsearch.persistent42sat._worker',stall):
                result = solve_staged(planted_problem(),[2],wall_seconds=.02,memory_mb=512)
            self.assertEqual(result['status'],'UNKNOWN')
            self.assertTrue(result['worker_reaped'])
            self.assertEqual(result['worker_exitcode'],-signal.SIGTERM)
            self.assertLess(result['elapsed_seconds'],.8)
        finally:
            signal.signal(signal.SIGTERM,previous)

    def test_cooperative_exhaustion_stays_unknown(self):
        result = solve_staged(planted_problem(),[.1,.1],conflict_limits=[0,0],
            wall_seconds=1,memory_mb=512)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual([x['status'] for x in result['slice_history']],['UNKNOWN','UNKNOWN'])
        self.assertTrue(result['worker_reaped'])

    def test_parent_stop_and_invalid_backend_are_not_unsat(self):
        result = solve_staged(planted_problem(),[2],wall_seconds=1,memory_mb=512,cancelled=lambda:True)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertTrue(result['worker_reaped'])
        result = solve_staged(planted_problem(),[.1],wall_seconds=1,memory_mb=512,
            options={'invalid-persistent42-option':'1'})
        self.assertEqual(result['status'],'ERROR')


if __name__=='__main__':
    unittest.main()
import ast
