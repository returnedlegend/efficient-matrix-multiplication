"""Tiny exact catalogue/delta controls; no production enumeration or scan."""
import copy
import itertools
import unittest

from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import atom_column,atom_from_term,term_from_atom,xor_columns
from mmsearch.tensor_code7_sparse_cycles import enumerate_cycles,validate_catalogue,scan_seed_deltas
from mmsearch.verify import verify_candidate


class SparseCycleTests(unittest.TestCase):
 def test_merge3_complete_zero_and_scan_improves_planted_zero_padding(self):
  base=[atom_from_term(t,2) for t in naive_candidate(2)['terms']]
  atoms=base+[(1,3,2),(2,3,2),(3,3,2)]
  cat=enumerate_cycles(atoms,2);cycles=validate_catalogue(cat,atoms,2)
  expected=sum(1<<i for i in (8,9,10));self.assertIn(expected,cycles)
  seed=(1<<len(atoms))-1;seen=[]
  scan=scan_seed_deltas([seed],cycles,on_negative=lambda item:seen.append(item) or False)
  self.assertTrue(scan['complete']);self.assertTrue(any(x['state_hex']==hex((1<<8)-1) for x in seen))
  for item in seen:
   state=int(item['state_hex'],16);candidate=dict(dimension=2,field=2,terms=[term_from_atom(a,2) for i,a in enumerate(atoms) if state>>i&1])
   self.assertTrue(verify_candidate(candidate)['valid'])

 def test_shared_factor_flip4_is_exact_all_inside(self):
  atoms=[(1,1,1),(1,2,2),(1,3,1),(1,2,3)]
  cat=enumerate_cycles(atoms,2);validate_catalogue(cat,atoms,2)
  self.assertTrue(cat['complete']);self.assertTrue(any(r['weight']==4 and int(r['mask_hex'],16)==15 for r in cat['cycles']))

 def test_plus5_all_six_axis_orders_have_verified_witness(self):
  original=[(1,1,1),(2,2,2),(3,1,1),(2,1,3),(2,3,2)]
  for order in itertools.permutations(range(3)):
   atoms=[tuple(t[i] for i in order) for t in original]
   cat=enumerate_cycles(atoms,2);masks=validate_catalogue(cat,atoms,2)
   self.assertIn(31,masks);self.assertEqual(masks.count(31),1)
   self.assertEqual(xor_columns([atom_column(a,2) for a in atoms],31),0)

 def test_required_point_missing_never_invented(self):
  atoms=[(1,1,1),(2,2,2),(3,1,1),(2,1,3)]
  cat=enumerate_cycles(atoms,2);self.assertFalse(any(r['weight']==5 for r in cat['cycles']))
  self.assertTrue(cat['complete'])

 def test_trial_and_cancellation_caps_are_unknown_not_negative_proofs(self):
  atoms=[(1,1,1),(2,2,2),(3,1,1),(2,1,3),(2,3,2)]
  partial=enumerate_cycles(atoms,2,max_trials=1)
  self.assertFalse(partial['complete']);self.assertEqual(partial['status'],'UNKNOWN');self.assertEqual(partial['stop_reason'],'trial_cap')
  stopped=enumerate_cycles(atoms,2,cancelled=lambda:'synthetic_clock')
  self.assertFalse(stopped['complete']);self.assertEqual(stopped['trials'],0)

 def test_corrupt_mask_weight_and_identity_rejected(self):
  atoms=[(1,1,1),(2,2,2),(3,1,1),(2,1,3),(2,3,2)];cat=enumerate_cycles(atoms,2)
  for key,value in [('mask_hex','0x1'),('weight',5.0),('family','merge3')]:
   bad=copy.deepcopy(cat);bad['cycles'][0][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):validate_catalogue(bad,atoms,2)

 def test_scan_delta_is_exact_and_does_not_feed_back(self):
  seeds=[3,1];cycles=[7]
  seen=[];report=scan_seed_deltas(seeds,cycles,on_negative=lambda item:seen.append(item) or False)
  self.assertEqual(report['evaluated'],2);self.assertEqual(len(seen),1)
  self.assertEqual(seen[0]['delta'],-1);self.assertEqual(seen[0]['new_weight'],1)
  self.assertEqual(seeds,[3,1])

 def test_scan_cap_and_callback_stop_are_explicit_partial(self):
  report=scan_seed_deltas([3,3],[7],max_evaluations=1)
  self.assertFalse(report['complete']);self.assertEqual(report['stop_reason'],'evaluation_cap')
  report=scan_seed_deltas([3,3],[7],on_negative=lambda _:True)
  self.assertFalse(report['complete']);self.assertEqual(report['stop_reason'],'callback_stop')

 def test_literal_bounds_and_duplicate_atoms_fail(self):
  for args in [dict(max_trials=True),dict(max_cycles=10001),dict(n=2.0)]:
   with self.assertRaises(ValueError):enumerate_cycles([(1,1,1)],**({'n':2}|args))
  with self.assertRaises(ValueError):enumerate_cycles([(1,1,1),(1,1,1)],2)


if __name__=='__main__':unittest.main()
