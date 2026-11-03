import unittest
from mmsearch.cyclic_tensor_code7 import TinyOrbitCode
from mmsearch.search import naive_terms
from scripts.audit_cyclic_polarization7 import materialize

class ExtensionAuditTests(unittest.TestCase):
    def test_tiny_audit_reuses_old_columns_and_known_odd_relation(self):
        terms=naive_terms(3);old=TinyOrbitCode.build(terms,3);dictionary,report,changed=materialize(old.representatives,terms,(1,16),3)
        self.assertEqual(report['dictionary_orbits'],len(old.columns)+3);self.assertEqual(report['polarized_cost'],32)
        self.assertEqual(report['polarized_cubes'],2);self.assertTrue(report['joint_complete_kernel_projection']['exact92_residue_permitted'])
        self.assertGreater(report['kernel_parity']['odd_basis_vectors'],0);self.assertEqual(len(changed),32)
        for i,j in enumerate(report['old_to_new_column_map']):self.assertEqual(int(dictionary['compressed_columns_hex'][j],16),old.columns[i])

    def test_default_n5_and_non_absent_extensions_are_rejected(self):
        with self.assertRaises(ValueError):materialize([],[],(4096,262208),5)
        source=naive_terms(2);old=TinyOrbitCode.build(source,2)
        with self.assertRaises(ValueError):materialize(old.representatives,source,(1,1),2)

if __name__=='__main__':unittest.main()
