import unittest
from mmsearch import cyclic_tensor_polarization7 as p
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.search import naive_terms
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import _check_all_basis_outputs

class PolarizationOrbitTests(unittest.TestCase):
    def test_all_small_pairs_five_orbits_nine_products_odd_zero(self):
        for a in range(1,16):
            for b in range(a+1,16):
                representatives=p.polarization_orbits(a,b,2)
                self.assertEqual(len(representatives),5);self.assertEqual(sum(len(c.orbit(term,2)) for term in representatives),9)
                tensor=0
                for term in representatives:tensor^=c.orbit_tensor(term,2)
                self.assertEqual(tensor,0)

    def test_exact_n3_seed27_to32_two_cubes_and_odd_relation(self):
        source=naive_terms(3);code,relations=p.extend_tiny(source,[(1,16)],3);seed=code.state_from_terms(source);changed=seed^relations[0]
        self.assertEqual(relations[0].bit_count()%2,1);self.assertEqual(code.weight(seed),27);self.assertEqual(code.weight(changed),32)
        self.assertEqual(code.expand_state(changed),p.polarize_tiny_seed(source,1,16,3))
        cubes=[i for i,w in enumerate(code.weights) if w==1];self.assertEqual(sum((changed>>i)&1 for i in cubes),2)
        for state in [seed,changed]:
            candidate=code.candidate(state);self.assertTrue(verify_candidate(candidate,random_trials=0)['valid'])
            check=_check_all_basis_outputs(3,[(tuple(t['u']),tuple(t['v']),tuple(t['w'])) for t in candidate['terms']]);self.assertEqual(check['mismatch_count'],0);self.assertEqual(check['output_bits_checked'],729)

    def test_rank3_nonzero_xor_seed_breaks_old_mod6_obstruction(self):
        # Actual-source-shaped abstract projection: three independent old cubes,
        # one new sum; old complete kernel toggles000/111 with even parity.
        report=p.projected_diagnostics(4,7,1,[(7,0),(11,1)])
        self.assertEqual(report['necessary_cost_residues_mod6'],[0,2,3]);self.assertIn(2,report['possible_cube_counts']);self.assertTrue(report['exact92_residue_permitted'])
        self.assertEqual(p.gf2_rank([1,2,4]),3)

    def test_rank2_line_and_zero_xor_rank3_still_exclude_mod3_two(self):
        # Three line cubes1,2,3, old all-three toggle and pair polarization.
        line=p.projected_diagnostics(3,7,1,[(7,0),(7,1)])
        self.assertEqual(line['possible_cube_counts'],[0,3]);self.assertFalse(line['exact92_residue_permitted'])
        forms=list(range(1,8));generators=list(p.polarization_projection_generators(forms))+[(7,0)]
        full=p.projected_diagnostics(7,7,1,generators)
        self.assertEqual(full['possible_cube_counts'],[0,3,4,7]);self.assertFalse(full['exact92_residue_permitted'])

    def test_rank4_zero_xor_weight5_circuit_can_remove_congruence_obstruction(self):
        forms=list(range(1,16));generators=list(p.polarization_projection_generators(forms))+[(7,0)]
        report=p.projected_diagnostics(15,7,1,generators)
        self.assertIn(5,report['possible_cube_counts']);self.assertTrue(report['exact92_residue_permitted'])
        circuit=[1,2,4,8,15];value=0
        for form in circuit:value^=form
        self.assertEqual(value,0);self.assertEqual(p.gf2_rank(circuit),4)

    def test_n5_generation_and_invalid_inputs_remain_disabled(self):
        for call in [lambda:p.polarization_orbits(1,2,5),lambda:p.extend_tiny([],[(1,2)],5),lambda:p.polarize_tiny_seed([],1,2,5)]:
            with self.assertRaises(ValueError):call()
        for a,b in [(0,1),(1,1),(True,2)]:
            with self.assertRaises(ValueError):p.polarization_orbits(a,b,2)
        with self.assertRaises(ValueError):p.projected_diagnostics(16,0,0,[])

if __name__=='__main__':unittest.main()
