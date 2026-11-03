"""Tiny controls only; no n5 dictionary construction, decoding or search."""
import importlib.util
import itertools
import random
import unittest
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.search import naive_terms
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import _check_all_basis_outputs


class CyclicTensorCodeTests(unittest.TestCase):
    def test_whole_orbit_canonicalization_cube_weight_and_reflection(self):
        self.assertEqual(c.orbit((1,1,1),2),((1,1,1),))
        self.assertEqual(c.orbit((1,2,4),2),((1,2,4),(2,4,1),(4,1,2)))
        self.assertNotEqual(c.orbit_representative((1,2,4),2),c.orbit_representative((1,4,2),2))
        self.assertEqual(c.orbit_representatives([(1,2,4),(2,4,1),(1,1,1)],2),((1,1,1),(1,2,4)))
        for atom in [(0,1,1),(-1,1,1),(True,1,1),(16,1,1),(1,2)]:
            with self.subTest(atom=atom),self.assertRaises(ValueError):c.orbit(atom,2)
        with self.assertRaises(ValueError):c.orbit_representatives([(1,1,1),(2,2,2)],2,max_orbits=1)
        with self.assertRaises(ValueError):c.TinyOrbitCode.build([],5)

    def test_projection_inverse_all_invariant_tensors_and_noninvariant_rejection(self):
        # width2 has4 coordinate orbits; exhaust all16 invariant tensors.
        self.assertEqual(len(c.coordinate_orbits(2)),4)
        for x in range(16):
            full=c.expand_invariant(x,2);self.assertEqual(c.compress_invariant(full,2),x)
        with self.assertRaises(ValueError):c.compress_invariant(1<<1,2)
        for width in [1,2,3,4,9,25]:
            coordinates=c.coordinate_orbits(width)
            self.assertEqual(len(coordinates),(width**3+2*width)//3)
            self.assertEqual(sorted(i for group in coordinates for i in group),list(range(width**3)))
        self.assertEqual(len(c.coordinate_orbits(25)),5225)

    def test_compression_preserves_all_tiny_columns_and_linear_equations(self):
        atoms=list(itertools.product(range(1,4),repeat=3))
        code=c.TinyOrbitCode.build(atoms,2);full=c.TinyOrbitCode.build(atoms,2,compressed=False)
        self.assertEqual(code.representatives,full.representatives)
        for column,literal in zip(code.columns,full.columns):self.assertEqual(c.expand_invariant(column,4),literal)
        for state in range(1<<len(code.columns)):
            self.assertEqual(c.expand_invariant(c.xor_columns(code.columns,state),4),c.xor_columns(full.columns,state))
            self.assertEqual(code.weight(state),len(code.expand_state(state)))
        # Fixed cubes still contribute one full outer tensor, not zero or3 cost.
        self.assertEqual(c.orbit_tensor((3,3,3),2),c.atom_tensor((3,3,3),2))

    def test_exact_target_convention_and_nullspace_moves_n2_n3(self):
        rng=random.Random(7)
        for n in [2,3]:
            source=list(naive_terms(n));atoms=source+[(1,2,4),(1,2,8),(1,2,12)]
            # Exact whole-orbit linearity relation B(1,2,4)+B(1,2,8)=B(1,2,12).
            code=c.TinyOrbitCode.build(atoms,n);state=code.state_from_terms(source);system=code.linear_system()
            self.assertTrue(system['consistent']);self.assertEqual(system['rank']+system['nullity'],len(code.columns));self.assertGreater(system['nullity'],0)
            self.assertEqual(c.xor_columns(code.columns,state),code.target());self.assertEqual(c.xor_columns(code.columns,system['particular']),code.target())
            for _ in range(24):
                move=0
                for relation in system['kernel']:
                    self.assertEqual(c.xor_columns(code.columns,relation),0)
                    if rng.getrandbits(1):move^=relation
                candidate=code.candidate(state^move);report=verify_candidate(candidate,random_trials=0)
                self.assertTrue(report['valid']);self.assertEqual(report['exact_entries_checked'],n**6)
                independent=_check_all_basis_outputs(n,[(tuple(t['u']),tuple(t['v']),tuple(t['w'])) for t in candidate['terms']])
                self.assertEqual(independent['mismatch_count'],0);self.assertEqual(independent['output_bits_checked'],n**6)
            with self.assertRaises(ValueError):code.state_from_terms(source+[source[0]])
            partial=[(1,2,4)]
            with self.assertRaises(ValueError):code.state_from_terms(partial)
            with self.assertRaises(ValueError):code.candidate(0)
        self.assertEqual(c.target_tensor(1),1)
        with self.assertRaises(ValueError):c.TinyOrbitCode.build([(1,1,1)],2).candidate(1)
        self.assertFalse(c.TinyOrbitCode.build([(1,1,1)],2).linear_system()['consistent'])

    def test_planted_exact_orbit_relation_reduces_weight11_to8(self):
        old_orbits=[(1,2,4),(8,4,2)]
        new_orbits=[(9,2,4),(8,2,6),(8,6,2)]
        cubes=[(1,1,1),(8,8,8)]
        code=c.TinyOrbitCode.build(old_orbits+new_orbits+cubes,2)
        source=set(cubes)
        for atom in new_orbits:source.update(c.orbit(atom,2))
        source_state=code.state_from_terms(sorted(source))
        naive_state=code.state_from_terms(naive_terms(2))
        self.assertEqual(code.weight(source_state),11);self.assertEqual(code.weight(naive_state),8)
        relation=source_state^naive_state
        self.assertEqual(c.xor_columns(code.columns,relation),0)
        self.assertEqual(code.weight(source_state^relation),8)
        for state in [source_state,naive_state]:
            candidate=code.candidate(state);self.assertTrue(verify_candidate(candidate,random_trials=0)['valid'])
            check=_check_all_basis_outputs(2,[(tuple(t['u']),tuple(t['v']),tuple(t['w'])) for t in candidate['terms']])
            self.assertEqual(check['mismatch_count'],0)
        # Constant target metadata is permitted; no n5 column dictionary exists.
        full=c.target_tensor(5);compressed=c.compress_invariant(full,25)
        self.assertEqual(full.bit_count(),125);self.assertEqual(compressed.bit_count(),45)
        self.assertEqual(c.expand_invariant(compressed,25),full)

    def test_strict_state_and_weight_literals(self):
        self.assertEqual(c.repeated_weight_literals([1,2],[1,3]),[1,2,2,2])
        for variables,weights in [([1,1],[1,3]),([True],[1]),([1],[2]),([1],[True]),([1,2],[1])]:
            with self.assertRaises(ValueError):c.repeated_weight_literals(variables,weights)
        code=c.TinyOrbitCode.build(naive_terms(2),2)
        for state in [-1,True,1<<len(code.columns)]:
            with self.assertRaises(ValueError):code.expand_state(state)

    @unittest.skipUnless(importlib.util.find_spec('pysat'),'optional PySAT unavailable; repeated-literal SAT claim deferred')
    def test_repeated_literal_seqcounter_matches_integer_weight_exhaustively(self):
        from pysat.card import CardEnc,EncType
        from pysat.solvers import Solver
        for weights in [(1,3,1),(3,3),(1,3,3)]:
            variables=list(range(1,len(weights)+1));literals=c.repeated_weight_literals(variables,weights)
            for bound in range(sum(weights)+2):
                formula=CardEnc.atmost(lits=literals,bound=bound,top_id=len(weights),encoding=EncType.seqcounter)
                with Solver(name='g3',bootstrap_with=formula.clauses) as solver:
                    for values in itertools.product([False,True],repeat=len(weights)):
                        assumptions=[v if value else -v for v,value in zip(variables,values)]
                        expected=sum(weight for weight,value in zip(weights,values) if value)<=bound
                        self.assertEqual(solver.solve(assumptions=assumptions),expected,(weights,bound,values))

if __name__=='__main__':unittest.main()
