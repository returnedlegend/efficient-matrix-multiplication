import itertools
import unittest
from mmsearch.tensor_code7_even_components import component_basis,minimize_components
from mmsearch.tensor_code7_even_components import select_starts

class ComponentsTests(unittest.TestCase):
 def test_gray_matches_exhaustive_and_composes_disjoint_minima(self):
  cycles=[0b0011,0b0110,0b110000,0b11000000]
  starts=[0b11110101,0b10101010]
  r=minimize_components(starts,cycles,target=-2)
  self.assertTrue(r['complete'])
  for x,w,y in zip(starts,r['weights'],r['states_hex']):
   expected=min((x^__import__('functools').reduce(int.__xor__,[z for i,z in enumerate(cycles) if m>>i&1],0)).bit_count() for m in range(1<<len(cycles)))
   self.assertEqual(w,expected);self.assertEqual(int(y,16).bit_count(),expected)
 def test_shared_coset_cache(self):
  r=minimize_components([3,6],[3,6],target=-2)
  self.assertEqual(r['cache_hits'],1);self.assertEqual(r['enumerated_states'],4);self.assertEqual(r['weights'],[0,0])
 def test_rank_cap_reports_partial_valid_bounds(self):
  r=minimize_components([3],[3,6],max_rank=1,target=-2)
  self.assertFalse(r['complete']);self.assertEqual(r['skipped_components'],1)
  self.assertLessEqual(r['lower_bounds'][0],min((3^z).bit_count() for z in [0,3,6,5]))
 def test_last_enumeration_callback_stop_unknown(self):
  count=0
  def stop():
   nonlocal count
   count+=1;return 'late' if count>=4 else None
  r=minimize_components([3],[3],cancelled=stop,target=-2)
  self.assertFalse(r['complete']);self.assertEqual(r['status'],'UNKNOWN')
 def test_odd_generators_and_odd_starts_rejected(self):
  for starts,cycles in [([3],[1]),([1],[3])]:
   with self.assertRaises(ValueError):minimize_components(starts,cycles)
 def test_even_initialization_respects_cap_and_provenance(self):
  r=select_starts([15,7],[3,7],ceiling=98)
  self.assertEqual(r[0]['kind'],'original_even');self.assertEqual(r[1]['kind'],'odd_initialization')
  self.assertTrue(all(int(t['state_hex'],16).bit_count()%2==0 for t in r))
 def test_checkpoint_is_private_snapshot_and_final_stop_is_unknown(self):
  expired=False
  def callback(value):
   nonlocal expired
   value['components'].clear();value['weights'][0]=99;expired=True
  r=minimize_components([3],[3],checkpoint=callback,cancelled=lambda:expired,target=-2)
  self.assertFalse(r['complete']);self.assertNotEqual(r['weights'],[99]);self.assertEqual(len(r['components']),1)

 def test_prefix_checkpoint_never_claims_all_components_complete(self):
  checkpoints=[]
  result=minimize_components([15],[3,12],checkpoint=checkpoints.append,target=-2)
  self.assertFalse(checkpoints[0]['complete']);self.assertEqual(checkpoints[0]['processed_components'],1)
  self.assertTrue(result['complete']);self.assertEqual(result['processed_components'],2)

 def test_timely_composed_target_stops_before_next_large_solver(self):
  called=[]
  def solver(*_):self.fail('large solver must not run after target')
  r=minimize_components([15],[3,12,24],max_rank=1,target=2,on_target=lambda item:called.append(item) or True,large_solver=solver)
  self.assertTrue(r['target_found']);self.assertEqual(r['processed_components'],1);self.assertEqual(len(called),1)
  self.assertFalse(r['complete']) # Remaining minima are intentionally uncomputed.
