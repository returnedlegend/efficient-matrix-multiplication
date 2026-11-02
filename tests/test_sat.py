"""Semantic checks for local tensor CNF, independent coefficient verification."""
import copy
import importlib.util
import itertools
import unittest

from mmsearch.sat import CNF, build_local_cnf, decode_model, solve_local
from mmsearch.tensor import naive_candidate
from mmsearch.verify import verify_candidate


def holds(clauses,values):
    return all(any(values[abs(x)] == (x>0) for x in clause) for clause in clauses)


class SATEncodingTests(unittest.TestCase):
    def test_conjunction_equivalence_exhaustively(self):
        cnf=CNF()
        inputs=[cnf.variable() for _ in range(3)]
        q=cnf.conjunction(inputs)
        for bits in itertools.product((False,True),repeat=4):
            values=dict(zip(range(1,5),bits))
            self.assertEqual(holds(cnf.clauses,values),bits[3] == all(bits[:3]))
        self.assertEqual(cnf.conjunction([inputs[0],0,inputs[1]]),0)
        self.assertEqual(cnf.conjunction(inputs),q)

    def test_xor_chain_and_duplicate_cancellation_exhaustively(self):
        for parity in (0,1):
            cnf=CNF()
            variables=[cnf.variable() for _ in range(3)]
            cnf.parity(variables,parity)
            for values in itertools.product((False,True),repeat=3):
                extensions=[]
                for extras in itertools.product((False,True),repeat=cnf.nv-3):
                    extensions.append(holds(cnf.clauses,dict(zip(range(1,cnf.nv+1),values+extras))))
                self.assertEqual(any(extensions),sum(values)%2 == parity)
        cnf=CNF()
        a=cnf.variable()
        cnf.parity([a,a,0],1)
        self.assertEqual(cnf.clauses,[[]])

    def test_rejects_nonternary_and_decimal_factors(self):
        source=naive_candidate(1)
        source['terms'].append(copy.deepcopy(source['terms'][0]))
        for value in (2,1.0,True):
            corrupt=copy.deepcopy(source)
            corrupt['terms'][0]['u'][0]=value
            with self.assertRaises(ValueError):
                build_local_cnf(corrupt,rank=1,drop_term=1,active_terms=[0])
        source['terms'][0]['u'][0]=-1
        problem=build_local_cnf(source,rank=1,drop_term=1,active_terms=[0])
        self.assertEqual(problem['source']['terms'][0]['u'],[1])

    def test_all_zero_equations_and_frozen_neighborhood_metadata(self):
        source=naive_candidate(2)
        problem=build_local_cnf(source,rank=7,drop_term=7,active_terms=[0],support_mode='union')
        self.assertEqual(problem['metadata']['tensor_equations'],64)
        self.assertEqual(len(problem['metadata']['frozen_terms']),6)
        self.assertEqual(len(problem['retained']),7)
        self.assertTrue(all(type(x) is int for clause in problem['clauses'] for x in clause))
        with self.assertRaises(ValueError):
            build_local_cnf(source,rank=7,drop_term=7,active_terms=[7])

    def test_hard_budget_validation(self):
        for seconds in (float('nan'),float('inf'),-1,0):
            with self.assertRaises(ValueError):
                solve_local({},seconds=seconds)

    @unittest.skipUnless(importlib.util.find_spec('pysat'),'python-sat optional dependency missing')
    def test_sat_candidate_exactly_verified_and_decodable(self):
        source=naive_candidate(1)
        source['terms'].append({'u':[0],'v':[0],'w':[0]})
        problem=build_local_cnf(source,rank=1,drop_term=1,active_terms=[0])
        result=solve_local(problem,seconds=3,conflicts=100)
        self.assertEqual(result['status'],'SAT')
        self.assertTrue(verify_candidate(result['candidate'])['valid'])
        self.assertEqual(result['verification']['exact_entries_checked'],1)

    @unittest.skipUnless(importlib.util.find_spec('pysat'),'python-sat optional dependency missing')
    def test_unsat_is_only_local_and_keeps_all_zero_equations(self):
        # Two independent rank-one tensors cannot be replaced with one, even
        # allowing all four coordinates of each factor.
        source=naive_candidate(2)
        problem=build_local_cnf(source,rank=7,drop_term=7,active_terms=[0],support_mode='full')
        result=solve_local(problem,seconds=3,conflicts=10000)
        self.assertEqual(result['status'],'UNSAT')
        self.assertEqual(problem['metadata']['tensor_equations'],64)
        self.assertIn('local',problem['metadata']['scope'])


if __name__=='__main__':
    unittest.main()
