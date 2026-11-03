"""Nested real-kernel neighborhoods and exact rank8 feasibility controls."""
import importlib.util
import unittest

from mmsearch.free_factor_sat import build_problem,build_system,solve
from mmsearch.local_free_factor_sat import checked_circuits,local_assumptions,local_bound
from mmsearch.local_free_factor_sat_large import neighborhoods
from mmsearch.tensor import naive_candidate

HAVE_SOLVER = bool(importlib.util.find_spec('pycryptosat') and importlib.util.find_spec('pysat'))


def full_two_by_two():
    system = build_system([(u,1,w) for u in range(1,16) for w in range(1,16)],
                          2,'wu',naive_candidate(2))
    pair_map = {p:g for g,p in enumerate(system['pairs'])}
    records = []
    for axis in range(2):
        for fixed in range(1,16):
            triples = {tuple(sorted((a,b,a^b))) for a in range(1,16) for b in range(a+1,16)}
            for triple in sorted(triples):
                pairs = [(fixed,x) if axis == 0 else (x,fixed) for x in triple]
                records.append(dict(support=sorted(pair_map[p] for p in pairs)))
    return system,checked_circuits(system,records)


class LargeLocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.system,cls.supports = full_two_by_two()
        cls.plan = list(neighborhoods(cls.system,cls.supports,seed=83,families=2,max_groups=256))

    def test_actual_kernel_unions_are_nested_and_relax_only_outside_assumptions(self):
        self.assertGreaterEqual(len(self.plan),4)
        self.assertLessEqual(len(self.plan),8)
        for family in sorted({item['family'] for item in self.plan}):
            chain = [item for item in self.plan if item['family']==family]
            if family == 0:
                self.assertEqual([item['circuit_count'] for item in chain],[8,16,32,64])
            previous_groups = set()
            previous_assumptions = None
            for item in chain:
                union = set()
                for index in item['circuit_indices']:
                    if union:
                        self.assertTrue(union & self.supports[index])
                    union.update(self.supports[index])
                groups = set(item['free_groups'])
                self.assertEqual(union,groups)
                self.assertTrue(previous_groups < groups)
                self.assertLessEqual(len(groups),256)
                assumptions = set(local_assumptions(self.system,groups))
                if previous_assumptions is not None:
                    self.assertTrue(assumptions < previous_assumptions)
                previous_groups,previous_assumptions = groups,assumptions
                # A feasible rank8 baseline cannot be excluded by a sound bound.
                self.assertLessEqual(local_bound(self.system,groups,8)['lower_bound'],8)

    @unittest.skipUnless(HAVE_SOLVER,'optional XOR solver unavailable')
    def test_exact_control_model_remains_feasible_through_nested_expansion(self):
        first = self.plan[0]
        problem = build_problem(self.system,8,max_formula_mb=384)
        control = solve(problem,seconds=2,memory_mb=512,
                        assumptions=local_assumptions(self.system,first['free_groups']))
        self.assertEqual(control['status'],'SAT')
        self.assertTrue(control['worker_reaped'])
        self.assertTrue(control['verification']['valid'])
        self.assertEqual(control['verification']['exact_entries_checked'],64)
        for item in self.plan:
            if item['family'] != first['family']:
                continue
            for literal in local_assumptions(self.system,item['free_groups']):
                self.assertEqual(control['complete_assignment'][abs(literal)],literal > 0)

    def test_resource_guard_and_small_group_cap(self):
        for kwargs in [dict(max_groups=257),dict(families=65)]:
            with self.assertRaises(ValueError):
                list(neighborhoods(self.system,self.supports,**kwargs))
        limited = list(neighborhoods(self.system,self.supports,seed=83,families=2,max_groups=32))
        self.assertTrue(limited)
        self.assertTrue(all(item['free_group_count'] <= 32 for item in limited))


if __name__ == '__main__':
    unittest.main()
