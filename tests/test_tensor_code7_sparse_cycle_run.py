"""Actual tiny pipeline/late-publication controls; no production scan."""
from datetime import datetime,timezone
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import prepare,term_from_atom,second_check
from scripts import tensor_code7_sparse_cycle_run as worker
from scripts.tensor_code7 import Stop


class SparseRuntimeTests(unittest.TestCase):
 def fixture(self):
  candidate=naive_candidate(2)
  candidate['terms'] += [term_from_atom(t,2) for t in ((1,3,2),(2,3,2),(3,3,2))]
  doc=prepare([candidate])
  args=SimpleNamespace(max_trials=10000,max_cycles=1000,max_evaluations=10000,max_negative_candidates=16,
   authorize_seed_scan=True,target_weight=8,code_sha256={})
  return doc,args

 def test_exact_pipeline_finds_planted_zero_padding_reduction(self):
  doc,args=self.fixture()
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);report=worker.run_pipeline(doc,root,lambda *_:None,args,'tiny')
   self.assertTrue(report['winner']);self.assertTrue((root/'first-record-evidence/candidate.json').exists())
   self.assertLessEqual(report['saved'][0]['rank'],8)
   checks=json.loads((root/'first-record-evidence/verification.json').read_bytes())
   self.assertTrue(checks['primary']['valid']);self.assertTrue(checks['independent']['valid'])

 def test_enumeration_only_never_dispatches_candidate_scan(self):
  doc,args=self.fixture();args.authorize_seed_scan=False
  with tempfile.TemporaryDirectory() as directory,patch.object(worker,'scan_seed_deltas') as scan:
   report=worker.run_pipeline(doc,Path(directory),lambda *_:None,args,'tiny')
  scan.assert_not_called();self.assertFalse(report['optimization_called'])

 def test_late_catalogue_retained_hidden_unknown(self):
  doc,args=self.fixture()
  def guard(stage='loop'):
   if stage=='post_enumeration':raise Stop('late_catalogue')
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   with self.assertRaises(Stop):worker.run_pipeline(doc,root,guard,args,'tiny')
   self.assertFalse((root/'catalogue.json').exists())
   raw=json.loads((root/'.raw-enumeration/after-cutoff.json').read_bytes())
   self.assertEqual(raw['status'],'UNKNOWN');self.assertIsNotNone(raw['raw']['catalogue'])

 def test_late_primary_prevents_second_checker_and_publication(self):
  doc,args=self.fixture()
  def guard(stage='loop'):
   if stage=='post_negative_primary':raise Stop('late_primary')
  with tempfile.TemporaryDirectory() as directory,patch.object(worker,'second_check',wraps=second_check) as independent:
   root=Path(directory)
   with self.assertRaises(Stop):worker.run_pipeline(doc,root,guard,args,'tiny')
   independent.assert_not_called();self.assertFalse((root/'first-record-evidence').exists())
   self.assertTrue(list(root.glob('.raw-candidates/*/raw.json')))

 def test_late_after_successful_record_move_quarantines_candidate(self):
  doc,args=self.fixture()
  def guard(stage='loop'):
   if stage=='post_scan_publication':raise Stop('late_scan_receipt')
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   with self.assertRaises(Stop):worker.run_pipeline(doc,root,guard,args,'tiny')
   self.assertFalse((root/'first-record-evidence').exists())
   withheld=list(root.glob('.raw-candidates/withheld-first-record-evidence-*'))
   self.assertEqual(len(withheld),1)
   raw=json.loads((withheld[0]/'raw.json').read_bytes());self.assertEqual(raw['status'],'UNKNOWN')
   self.assertTrue((root/'.raw-scan/incomplete.json').exists())

 def test_actual_main_late_final_guard_revokes_winner(self):
  doc,args=self.fixture()
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);frozen=root/'frozen';frozen.mkdir();prepared=frozen/'p.json';sources=frozen/'s.json';prepared.write_text('{}');sources.write_text('{}')
   qa=root/'qa.json';qa.write_text(json.dumps(dict(status='PASS',prepared_sha256=worker.raw_sha(prepared.read_bytes()),sources_sha256=worker.raw_sha(sources.read_bytes()),
    sparse_core_sha256=worker.raw_sha((worker.REPO/'mmsearch/tensor_code7_sparse_cycles.py').read_bytes()),runtime_sha256=worker.raw_sha(Path(worker.__file__).read_bytes()),runtime_closure_sha256=worker.digest({}))))
   class FakeGuard:
    hard=datetime(2099,1,1,tzinfo=timezone.utc);seconds=120;canonical=SimpleNamespace(signal_stop=False)
    def __init__(self,*_):self.started=time.monotonic()
    def __call__(self,stage='loop'):
     if stage=='post_final_sparse_receipt':raise Stop('late_final')
   out=root/'out';argv=['--campaign-dir',str(root),'--campaign-sha256','fixture','--guard-state',str(root/'guard'),
    '--prepared',str(prepared),'--prepared-sha256',worker.raw_sha(prepared.read_bytes()),'--sources',str(sources),'--sources-sha256',worker.raw_sha(sources.read_bytes()),
    '--outdir',str(out),'--authorize-cycle-enumeration','--authorize-seed-scan','--qa-receipt',str(qa),'--qa-sha256',worker.raw_sha(qa.read_bytes())]
   with patch.object(worker,'DirectGuard',FakeGuard),patch.object(worker,'runtime_hashes',return_value={}),\
     patch.object(worker,'load_root_pinned_native',return_value=doc),patch.object(worker.os,'sched_setaffinity'),\
     patch.object(worker.resource,'setrlimit'),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(worker.main(argv),0)
   report=json.loads((out/'result.json').read_bytes())
   self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(report['winner']);self.assertFalse(report['complete'])
   self.assertFalse((out/'first-record-evidence').exists())
   self.assertTrue(list(out.glob('.raw-candidates/withheld-first-record-evidence-*')))


if __name__=='__main__':unittest.main()
