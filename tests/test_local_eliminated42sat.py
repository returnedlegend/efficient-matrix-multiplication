import itertools
import importlib.util
import json
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch

from mmsearch.free_factor_sat import build_problem as global_problem,build_system,solve as global_solve
from mmsearch.local_eliminated42sat import baseline_assumptions,build_problem,solve,validate_decode
from mmsearch.local_free_factor_sat import local_assumptions
from mmsearch.recombine import canonical_terms,digest
from mmsearch.tensor import naive_candidate,strassen_candidate
from scripts.campaign_local_eliminated42sat import source_plan

HAVE_SOLVER = bool(importlib.util.find_spec('pycryptosat') and importlib.util.find_spec('pysat'))


class Eliminated42Tests(unittest.TestCase):
    def test_selection_uses_final_result_and_excludes_proved_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'queries').mkdir()
            (root/'neighborhoods.json').write_text(json.dumps([dict(free_groups=[0]),dict(free_groups=[1])]))
            for name,status in [('p0-0000','UNKNOWN'),('p1-0000','LOCAL_UNSAT'),('p0-0001','UNKNOWN')]:
                (root/'queries'/(name+'.result.json')).write_text(json.dumps(dict(status=status)))
            self.assertEqual([x['previous_index'] for x in source_plan(root,None)],[1])
            with self.assertRaises(ValueError):
                source_plan(root,[0])

    def planted(self):
        baseline,planted = naive_candidate(2),strassen_candidate(2)
        dictionary = sorted(set(canonical_terms(baseline))|set(canonical_terms(planted))|{(15,1,15)})
        system = build_system(dictionary,2,'wu',baseline)
        other = build_system(dictionary,2,'wu',planted)['baseline_vectors']
        free = [g for g,(a,b) in enumerate(zip(system['baseline_vectors'],other)) if a!=b]
        return system,free

    def test_exhaustive_reduced_formula_with_forced_substitution(self):
        # One forced group and two genuinely free groups. At rank3 there are
        # no cardinality auxiliaries, allowing exhaustive formula comparison.
        system = dict(pairs=[(1,1)]*3,coefficients=[7,6],right_sides=[1,0],
            baseline_vectors=[1,1,1],metadata=dict(width=1,pairs_sha256=digest('synthetic')))
        for free in [[],[0],[1,2],[0,1,2]]:
            problem = build_problem(system,free,3)
            for values in itertools.product([False,True],repeat=problem['nv']):
                assignment = [None]+list(values)
                formula_ok = all(any(assignment[abs(v)]==(v>0) for v in row) for row in problem['clauses']) and all(
                    bool(sum(assignment[v] for v in row)%2)==rhs for row,rhs in problem['xors'])
                vectors = list(system['baseline_vectors'])
                for g,v in problem['forced_vectors'].items():
                    vectors[int(g)] = v
                indicators_ok = True
                for key,xs in problem['x_variables'].items():
                    v = int(assignment[xs[0]])
                    vectors[int(key)] = v
                    indicators_ok &= assignment[problem['y_variables'][key]]==bool(v)
                original_ok = indicators_ok and all(
                    sum(vectors[g] for g in range(3) if row>>g&1)%2==rhs
                    for row,rhs in zip(system['coefficients'],system['right_sides']))
                self.assertEqual(formula_ok,original_ok)

    @unittest.skipUnless(HAVE_SOLVER,'optional native XOR solver unavailable')
    def test_planted_full_tensor_and_fixed_outside(self):
        system,free = self.planted()
        problem = build_problem(system,free,7)
        result = solve(problem,seconds=2,memory_mb=512)
        self.assertEqual(result['status'],'SAT')
        self.assertEqual(result['verification']['rank'],7)
        self.assertEqual(result['verification']['exact_entries_checked'],64)
        self.assertTrue(result['worker_reaped'])
        self.assertLess(problem['metadata']['x_variables'],global_problem(system,7)['metadata']['x_variables'])
        bad = list(result['complete_assignment'])
        bad[1] = not bad[1]
        with self.assertRaises(AssertionError):
            validate_decode(problem,bad)
        control = build_problem(system,free,8)
        result = solve(control,seconds=2,memory_mb=512,assumptions=baseline_assumptions(control))
        self.assertEqual(result['status'],'SAT')

    @unittest.skipUnless(HAVE_SOLVER,'optional native XOR solver unavailable')
    def test_conditional_unsat_agrees_with_retained_global_formula(self):
        system,_ = self.planted()
        for free in [[],[0],[1,3]]:
            result = solve(build_problem(system,free,7),seconds=2,memory_mb=512)
            original = global_solve(global_problem(system,7),seconds=2,memory_mb=512,
                assumptions=local_assumptions(system,free))
            self.assertEqual(result['status'],'LOCAL_UNSAT')
            self.assertEqual(original['status'],'UNSAT')

    @unittest.skipUnless(HAVE_SOLVER,'optional native XOR solver unavailable')
    def test_hard_timeout_and_inherited_signal_handler(self):
        system,free = self.planted()
        problem = build_problem(system,free,7)
        def stall(*args):
            signal.signal(signal.SIGTERM,signal.SIG_IGN)
            time.sleep(10)
        with patch('mmsearch.local_eliminated42sat._worker',stall):
            result = solve(problem,seconds=.02,memory_mb=512)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertTrue(result['worker_reaped'])
        self.assertLess(result['elapsed_seconds'],1)

    @unittest.skipUnless(HAVE_SOLVER,'optional native XOR solver unavailable')
    def test_error_is_not_unsat(self):
        system,free = self.planted()
        result = solve(build_problem(system,free,7),seconds=2,memory_mb=512,
            options={'definitely-invalid-42-option':'1'})
        self.assertEqual(result['status'],'ERROR')


if __name__=='__main__':
    unittest.main()
