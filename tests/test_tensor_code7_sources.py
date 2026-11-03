"""Synthetic ancestry/approval controls; no production source or tensor query."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import atom_from_term, digest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tensor_code7_source_test_worker", REPO/"scripts/tensor_code7.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class TensorCodeSourceTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        # Deliberately an incomplete tensor: this fixture tests lineage, not search.
        candidate = naive_candidate(5)
        candidate['terms'] = candidate['terms'][:93]
        source = root/'synthetic-source.json'
        source.write_text(json.dumps(candidate))
        raw_sha = worker.sha(source.read_bytes())
        term_hash = worker.term_identity(candidate)
        rl_hash = digest(sorted(atom_from_term(t,5) for t in candidate['terms']))
        identity = dict(term_set_sha256=term_hash,rl_source_sha256=rl_hash)
        node_id = 'native:'+term_hash
        registries = {}
        def registry(name, value):
            path = root/(name+'.json');path.write_text(json.dumps(value))
            registries[name] = dict(path=str(path),sha256=worker.sha(path.read_bytes()))
        registry('plan',dict(initial_pool=[dict(sha256=raw_sha,term_hash=term_hash,rl_source_hash=rl_hash)]))
        registry('armed',dict(owner='root',armed=True,plan_sha256=registries['plan']['sha256']))
        registry('split',dict(train=[rl_hash]))
        registry('exports',dict(sources=[dict(sha256=raw_sha,term_hash=term_hash)]))
        evidence = dict(approval_owner='root',approval_registry='armed',approval_sha256=registries['armed']['sha256'],
            plan_registry='plan',plan_sha256=registries['plan']['sha256'],selector=['initial_pool',0],
            split_registry='split',train_selector=['train'],train_identity=rl_hash,original_sha256=raw_sha)
        node = dict(id=node_id,path=str(source),sha256=raw_sha,identity=identity,parent_ids=[],parent_files=[],
            node_type='native_initial_train',split='train',root_id=node_id,root_approved_train=True,
            heldout_excluded=True,evaluation_excluded=True,root_training_evidence=evidence)
        anchor = dict(node,ancestor_ids=[node_id],eligibility='ELIGIBLE_PENDING_ROOT_REVIEW',origin_sha256=raw_sha,
                      export_registry='exports',export_selector=['sources',0])
        manifest = dict(format='tensor-code-source-anchors-v1',root_approved=False,anchors=[anchor],nodes={node_id:node},
            registries=registries,prohibited_identities=dict(heldout=['a'*64],evaluation=['b'*64]))
        args = SimpleNamespace(manifest=root/'manifest.json',approved_root=root)
        self.repin(args,manifest)
        return args,manifest,node_id

    def repin(self,args,manifest):
        args.manifest.write_text(json.dumps(manifest))
        args.manifest_sha256 = worker.sha(args.manifest.read_bytes())

    def load(self,args,root):
        return worker.load_sources(args,Path(root),lambda *_barrier:None)

    def test_synthetic_source_lineage_only_never_calls_dictionary_or_solver(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
            args,manifest,node_id=self.fixture(directory)
            with patch.object(worker,'prepare') as prepare:
                candidates,records,pin=self.load(args,output)
            prepare.assert_not_called()
            self.assertEqual(len(candidates),1);self.assertEqual(records[0]['anchor_id'],node_id)
            self.assertEqual(pin,args.manifest_sha256)

    def test_known_training_inputs_are_explicitly_catalog_bound(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
            args,manifest,node_id=self.fixture(directory)
            manifest["known_input_train_states"]=[copy.deepcopy(manifest["nodes"][node_id])]
            self.repin(args,manifest)
            candidates,records,_pin=self.load(args,output)
            self.assertEqual(len(candidates),2)
            self.assertEqual(records[-1]["source_group"],"native_initial_train")

    def test_parent_copy_requires_exact_terms_and_known_derivation(self):
        for kind in ("canonical_terms_preserved_root_copy", "UNKNOWN_DERIVATION"):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
                args,manifest,node_id=self.fixture(directory)
                child_id="bfs:"+manifest["nodes"][node_id]["identity"]["term_set_sha256"]
                child=copy.deepcopy(manifest["nodes"][node_id]);child.update(id=child_id,node_type="bfs_affine_train_descendant",split="train_descendant",
                    parent_ids=[node_id],parent_files=[dict(id=node_id,sha256=child["sha256"])],derivation=dict(type=kind))
                manifest["nodes"][child_id]=child
                anchor=manifest["anchors"][0];anchor.update(id=child_id,ancestor_ids=[child_id,node_id])
                self.repin(args,manifest)
                if kind=="UNKNOWN_DERIVATION":
                    with self.assertRaisesRegex(ValueError,"unknown source derivation"):self.load(args,output)
                else:
                    _candidates,records,_pin=self.load(args,output)
                    self.assertEqual(set(records[0]["ancestor_ids"]),{node_id,child_id})

    def test_unreviewed_manifest_repaired_selfhash_is_not_approval(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
            args,manifest,node_id=self.fixture(directory)
            args.manifest.write_text(json.dumps(dict(manifest,root_approved=True)))
            with self.assertRaisesRegex(ValueError,'root-reviewed hash'):self.load(args,output)

    def test_unknown_parent_edge_rejected(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
            args,manifest,node_id=self.fixture(directory)
            manifest['nodes'][node_id]['parent_ids']=['unknown']
            manifest['nodes'][node_id]['parent_files']=[dict(id='unknown',sha256='c'*64)]
            self.repin(args,manifest)
            with self.assertRaisesRegex(ValueError,'unknown or mismatched parent'):self.load(args,output)

    def test_heldout_ancestor_rejected_despite_claimed_eligible_flags(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
            args,manifest,node_id=self.fixture(directory)
            manifest['prohibited_identities']['heldout'].append(manifest['nodes'][node_id]['identity']['rl_source_sha256'])
            self.repin(args,manifest)
            with self.assertRaisesRegex(ValueError,'heldout/evaluation'):self.load(args,output)

    def test_corrupted_frozen_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
            args,manifest,node_id=self.fixture(directory)
            Path(manifest['nodes'][node_id]['path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):self.load(args,output)

    def test_root_training_catalog_and_arm_pins_are_both_required(self):
        for corruption in ('arm','train'):
            with self.subTest(corruption=corruption),tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as output:
                args,manifest,node_id=self.fixture(directory)
                key='armed' if corruption=='arm' else 'split'
                path=Path(manifest['registries'][key]['path'])
                data=json.loads(path.read_bytes())
                if corruption=='arm':data['armed']=False
                else:data['train']=[]
                path.write_text(json.dumps(data));new_sha=worker.sha(path.read_bytes())
                manifest['registries'][key]['sha256']=new_sha
                if corruption=='arm':manifest['nodes'][node_id]['root_training_evidence']['approval_sha256']=new_sha
                self.repin(args,manifest)
                with self.assertRaises(ValueError):self.load(args,output)

    def test_prepared_extra_atom_rejected_by_approved_source_reconstruction(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as prepared_root,tempfile.TemporaryDirectory() as query_root:
            args,manifest,node_id=self.fixture(directory)
            _candidates,records,_pin=self.load(args,prepared_root)
            args.prepared=Path(prepared_root)/'prepared.json';args.prepared.write_text('{}')
            args.outdir=Path(query_root)
            document=dict(source_manifest_sha256=args.manifest_sha256,sources=records,seed_parameters=dict(cap=5000),atoms=[[1,1,1],[2,2,2]])
            with patch.object(worker,'prepare',return_value=dict(atoms=[[1,1,1]])):
                with self.assertRaisesRegex(ValueError,'differs from approved source reconstruction'):
                    worker.verify_source_binding(args,document,lambda *_barrier:None)


if __name__=='__main__':unittest.main()
