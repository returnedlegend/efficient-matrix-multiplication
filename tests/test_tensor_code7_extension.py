"""Tiny exact v2 controls; no production extension generation or search."""
import copy
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import (digest,prepare,target_tensor,validate_prepared,xor_columns)
from mmsearch.tensor_code7_extension import (WITNESS_SCHEMA,build_extension,plus_atoms,
    raw_sha,retain_raw_candidate,scalar_zero_check,validate_extension_prepared,validate_witnesses)

REPO=Path(__file__).resolve().parents[1]


class TensorCodeExtensionTests(unittest.TestCase):
    def fixture(self,permutation=None):
        base=prepare([naive_candidate(2)])
        sha=digest(base)
        parents=[tuple(base['atoms'][i]) for i in (0,7)]
        permutation=permutation or [0,1,2]
        proposed=plus_atoms(*parents,permutation,2)
        manifest=dict(schema=WITNESS_SCHEMA,base_prepared_sha256=sha,
            base_dictionary_sha256=base['dictionary_sha256'],max_new_atoms=100,
            relations=[dict(id='tiny-odd-plus-000',parent_atom_ids=[0,7],
                axis_permutation=permutation,new_atoms=[list(a) for a in proposed])])
        return base,manifest,sha

    def test_even_trivial_code_extended_by_certified_odd_cycle(self):
        base,manifest,sha=self.fixture()
        self.assertEqual(base['nullity'],0)
        doc=build_extension(base,manifest,sha,digest(manifest))
        atoms,columns,seeds,cycles,receipt=validate_extension_prepared(doc,base,manifest,sha,digest(manifest))
        self.assertEqual(doc['base_atom_count'],8);self.assertEqual(doc['new_atom_count'],3)
        self.assertTrue(doc['base_kernel_all_even']);self.assertTrue(doc['parity_broken'])
        self.assertGreater(doc['odd_kernel_basis_count'],0)
        self.assertEqual(doc['rank']+doc['nullity'],len(columns))
        z=int(doc['odd_relation_certificates'][0]['cycle_hex'],16)
        self.assertEqual(z.bit_count(),5);self.assertEqual(xor_columns(columns,z),0)
        self.assertEqual(xor_columns(columns,seeds[0]^z),target_tensor(2))
        self.assertEqual(seeds[0].bit_count(),8);self.assertEqual((seeds[0]^z).bit_count(),9)
        self.assertEqual(atoms[:8],[tuple(a) for a in base['atoms']])
        self.assertEqual(doc['seed_states_hex'],base['seed_states_hex'])
        self.assertTrue(receipt['parity_broken'])

    def test_all_six_axis_orders_preserve_full_tensor(self):
        for permutation in itertools.permutations(range(3)):
            base,manifest,sha=self.fixture(list(permutation))
            doc=build_extension(base,manifest,sha,digest(manifest))
            self.assertTrue(doc['parity_broken'])
            self.assertEqual(doc['odd_relation_certificates'][0]['full_tensor_xor_hex'],'0x0')

    def test_corrupted_witness_atom_rejected(self):
        base,manifest,sha=self.fixture();manifest['relations'][0]['new_atoms'][0][0]^=2
        with self.assertRaisesRegex(ValueError,'differs from exact plus'):
            build_extension(base,manifest,sha,digest(manifest))

    def test_zero_duplicate_or_nonliteral_factors_rejected(self):
        for left,right in [((1,1,1),(1,2,2)),((1,1,1),(2,1,2)),((1,1,1),(2,2,1)),((1,1,1),(1,1,1))]:
            with self.assertRaises(ValueError):plus_atoms(left,right,[0,1,2],2)
        for bad in (True,1.0,-1):
            with self.assertRaises(ValueError):plus_atoms((bad,1,1),(8,8,8),[0,1,2],2)

    def test_base_hash_and_parent_ids_are_authenticated(self):
        for mutation in ('hash','id','floatid','permutation'):
            base,manifest,sha=self.fixture()
            if mutation=='hash':manifest['base_prepared_sha256']='0'*64
            elif mutation=='id':manifest['relations'][0]['parent_atom_ids'][1]=8
            elif mutation=='floatid':manifest['relations'][0]['parent_atom_ids'][1]=7.0
            else:manifest['relations'][0]['axis_permutation']=[0,0,2]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                build_extension(base,manifest,sha,digest(manifest))

    def test_strict_new_atom_and_relation_caps(self):
        base,manifest,sha=self.fixture();manifest['max_new_atoms']=1
        with self.assertRaisesRegex(ValueError,'cap exceeded'):build_extension(base,manifest,sha,digest(manifest))
        base,manifest,sha=self.fixture();manifest['relations']*=17
        with self.assertRaisesRegex(ValueError,'1..16'):build_extension(base,manifest,sha,digest(manifest))

    def test_duplicate_cycle_and_unknown_top_fields_rejected(self):
        base,manifest,sha=self.fixture()
        duplicate=copy.deepcopy(manifest["relations"][0]);duplicate["id"]="same-cycle-other-name"
        manifest["relations"].append(duplicate)
        with self.assertRaisesRegex(ValueError,"duplicate five-term"):
            build_extension(base,manifest,sha,digest(manifest))
        base,manifest,sha=self.fixture();manifest["arbitrary_atoms"]=[[1,2,4]]
        with self.assertRaisesRegex(ValueError,"top-level witness fields"):
            build_extension(base,manifest,sha,digest(manifest))

    def test_independent_scalar_zero_checker_catches_corruption(self):
        base,manifest,sha=self.fixture()
        five=[tuple(base["atoms"][i]) for i in (0,7)]+[tuple(a) for a in manifest["relations"][0]["new_atoms"]]
        self.assertTrue(scalar_zero_check(five,2)["valid"])
        five[-1]=(five[-1][0]^1,five[-1][1],five[-1][2])
        self.assertFalse(scalar_zero_check(five,2)["valid"])
        self.assertEqual(scalar_zero_check(five,2)["exact_entries_checked"],64)

    def test_v2_numeric_aliases_are_not_equal_to_authenticated_document(self):
        for key in ("field","rank","nullity","parity_broken"):
            base,manifest,sha=self.fixture();doc=build_extension(base,manifest,sha,digest(manifest))
            doc[key]=float(doc[key])
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_extension_prepared(doc,base,manifest,sha,digest(manifest))
        base,manifest,sha=self.fixture();doc=build_extension(base,manifest,sha,digest(manifest));doc["atoms"][0][0]=float(doc["atoms"][0][0])
        with self.assertRaises(ValueError):validate_extension_prepared(doc,base,manifest,sha,digest(manifest))

    def test_v1_union_policy_remains_strict(self):
        base,manifest,sha=self.fixture();doc=build_extension(base,manifest,sha,digest(manifest))
        with self.assertRaisesRegex(ValueError,'schema'):validate_prepared(doc)
        self.assertEqual(base['dictionary_size'],8)

    def test_v2_self_repaired_hash_cannot_authorize_extra_atom_or_state(self):
        for corruption in ('atom','seed','column','cycle','parity'):
            base,manifest,sha=self.fixture();doc=build_extension(base,manifest,sha,digest(manifest))
            if corruption=='atom':doc['atoms'].append([2,2,2]);doc['dictionary_sha256']=digest(doc['atoms'])
            elif corruption=='seed':doc['seed_states_hex'][0]='0x0'
            elif corruption=='column':doc['columns_hex'][0]='0x0';doc['columns_sha256']=digest(doc['columns_hex'])
            elif corruption=='cycle':doc['kernel_hex'][0]='0x1'
            else:doc['parity_broken']=False
            with self.subTest(corruption=corruption),self.assertRaisesRegex(ValueError,'authenticated exact reconstruction'):
                validate_extension_prepared(doc,base,manifest,sha,digest(manifest))

    def test_n5_generation_requires_separately_authenticated_receipt(self):
        # Fail before any n5 atom construction: no production generation occurs.
        with self.assertRaisesRegex(ValueError,'authenticated v1 base receipt'):
            build_extension(dict(dimension=5,dictionary_sha256='untrusted'),{},'untrusted','untrusted')

    def test_operations_guard_cannot_ingest_expired_raw_92_shape(self):
        from scripts.campaign_operations_v3 import walk_files,canonical_candidate
        # Synthetic schema-valid92-term shape, not an exact multiplication claim.
        raw=naive_candidate(5);raw['terms']=raw['terms'][:92]
        self.assertEqual(len(canonical_candidate(raw)['terms']),92)
        with tempfile.TemporaryDirectory() as directory:
            path=retain_raw_candidate(directory,raw,'synthetic_expired_budget')
            self.assertIn('.raw-candidates',path.parts)
            self.assertNotIn(path,list(walk_files(directory)))
            wrapper=json.loads(path.read_bytes())
            with self.assertRaises((ValueError,KeyError,TypeError)):canonical_candidate(wrapper)
            self.assertEqual(wrapper['raw']['candidate'],raw)
            self.assertEqual(wrapper['status'],'UNKNOWN');self.assertFalse(wrapper['complete'])
            self.assertTrue(wrapper['after_cutoff'])

    def test_expired_authorized_runner_returns_unknown_before_input_io(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);campaign=root/"campaign.json"
            campaign.write_text(json.dumps(dict(deadline_utc="2000-01-01T00:00:00Z")))
            command=[sys.executable,"-B",str(REPO/"scripts/tensor_code7_extension.py"),
                "--authorize-extension-preparation","--qa-approval","root-reviewed",
                "--base-prepared","/DO_NOT_READ","--base-sha256","0"*64,
                "--witnesses","/DO_NOT_READ","--witnesses-sha256","0"*64,
                "--source-manifest","/DO_NOT_READ","--source-manifest-sha256","0"*64,
                "--approved-root","/DO_NOT_READ","--campaign-dir",str(root),
                "--campaign-sha256",raw_sha(campaign.read_bytes()),"--guard-state",str(root/"missing-guard.json"),
                "--hard-utc","2000-01-01T00:00:00Z","--outdir",str(root/"DO_NOT_CREATE")]
            completed=subprocess.run(command,capture_output=True,text=True,check=True)
            report=json.loads(completed.stdout)
            self.assertEqual(report["status"],"UNKNOWN");self.assertFalse(report["complete"])
            self.assertFalse(report["production_inputs_read"]);self.assertFalse(report["extension_generated"])
            self.assertFalse((root/"DO_NOT_CREATE").exists())

    def test_runner_disabled_before_opening_production_inputs(self):
        completed=subprocess.run([sys.executable,'-B',str(REPO/'scripts/tensor_code7_extension.py'),
            '--base-prepared','/DO_NOT_READ','--witnesses','/DO_NOT_READ'],capture_output=True,text=True,check=True)
        report=json.loads(completed.stdout)
        self.assertFalse(report['production_inputs_read']);self.assertFalse(report['extension_generated'])
        self.assertFalse(report['search_called']);self.assertFalse(report['sat_called'])


if __name__=='__main__':unittest.main()
