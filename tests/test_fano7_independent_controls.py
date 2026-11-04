"""Independent Fano formula/model and combined input-tamper controls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from mmsearch import fano_quotient_sat7 as subject
from mmsearch.fano_quotient_adapter7 import load_pinned_case
from mmsearch.compact_eight43 import exact_coordinates
from mmsearch.compact_rank2_edges43 import matrix_rank_at_most_two,rankone_factors
from tests.fano7_independent_fixture import planted_fano_b7
from tests.test_fano_quotient_sat7 import literal_assignment


class FanoIndependentControls(unittest.TestCase):
    def test_full_variable_namespace_and_every_literal_model_gate(self):
        f=planted_fano_b7();points=[dict(left=p['left'],right=p['right'],column=p['matrix']) for p in f['backbone_rankone_points']]
        problem=subject.build_problem(f['slices'],11,11,points,f['slices'])
        groups=[problem['u_variables'],problem['v_variables'],problem['z_variables'],problem['product_variables'],
                problem['a_variables'],problem['inverse_variables']]
        variables=[v for group in groups for row in group for v in row]
        variables += [v for row in problem['inverse_product_variables'] for cell in row for v in cell]
        self.assertEqual(sorted(variables),list(range(1,problem['nv']+1)))
        model,_=literal_assignment(problem,[(p['left'],p['right']) for p in f['fano_rankone_points']])
        result=subject.validate_decode(problem,model)
        self.assertEqual(len(result['support']),14)
        self.assertEqual(result['target_coordinates'],[exact_coordinates(value,[p['column'] for p in result['support']]) for value in f['slices']])
        for variable in variables:
            bad=list(model);bad[variable]=not bad[variable]
            with self.assertRaises(AssertionError,msg='singlemodelbit '+str(variable)):
                subject.validate_decode(problem,bad)

    def test_callback_cannot_replace_formula_and_update_self_attested_hash(self):
        problem=subject.build_problem([1,2,4,8],2,2,[])
        def mutate():
            problem['clauses'].append([])
            problem['metadata']['formula_sha256']=subject.digest({k:v for k,v in problem.items() if k!='metadata'})
            return False
        result=subject.solve(problem,cancelled=mutate)
        self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(result['reason'],'formula_changed')
        self.assertFalse(result['worker_started'])

    def test_pinned_source_manifest_rejects_combined_core_metadata_checksum_tamper(self):
        campaign=Path(__file__).resolve().parents[1]/'artifacts/marathon7_20261103T122417Z'
        metadata=campaign/'c3-surplus3-pair-metadata-nine-v1';cores=campaign/'binary-block-nine-core-prep-001'
        f=planted_fano_b7();item=json.loads((metadata/'case-02.json').read_bytes());data=json.loads((cores/'case-02.json').read_bytes())
        data['core']=f['core'];data['shape']=f['shape'];basis=f['slices'];points=[]
        for mask in range(1,2048):
            value=0
            for i,matrix in enumerate(basis):
                if mask>>i&1:value^=matrix
            if matrix_rank_at_most_two(value,11,11)[0]==1:
                left,right=rankone_factors(value,11,11)
                points.append(dict(matrix_hex=hex(value),left=left,right=right,space_coordinates_hex=hex(exact_coordinates(value,basis))))
        rawdata=(json.dumps(data,sort_keys=True,indent=2)+'\n').encode()
        item.update(input_core_sha256=hashlib.sha256(rawdata).hexdigest(),raw_slices_hex=[hex(v) for v in basis],space_basis_hex=[hex(v) for v in basis],rankone_points=points)
        rawitem=(json.dumps(item,sort_keys=True,indent=2)+'\n').encode();checks=json.loads((metadata/'checksums.json').read_bytes());checks['case-02.json']=hashlib.sha256(rawitem).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m=root/metadata.name;c=root/cores.name;m.mkdir();c.mkdir()
            (m/'manifest.json').write_bytes((metadata/'manifest.json').read_bytes())
            (m/'checksums.json').write_text(json.dumps(checks));(m/'case-02.json').write_bytes(rawitem)
            (c/'manifest.json').write_bytes((cores/'manifest.json').read_bytes());(c/'case-02.json').write_bytes(rawdata)
            with self.assertRaises(ValueError):load_pinned_case(root,2)


if __name__=='__main__':unittest.main()
