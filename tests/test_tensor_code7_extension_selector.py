"""Exact tiny tests for the separate pair-escape selector; no N5 generation."""
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import digest,prepare,supports
from mmsearch.tensor_code7_extension import build_extension,raw_sha
from mmsearch.tensor_code7_extension_selector import (AXIS_ORDERS,pair_column,span,remainder,
    projection_diagnostics,select_witnesses)


class TensorCodeExtensionSelectorTests(unittest.TestCase):
    def fixture(self):
        base=prepare([naive_candidate(2)])
        return base,[tuple(t) for t in base['atoms']],int(base['seed_states_hex'][0],16)

    def test_cross_escape_exactly_equals_projected_rank_gain(self):
        base,atoms,seed=self.fixture()
        outside=projection_diagnostics(atoms,seed,[0,7],[0,1,2],2)
        inside=projection_diagnostics(atoms,seed,[0,5],[0,1,2],2)
        self.assertTrue(outside['seed_pair_span_escape']);self.assertTrue(outside['global_pair_span_escape'])
        self.assertEqual(outside['seed_pair_rank_gain'],1)
        self.assertFalse(inside['seed_pair_span_escape']);self.assertEqual(inside['seed_pair_rank_gain'],0)
        for parents in ([0,7],[0,5]):
            from mmsearch.tensor_code7_extension import plus_atoms
            new=plus_atoms(atoms[parents[0]],atoms[parents[1]],[0,1,2],2)
            oldpairs=[pair_column(t[0],t[1],4) for t in atoms]
            actual=len(span(oldpairs+[pair_column(t[0],t[1],4) for t in new]))-len(span(oldpairs))
            self.assertEqual(actual,projection_diagnostics(atoms,seed,parents,[0,1,2],2)['global_pair_rank_gain'])

    def test_global_pair_span_can_be_larger_than_seed_pair_span(self):
        base,atoms,seed=self.fixture()
        from mmsearch.tensor_code7_extension import plus_atoms
        atoms+=plus_atoms(atoms[0],atoms[7],[0,1,2],2)
        result=projection_diagnostics(atoms,seed,[0,7],[0,1,2],2)
        self.assertTrue(result['seed_pair_span_escape']);self.assertFalse(result['global_pair_span_escape'])
        self.assertGreater(result['global_pair_span_rank'],result['seed_pair_span_rank'])

    def test_all_axis_orders_have_at_most_one_projected_new_direction(self):
        base,atoms,seed=self.fixture()
        from mmsearch.tensor_code7_extension import plus_atoms
        for order in AXIS_ORDERS:
            new=plus_atoms(atoms[0],atoms[7],list(order),2)
            old=[pair_column(t[order[0]],t[order[1]],4) for t in atoms]
            newpairs=[pair_column(t[order[0]],t[order[1]],4) for t in new]
            actual=len(span(old+newpairs))-len(span(old))
            diag=projection_diagnostics(atoms,seed,[0,7],order,2)
            self.assertLessEqual(actual,1);self.assertEqual(actual,diag['seed_pair_rank_gain'])

    def test_bounded_deterministic_selector_only_emits_seed_escapes(self):
        base,atoms,seed=self.fixture();pin=digest(base)
        left,audit=select_witnesses(base,pin,max_relations=4,max_new_atoms=12,max_attempts=168)
        right,other=select_witnesses(base,pin,max_relations=4,max_new_atoms=12,max_attempts=168)
        self.assertEqual(left,right);self.assertEqual(audit,other)
        self.assertLessEqual(audit['attempted_pair_axis_records'],168)
        self.assertEqual(audit['accepted_relations'],4)
        self.assertFalse(audit['target_query_called'])
        self.assertTrue(all(item['diagnostics']['seed_pair_span_escape'] for item in audit['selected']))
        self.assertTrue(all(item['independent_full_zero_check']['valid'] for item in audit['selected']))
        self.assertLessEqual(audit['derived_new_atom_count'],12)
        document=build_extension(base,left,pin,digest(left))
        self.assertTrue(document['parity_broken'])
        self.assertEqual(document['seed_states_hex'],base['seed_states_hex'])

    def test_odd_relations_inside_pair_space_are_not_used_as_escape_evidence(self):
        base,atoms,seed=self.fixture()
        inside=projection_diagnostics(atoms,seed,[0,5],[0,1,2],2)
        self.assertFalse(inside['seed_pair_span_escape'])
        manifest,audit=select_witnesses(base,digest(base),max_relations=16,max_new_atoms=100,max_attempts=168)
        self.assertGreater(audit['inside_seed_skipped'],0)
        self.assertTrue(all(item['diagnostics']['seed_pair_span_escape'] for item in audit['selected']))

    def test_membership_remainder_is_full_reduction_not_early_stop(self):
        basis=span([0b101,0b010])
        self.assertEqual(remainder(basis,0b111),0)
        self.assertEqual(remainder(basis,0b110),0b001)

    def test_bounds_literal_types_and_coactivity_fail_closed(self):
        base,atoms,seed=self.fixture()
        for args in (dict(max_attempts=8193),dict(max_relations=17),dict(max_new_atoms=101),dict(max_attempts=True),dict(require_seed_escape=False)):
            with self.assertRaises(ValueError):select_witnesses(base,digest(base),**args)
        with self.assertRaises(ValueError):projection_diagnostics(atoms,seed^1,[0,7],[0,1,2],2)
        with self.assertRaises(ValueError):pair_column(True,1,4)
        with self.assertRaises(ValueError):projection_diagnostics(atoms,-1,[0,7],[0,1,2],2)

    def test_disabled_cli_never_opens_base_input(self):
        script=Path(__file__).resolve().parents[1]/"scripts/tensor_code7_extension_select.py"
        completed=subprocess.run([sys.executable,"-B",str(script),"--base-prepared","/DO_NOT_READ"],capture_output=True,text=True,check=True)
        report=json.loads(completed.stdout)
        self.assertFalse(report["production_inputs_read"]);self.assertFalse(report["n5_witnesses_generated"])
        self.assertFalse(report["target_query_called"])

    def test_expired_authorized_cli_returns_unknown_before_base_io(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);campaign=root/"campaign.json"
            campaign.write_text(json.dumps(dict(deadline_utc="2000-01-01T00:00:00Z")))
            script=Path(__file__).resolve().parents[1]/"scripts/tensor_code7_extension_select.py"
            command=[sys.executable,"-B",str(script),"--authorize-witness-generation","--qa-approval","root-reviewed",
                "--base-prepared","/DO_NOT_READ","--base-sha256","0"*64,"--source-manifest","/DO_NOT_READ",
                "--source-manifest-sha256","0"*64,"--approved-root","/DO_NOT_READ","--campaign-dir",str(root),
                "--campaign-sha256",raw_sha(campaign.read_bytes()),"--guard-state",str(root/"missing-resource.json"),
                "--hard-utc","2000-01-01T00:00:00Z","--outdir",str(root/"DO_NOT_CREATE")]
            completed=subprocess.run(command,capture_output=True,text=True,check=True)
            report=json.loads(completed.stdout)
            self.assertEqual(report["status"],"UNKNOWN");self.assertFalse(report["complete"])
            self.assertFalse(report["production_inputs_read"]);self.assertFalse((root/"DO_NOT_CREATE").exists())

    def test_no_n5_witness_generation_without_separate_receipt(self):
        with self.assertRaisesRegex(ValueError,'authenticated base receipt'):
            select_witnesses(dict(dimension=5,dictionary_sha256='untrusted'), 'untrusted')


if __name__=='__main__':unittest.main()
