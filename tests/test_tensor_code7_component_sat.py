import unittest
from mmsearch.tensor_code7_component_sat import solve_bound,minimize_local
from mmsearch.tensor_code7_even_components import component_basis

class ComponentSatTests(unittest.TestCase):
 def test_actual_native_sat_unsat_models_match_bruteforce(self):
  for origin in [0,1,3,7,15]:
   basis=[3,6];support=7;origin&=support
   values=[origin,origin^3,origin^6,origin^3^6];minimum=min(x.bit_count() for x in values)
   result=minimize_local(origin,basis,support,seconds=5)
   self.assertTrue(result['complete'],result);self.assertEqual(result['upper_bound'],minimum)
   self.assertIn(int(result['minimizer_hex'],16),values)
   for q in result['queries']:self.assertTrue(q['worker_reaped'])
 def test_direct_unsat_and_sat_boundary(self):
  self.assertEqual(solve_bound(1,[3],3,0,seconds=3)['status'],'UNSAT')
  self.assertEqual(solve_bound(3,[3],3,0,seconds=3)['status'],'SAT')
 def test_cancel_before_dispatch(self):
  r=solve_bound(3,[3],3,0,cancelled=lambda:'stop')
  self.assertEqual(r['status'],'UNKNOWN');self.assertFalse(r['solver_called'])
 def test_unknown_does_not_become_exact(self):
  def fake(*_):return dict(status='UNKNOWN',reason='late',cpu_seconds=0)
  r=minimize_local(3,[3],3,solve=fake)
  self.assertFalse(r['complete']);self.assertEqual(r['lower_bound'],0);self.assertEqual(r['upper_bound'],2)
 def test_invalid_sat_model_rejected(self):
  def fake(*_):return dict(status='SAT',state_hex='0x1',cpu_seconds=0)
  with self.assertRaises(ValueError):minimize_local(3,[3],3,solve=fake)

 def test_nontriangular_input_basis_normalized_and_dependent_rejected(self):
  for basis in ([3,6],[6,3]):
   r=minimize_local(5,basis,7,seconds=5)
   self.assertTrue(r['complete']);self.assertEqual(r['upper_bound'],0)
  with self.assertRaises(ValueError):solve_bound(3,[3,3],3,0)
 def test_callback_cannot_mutate_private_basis_snapshot(self):
  source=[3]
  def fake(*args):
   source[:]=[5]
   self.assertIsInstance(args[1],tuple)
   return dict(status='SAT',state_hex='0x0',cpu_seconds=0)
  r=minimize_local(3,source,3,solve=fake)
  self.assertTrue(r['complete']);self.assertEqual(r['upper_bound'],0)
 def test_late_query_callback_is_unknown_with_raw(self):
  expired=False
  def fake(*_):
   nonlocal expired
   expired=True;return dict(status='SAT',state_hex='0x0',cpu_seconds=0)
  r=minimize_local(3,[3],3,cancelled=lambda:expired,solve=fake)
  self.assertFalse(r['complete']);self.assertEqual(r['upper_bound'],2);self.assertIn('raw',r['queries'][0])

 def test_early_return_rejects_malformed_binary_state_and_budget(self):
  for origin,support,seconds in [(-1,3,1),(True,3,1),(0,-1,1),(0,True,1),(0,3,float('nan')),(0,3,True)]:
   with self.assertRaises(ValueError):minimize_local(origin,[3],support,seconds=seconds)
  with self.assertRaises(ValueError):solve_bound(0,[3],-1,0)
