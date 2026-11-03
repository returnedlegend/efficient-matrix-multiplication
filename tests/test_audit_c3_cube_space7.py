import itertools
import unittest
from scripts.audit_c3_cube_space7 import intersection_witnesses,xor,column_basis
from mmsearch.cyclic_tensor_code7 import atom_tensor

class CubeSpaceTests(unittest.TestCase):
    def test_tiny_intersections_match_literal_span_sets(self):
        columns=[1,2,4]
        families=[[],[1],[2],[3],[1,2],[1,4],[3,5],[1,2,4]]
        def span(values):return {xor(values,mask) for mask in range(1<<len(values))}
        for base,space in itertools.product(families,repeat=2):
            result=intersection_witnesses(base,space)
            actual=span(base)&span(space)
            self.assertEqual(len(actual),1<<result['intersection_dimension'])
            for witness in result['intersection_witnesses']:self.assertEqual(xor(space,int(witness['space_mask_hex'],16)),xor(base,int(witness['base_mask_hex'],16)))

    def test_diagonal_cube_components_have_flattening_rank_equal_to_count(self):
        columns=[atom_tensor((a,a,a),2) for a in [1,2,4]]
        for selected in range(8):
            tensor=xor(columns,selected);rows=[(tensor>>(i*16))&65535 for i in range(4)]
            self.assertEqual(len(column_basis(rows)[0]),selected.bit_count())

    def test_dependent_space_inputs_are_rejected(self):
        with self.assertRaises(ValueError):intersection_witnesses([1,2],[1,1])

if __name__=='__main__':unittest.main()
