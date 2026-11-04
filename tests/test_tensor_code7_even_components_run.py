import contextlib,io,json,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import prepare,term_from_atom
from mmsearch.tensor_code7_sparse_cycles import enumerate_cycles
from scripts import tensor_code7_even_components as worker
from scripts import tensor_code7_sparse_cycle_run as gate
from scripts.tensor_code7 import Stop

class ComponentRuntimeTests(unittest.TestCase):
 def fixture(self,root):
  c=naive_candidate(2);c['terms'] += [term_from_atom(t,2) for t in [(3,3,7),(3,5,9),(3,6,7),(3,5,14)]]
  doc=prepare([c]);cat=enumerate_cycles([tuple(t) for t in doc['atoms']],2);path=root/'catalogue.json';worker.write_json(path,cat)
  return doc,SimpleNamespace(catalogue=path,catalogue_sha256=worker.raw_sha(path.read_bytes()),max_rank=20,max_states=10000,target_weight=8,code_sha256={})
 def test_actual_planted_full_tensor_composition_finds_target(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);doc,args=self.fixture(root);r=worker.run_pipeline(doc,root,lambda *_:None,args,'tiny')
   self.assertTrue(r['winner']);self.assertEqual(r['saved'][0]['rank'],8)
   self.assertTrue((root/'first-record-evidence/candidate.json').exists())
 def test_late_primary_blocks_second_checker(self):
  def guard(stage='loop'):
   if stage=='post_negative_primary':raise Stop('late')
  with tempfile.TemporaryDirectory() as td,patch.object(gate,'second_check') as second:
   root=Path(td);doc,args=self.fixture(root)
   with self.assertRaises(Stop):worker.run_pipeline(doc,root,guard,args,'tiny')
   second.assert_not_called();self.assertFalse((root/'first-record-evidence').exists());self.assertTrue(list(root.glob('.raw-candidates/*/raw.json')))
 def test_late_after_composed_publication_quarantines(self):
  def guard(stage='loop'):
   if stage=='post_components_publication':raise Stop('late')
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);doc,args=self.fixture(root)
   with self.assertRaises(Stop):worker.run_pipeline(doc,root,guard,args,'tiny')
   self.assertFalse((root/'first-record-evidence').exists());self.assertTrue(list(root.glob('.raw-candidates/withheld-first-record-evidence-*')))
 def test_main_late_final_revokes_target(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);doc,args=self.fixture(root);frozen=root/'frozen';frozen.mkdir();p=frozen/'p.json';s=frozen/'s.json';p.write_text('{}');s.write_text('{}');qa=root/'qa.json'
   qa.write_text(json.dumps(dict(status='PASS',prepared_sha256=worker.raw_sha(p.read_bytes()),sources_sha256=worker.raw_sha(s.read_bytes()),component_core_sha256=worker.raw_sha((worker.REPO/'mmsearch/tensor_code7_even_components.py').read_bytes()),catalogue_sha256=args.catalogue_sha256,runtime_sha256=worker.raw_sha(Path(worker.__file__).read_bytes()),runtime_closure_sha256=worker.digest({}),dependency_closure_sha256=worker.digest({}))))
   class Guard:
    hard=datetime(2099,1,1,tzinfo=timezone.utc);seconds=120;canonical=SimpleNamespace(signal_stop=False)
    def __init__(self,*_):self.started=time.monotonic()
    def __call__(self,stage='loop'):
     if stage=='post_final_sparse_receipt':raise Stop('latefinal')
   out=root/'out';argv=['--campaign-dir',str(root),'--campaign-sha256','tiny','--guard-state',str(root/'guard'),'--prepared',str(p),'--prepared-sha256',worker.raw_sha(p.read_bytes()),'--sources',str(s),'--sources-sha256',worker.raw_sha(s.read_bytes()),'--catalogue',str(args.catalogue),'--catalogue-sha256',args.catalogue_sha256,'--outdir',str(out),'--authorize-component-search','--qa-receipt',str(qa),'--qa-sha256',worker.raw_sha(qa.read_bytes())]
   original=worker.run_pipeline
   def pipeline(*values):values[3].target_weight=8;return original(*values)
   with patch.object(worker,'DirectGuard',Guard),patch.object(worker,'runtime_hashes',return_value={}),patch.object(worker,'dependency_hashes',return_value={}),patch.object(worker,'load_root_pinned_native',return_value=doc),patch.object(worker,'run_pipeline',side_effect=pipeline),patch.object(worker.os,'sched_setaffinity'),patch.object(worker.resource,'setrlimit'),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(worker.main(argv),0)
   report=json.loads((out/'result.json').read_bytes());self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(report['winner']);self.assertFalse((out/'first-record-evidence').exists());self.assertTrue(list(out.glob('.raw-candidates/withheld-first-record-evidence-*')))
