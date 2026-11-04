"""Independent tiny finite-code truth tables; no production solver inputs."""
import copy
import itertools
import random
import unittest
from unittest.mock import patch

import pycryptosat
from mmsearch import cyclic_code_sat7 as subject


def syndrome(columns, state):
    value = 0
    for i, column in enumerate(columns):
        if state >> i & 1:
            value ^= column
    return value


def basis(values):
    pivots = {}
    for value in values:
        while value:
            k = value.bit_length() - 1
            if k not in pivots:
                pivots[k] = value
                break
            value ^= pivots[k]
    return list(pivots.values())


class IndependentCyclicCodeSAT(unittest.TestCase):
    def test_literal_code_and_integer_budget_truth_tables(self):
        rng = random.Random(71103)
        checked = 0
        for case in range(8):
            columns = [rng.randrange(8) for _ in range(7)]
            seed = rng.randrange(128)
            target = syndrome(columns, seed)
            kernel = basis(s for s in range(1, 128) if syndrome(columns, s) == 0)
            weights = [3] * (case % 5 + 2) + [1] * (5 - case % 5)
            for budget in (2, 5, 8):
                p = subject.build_problem(columns, target, seed, kernel, weights,
                                          len(basis(columns)), budget)
                protected = p['alpha_variables'] + p['orbit_variables'] + [p['gate_variable']]
                self.assertEqual(len(protected), len(set(protected)))
                self.assertEqual(protected, list(range(1, len(protected) + 1)))
                solver = pycryptosat.Solver(threads=1)
                solver.add_clause([p['nv'], -p['nv']])
                for row in p['clauses']:
                    solver.add_clause(row)
                for row, rhs in p['xors']:
                    solver.add_xor_clause(row, rhs)
                for state in range(128):
                    assumptions = [v if state >> i & 1 else -v
                                   for i, v in enumerate(p['orbit_variables'])]
                    actual, assignment = solver.solve(assumptions=assumptions)
                    expected = syndrome(columns, state) == target and sum(
                        w for i, w in enumerate(weights) if state >> i & 1) <= budget
                    self.assertEqual(actual, expected, (case, budget, state))
                    if actual:
                        decoded = subject.validate_decode(p, assignment, assumptions)
                        self.assertEqual(int(decoded['state_hex'], 16), state)
                    checked += 1
        self.assertEqual(checked, 3072)

    def test_self_attested_callback_mutation_is_unknown(self):
        p = subject.build_problem([0, 0], 0, 0, [1, 2], [1, 3], 0, 2)
        def mutate():
            p['clauses'].append([])
            p['metadata']['formula_sha256'] = subject.digest(
                {k: v for k, v in p.items() if k != 'metadata'})
            return False
        result = subject.solve(p, seconds=1, memory_mb=128, cancelled=mutate)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(result['reason'], 'formula_changed')
        self.assertFalse(result['worker_started'])

    def test_hard_utc_and_complete_kernel_requirements(self):
        with patch.object(subject.time, 'time', return_value=subject.HARD_DEADLINE + 1):
            guard = subject._Guard(100, '2100-01-01T00:00:00Z', None)
            self.assertEqual(guard.deadline, subject.HARD_DEADLINE)
            self.assertEqual(guard.reason(), 'deadline')
        with self.assertRaises(ValueError):
            subject.build_problem([1, 1], 0, 0, [], [1, 3], 1, 2)
        p = subject.build_problem([1, 1], 0, 0, [3], [1, 3], 1, 2)
        wrong = copy.deepcopy(p)
        wrong['kernel'] = [1]
        with self.assertRaises(ValueError):
            subject.validate_code(wrong['columns'], wrong['target'], wrong['seed'],
                                  wrong['kernel'], wrong['weights'], wrong['rank'])


if __name__ == '__main__':
    unittest.main()
