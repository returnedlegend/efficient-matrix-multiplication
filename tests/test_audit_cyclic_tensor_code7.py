"""Tiny audit controls: exact columns, parity, forced cube bits, n5 gate."""
import contextlib
import io
import unittest
from mmsearch.search import naive_terms
from scripts.audit_cyclic_tensor_code7 import audit_columns,kernel_rank,independent_orbit_tensor,inner_phase_guard,main
from mmsearch import cyclic_tensor_code7 as c

class CyclicAuditTests(unittest.TestCase):
    def test_full_compressed_audit_exact_tiny_kernel(self):
        source=list(naive_terms(2));atoms=source+[(1,2,4),(1,2,8),(1,2,12)]
        dictionary,report=audit_columns(atoms,source,2)
        self.assertEqual(report['full_rank'],report['compressed_rank']);self.assertGreater(report['nullity'],0)
        self.assertEqual(report['seed_product_cost'],8);self.assertEqual(report['dictionary_independent_entries_checked'],64*report['dictionary_orbits'])
        self.assertEqual(report['kernel_parity']['can_change_cost_parity'],any(int(x,16).bit_count()%2 for x in dictionary['kernel_hex']))
        for atom in dictionary['representatives']:self.assertEqual(independent_orbit_tensor(c.orbit(atom,2),4),c.orbit_tensor(atom,2))

    def test_unique_cube_solution_forces_cube_and_even_kernel_preserves_parity(self):
        dictionary,report=audit_columns([(1,1,1)],[(1,1,1)],1)
        self.assertEqual(report['nullity'],0);self.assertEqual(report['forced_cube_ones'],1);self.assertEqual(report['forced_cube_zeros'],0)
        self.assertFalse(report['kernel_parity']['can_change_cost_parity'])
        rank,kernel=kernel_rank([1,1]);self.assertEqual(rank,1);self.assertEqual(kernel,(3,));self.assertEqual(kernel[0].bit_count()%2,0)
        rank,kernel=kernel_rank([1,2,3]);self.assertEqual(rank,2);self.assertEqual(kernel,(7,));self.assertEqual(kernel[0].bit_count()%2,1)

    def test_inner_phase_uses_canonical_polling_and_retains_progress(self):
        calls=[];guard=inner_phase_guard(calls.append)
        guard('column_elimination');guard('pre_source');self.assertEqual(calls,['loop','loop'])
        progress={};audit_columns([(1,1,1)],[(1,1,1)],1,progress=progress)
        self.assertEqual(progress['independently_checked_columns'],1);self.assertEqual(progress['full_rank'],1)

    def test_caps_partial_source_and_explicit_authorization_gate(self):
        source=list(naive_terms(2))
        with self.assertRaises(ValueError):audit_columns(source,source,2,max_orbits=1)
        with self.assertRaises(ValueError):audit_columns(source,[(1,2,4)],2)
        args=[]
        for name in ['prepared','manifest','approved-root','root-eligibility','campaign-dir','guard-state','output-dir','root-eligibility-sha256']:args+=['--'+name,'unused']
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(args)
        with self.assertRaises(ValueError):c.TinyOrbitCode.build([],5)

if __name__=='__main__':unittest.main()
