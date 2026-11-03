"""Native contract controls; no N5 optimization or trusted rank from inventory."""
from datetime import datetime,timezone
import contextlib
import io
import time
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mmsearch.tensor import naive_candidate,strassen_candidate
from mmsearch.tensor_code7 import digest,prepare
from mmsearch.tensor_code7_native_corpus import (native_bytes,parse_native,parse_json_candidate,
 identities,candidate_from_atoms,choose_diverse,command_pairs,build_prepared,load_sources)
from scripts import tensor_code7_native_corpus as runner
from scripts.tensor_code7 import Stop


class NativeCorpusTests(unittest.TestCase):
 def test_literal_native_text_roundtrip(self):
  atoms=((1,1,1),(8,8,8));raw=native_bytes(atoms)
  self.assertEqual(parse_native(raw,2),atoms)
  self.assertEqual(identities(atoms)['term_set_sha256'],runner.raw_sha(raw))

 def test_text_schema_corruption_rejected(self):
  for raw in (b'0 1 1\n',b'1 1 1\n1 1 1\n',b'01 1 1\n',b'1.0 1 1\n',b'1  1 1\n',b'16 1 1\n',b'1 1 1',b'8 8 8\n1 1 1\n',b'-1 1 1\n'):
   with self.subTest(raw=raw),self.assertRaises(ValueError):parse_native(raw,2)

 def test_json_literal_coefficients_and_field_types(self):
  candidate=naive_candidate(2)
  for bad in (True,1.0,2,-1):
   value=json.loads(json.dumps(candidate));value['terms'][0]['u'][0]=bad
   with self.assertRaises(ValueError):parse_json_candidate(json.dumps(value),2)
  for field in (2.0,True):
   with self.assertRaises(ValueError):parse_json_candidate(json.dumps(dict(candidate,field=field)),2)
  value=json.loads(json.dumps(candidate));value['terms'].append(value['terms'][0])
  with self.assertRaises(ValueError):parse_json_candidate(json.dumps(value),2)

 def test_generic_tiny_math_has_both_verified_parities(self):
  candidates=[naive_candidate(2),strassen_candidate(2)];old=prepare([candidates[0]])
  document=build_prepared(candidates,[],digest('tiny'),old)
  self.assertEqual(set(document['seed_weights']),{7,8});self.assertTrue(document['parity_broken'])
  self.assertEqual(document['rank']+document['nullity'],document['dictionary_size'])

 def test_production_math_requires_authenticated_native_receipt(self):
  with self.assertRaisesRegex(ValueError,'authenticated source receipt'):
   build_prepared([dict(dimension=5)],[],'untrusted',dict(atoms=[]))

 def test_deterministic_diversity_and94_interaction_selection(self):
  # Synthetic inventory labels only; no exact93/94 claim follows from selection.
  records=[];data={}
  for i,(run,rank,atoms) in enumerate([('a',93,{1,2,3}),('b',93,{3,4,5}),('a',93,{1,2,4}),('b',94,{1,2,3,4})]):
   key=f'id{i}';records.append(dict(run=run,rank=rank,identity=key,raw_sha256=key));data[key]=atoms
  selected,report=choose_diverse(records,lambda r:data[r['identity']],2,1)
  other,_=choose_diverse(list(reversed(records)),lambda r:data[r['identity']],2,1)
  self.assertEqual(selected,other);self.assertEqual([r['rank'] for r in selected],[93,93,94])
  self.assertFalse(report['full_tensor_checks_performed']);self.assertFalse(report['optimization_called'])

 def test_native_command_rejects_extra_data_sources_and_duplicates(self):
  valid=['worker','--input','input','--output','walk','--n','5','--target','92']
  self.assertEqual(command_pairs(valid)['--input'],'input')
  for extra in (['--pool','eval'],['--input','other'],['--n','5']):
   with self.assertRaises(ValueError):command_pairs(valid+extra)

 def test_source_schema_and_rank_policy_not_inventory_authority(self):
  with self.assertRaises(ValueError):load_sources(dict(schema='old'), 'x','/tmp','/tmp',lambda *_:b'',lambda *_:None)

 def test_poll_checks_UTC_every_callback_and_force_stages(self):
  class Fake:
   hard=datetime(2000,1,1,tzinfo=timezone.utc);started=0;seconds=120;canonical=SimpleNamespace(signal_stop=False)
   def __call__(self,*_):raise AssertionError('knownexpired callback muststopbeforedatareads')
  poll=runner.Poll(Fake())
  with self.assertRaises(Stop):poll()

 def test_output_cap_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   with self.assertRaises(Stop):runner.output_check(root,runner.OUTPUT_LIMIT+1)

 def test_late_final_publication_hides_prepared_and_returns_unknown(self):
  for barrier in ('pre_final_native_result','post_final_native_result'):
   with self.subTest(barrier=barrier),tempfile.TemporaryDirectory() as directory:
    root=Path(directory);base=root/'base';base.mkdir();path=base/'prepared.json';path.write_text('{}')
    manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(authority=dict(base_prepared=dict(path=str(path))))))
    candidates=[naive_candidate(2),strassen_candidate(2)];old=prepare([candidates[0]])
    records=[dict(canonical_certificate_sha256=runner.raw_sha((json.dumps(c,sort_keys=True,indent=2)+'\n').encode())) for c in candidates]
    class FakeGuard:
     hard=datetime(2099,1,1,tzinfo=timezone.utc);seconds=120;canonical=SimpleNamespace(signal_stop=False)
     def __init__(self,*_):self.started=time.monotonic()
     def __call__(self,stage='loop'):
      if stage==barrier:raise Stop('synthetic_late_finalization')
    out=root/'out'
    args=['prepare','--campaign-dir',str(root),'--campaign-sha256','fixture','--guard-state',str(root/'guard'),
      '--manifest',str(manifest),'--manifest-sha256',runner.raw_sha(manifest.read_bytes()),'--outdir',str(out),'--authorize-native-preparation']
    with patch.object(runner,'DirectGuard',FakeGuard),patch.object(runner,'load_sources',return_value=(candidates,records,old,None)),      patch.object(runner,'code_hashes',return_value={}),patch.object(runner.os,'sched_setaffinity'),      patch.object(runner.resource,'setrlimit'),contextlib.redirect_stdout(io.StringIO()):
     self.assertEqual(runner.main(args),0)
    result=json.loads((out/'result.json').read_bytes())
    self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
    self.assertFalse((out/'prepared.json').exists());self.assertFalse((out/'certificates').exists())
    self.assertTrue((out/'.inputs/after-cutoff-prepared.json').exists())


if __name__=='__main__':unittest.main()
