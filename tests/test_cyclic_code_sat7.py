import json,itertools,multiprocessing as mp,signal,time,unittest
from unittest.mock import patch
from pysat.solvers import Solver
from mmsearch import cyclic_code_sat7 as subject
from mmsearch import cyclic_tensor_code7 as c
from scripts.audit_cyclic_tensor_code7 import audit_columns
from scripts.run_cyclic_code_sat7 import verified_formula_payload,raw
from mmsearch.search import naive_terms
from mmsearch.verify import verify_candidate
from scripts.campaign_native_baseline7 import independent,base

def stalled_worker(problem,seconds,memory_mb,sender,assumptions=()):
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    while True:time.sleep(.01)

def malformed_worker(problem,seconds,memory_mb,sender,assumptions=()):
    sender.send(dict(status='SAT',assignment=[None,False]));sender.close()

def planted_problem(budget=8):
    naive=list(naive_terms(2));a,b=1,8;relation=[(a,a,a),(b,b,b),(a^b,a^b,a^b),*c.orbit((a,a,b),2),*c.orbit((a,b,b),2)]
    alternate=sorted(set(naive)^set(relation));dictionary,_=audit_columns(naive+relation,alternate,2)
    p=subject.build_problem([int(v,16) for v in dictionary['compressed_columns_hex']],int(dictionary['compressed_target_hex'],16),int(dictionary['seed_state_hex'],16),[int(v,16) for v in dictionary['kernel_hex']],dictionary['weights'],dictionary['rank'],budget)
    return p,dictionary

class CyclicCodeSATControls(unittest.TestCase):
    def test_exhaustive_cardinality_projection(self):
        checks=0
        for n in range(5):
            weights=[3]*n+[1]*5;size=len(weights)
            for budget in (2,5,8,11,14):
                p=subject.build_problem([0]*size,0,0,[1<<i for i in range(size)],weights,0,budget)
                with Solver(name='g3',bootstrap_with=p['clauses']) as solver:
                    for values in itertools.product((False,True),repeat=size):
                        assumptions=[v if x else -v for v,x in zip(p['orbit_variables'],values)];actual=solver.solve(assumptions=assumptions)
                        self.assertEqual(actual,sum(w for w,x in zip(weights,values) if x)<=budget);checks+=1
        self.assertEqual(checks,4960)
        for nf,cubes in itertools.product(range(362),range(6)):self.assertEqual(3*nf+cubes<=92,nf<=29 or(nf<=30 and cubes<=2))
    def test_persisted_formula_exact_bytes_and_json_roundtrip(self):
        p,_=planted_problem();parsed=verified_formula_payload(raw(p),p);self.assertEqual(parsed['metadata']['formula_sha256'],p['metadata']['formula_sha256'])
        with self.assertRaises(ValueError):verified_formula_payload(raw(p)+b' ',p)
        changed=json.loads(raw(p));changed['clauses'].append([])
        with self.assertRaises(ValueError):verified_formula_payload(raw(changed),p)
    def test_kernel_rank_and_budget_validation(self):
        p,_=planted_problem();self.assertEqual(sum(p['weights'][i] for i in range(len(p['weights'])) if p['seed']>>i&1),13)
        with self.assertRaises(ValueError):subject.build_problem([1],1,0,[],[1],1,2)
        with self.assertRaises(ValueError):subject.build_problem([0],0,0,[],[1],0,2)
        with self.assertRaises(ValueError):subject.build_problem([0],0,0,[1],[1],0,3)
    def test_real_planted_finite_code_sat_unsat_and_model_rejection(self):
        p,d=planted_problem();persisted=verified_formula_payload(raw(p),p);r=subject.solve(persisted,seconds=5,memory_mb=256);self.assertEqual(r['status'],'SAT',r);self.assertEqual(r['product_cost'],8);self.assertTrue(r['worker_reaped']);self.assertTrue(r['finite_code_membership_verified'])
        code=c.TinyOrbitCode(2,tuple(tuple(v) for v in d['representatives']),tuple(int(v,16) for v in d['compressed_columns_hex']),tuple(d['weights']),True);candidate=code.candidate(int(r['state_hex'],16));self.assertEqual(len(candidate['terms']),8);self.assertTrue(verify_candidate(candidate,random_trials=0)['valid']);self.assertEqual(independent(candidate,base.raw_json(candidate))['exact_entries_checked'],64)
        for bad in [r['complete_assignment'][:-1],[None]+[0]*(p['nv'])]:
            with self.assertRaises(AssertionError):subject.validate_decode(p,bad)
        bad=list(r['complete_assignment']);bad[p['orbit_variables'][0]]=not bad[p['orbit_variables'][0]]
        with self.assertRaises(AssertionError):subject.validate_decode(p,bad)
        q,_=planted_problem(5);u=subject.solve(q,seconds=5,memory_mb=256);self.assertEqual(u['status'],'FINITE_CODE_UNSAT');self.assertTrue(u['finite_dictionary_complete']);self.assertTrue(u['worker_reaped'])
    def test_malformed_worker_and_private_formula_tamper(self):
        p,_=planted_problem()
        with patch.object(subject,'worker',malformed_worker):r=subject.solve(p,seconds=5,memory_mb=256)
        self.assertEqual(r['status'],'ERROR');self.assertTrue(r['worker_reaped']);self.assertFalse(r['publication_eligible'])
        def mutate():p['clauses'].append([]);return False
        r=subject.solve(p,seconds=1,memory_mb=256,cancelled=mutate);self.assertEqual(r['status'],'UNKNOWN');self.assertEqual(r['reason'],'formula_changed');self.assertFalse(r['worker_started'])
    def test_late_sat_and_stalled_worker_reaped(self):
        p,_=planted_problem();flag=[False];original=subject.validate_decode
        def late(*a,**kw):
            value=original(*a,**kw);flag[0]=True;return value
        with patch.object(subject,'validate_decode',late):r=subject.solve(p,seconds=5,memory_mb=256,cancelled=lambda:flag[0])
        self.assertEqual(r['status'],'UNKNOWN');self.assertTrue(r['worker_reaped']);self.assertFalse(r['publication_eligible'])
        before={x.pid for x in mp.active_children()};start=time.monotonic()
        with patch.object(subject,'worker',stalled_worker):r=subject.solve(p,seconds=.2,memory_mb=256)
        self.assertEqual(r['status'],'UNKNOWN');self.assertTrue(r['worker_reaped']);self.assertLess(time.monotonic()-start,1);self.assertEqual({x.pid for x in mp.active_children()},before)
if __name__=='__main__':unittest.main()
