"""Independent literal gates, tiny models and bounded Fano branch lifecycle."""
import importlib.util
import itertools
import signal
import time
import unittest
from unittest.mock import patch
from mmsearch import fano_quotient_sat7 as subject
from mmsearch.fano_quotient_worker7 import worker

CMS=importlib.util.find_spec('pycryptosat') is not None


def stalled_worker(problem,seconds,memory_mb,sender,assumptions=()):
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    while True:time.sleep(.01)


def inverse_columns(columns):
    # Exhaustive 16-vector multiplication, independent of subject's GE helpers.
    lookup={}
    for v in range(16):
        out=0
        for k in range(4):
            if v>>k&1:out^=columns[k]
        lookup.setdefault(out,v)
    if len(lookup)!=16:return None
    return [lookup[1<<c] for c in range(4)]


def literal_assignment(problem,factors):
    a=[False]*(problem['nv']+1)
    def put(variables,value):
        for k,v in enumerate(variables):a[v]=bool(value>>k&1)
    raw=[]
    for p,(u,v) in enumerate(factors):
        put(problem['u_variables'][p],u);put(problem['v_variables'][p],v)
        cells=0
        for i in range(problem['rows']):
            for j in range(problem['columns']):
                cells|=((u>>i&1)&(v>>j&1))<<(i*problem['columns']+j)
        raw.append(cells);put(problem['product_variables'][p],cells)
    space_lookup={}
    for coordinate in range(1 << len(problem['space_basis'])):
        raw_value=0
        for t,point in enumerate(problem['space_basis']):
            if coordinate>>t&1:raw_value^=point
        space_lookup[raw_value]=coordinate
    qcols=[]
    for ell,indices in enumerate(((3,0,1),(4,0,2),(5,1,2),(6,0,1,2))):
        s=0
        for p in indices:s^=raw[p]
        z=space_lookup[s]
        put(problem['z_variables'][ell],z)
        q=0
        for t in range(len(problem['space_basis'])):
            if z>>t&1:q^=problem['quotient_columns'][t]
        qcols.append(q)
        for r in range(4):a[problem['a_variables'][r][ell]]=bool(q>>r&1)
    inverse=inverse_columns(qcols)
    for c in range(4):
        for k in range(4):a[problem['inverse_variables'][k][c]]=bool(inverse is not None and inverse[c]>>k&1)
    for r,c,k in itertools.product(range(4),repeat=3):
        a[problem['inverse_product_variables'][r][c][k]]=a[problem['a_variables'][r][k]] and a[problem['inverse_variables'][k][c]]
    return a,inverse is not None


def accepted(problem,assignment):
    return (all(any(assignment[abs(v)]==(v>0) for v in row) for row in problem['clauses']) and
            all((sum(assignment[v] for v in row)%2)==rhs for row,rhs in problem['xors']))


class FanoEncoderControls(unittest.TestCase):
    def tiny(self):return subject.build_problem([1,2,4,8,0,1],2,2,[],[1,2,4,8])

    def test_and_gate_exhaustive_all_eight_truth_assignments(self):
        clauses=subject.and_clauses(1,2,3)
        for x,y,z in itertools.product((False,True),repeat=3):
            a=[None,x,y,z]
            self.assertEqual(all(any(a[abs(v)]==(v>0) for v in row) for row in clauses),z==(x and y))

    def test_exhaustive_625_restricted_models_and_literal_inverse(self):
        problem=self.tiny();passed=0
        elementary=[(0,0),(1,1),(1,2),(2,1),(2,2)]
        for choices in itertools.product(elementary,repeat=4):
            model,invertible=literal_assignment(problem,[(0,0)]*3+list(choices))
            self.assertEqual(accepted(problem,model),invertible)
            if invertible:
                decoded=subject.validate_decode(problem,model);passed+=1
                self.assertEqual(len(decoded['target_coordinates']),6)
                self.assertEqual(decoded['target_coordinates'][4],0)
                self.assertEqual(decoded['target_coordinates'][0],decoded['target_coordinates'][5])
        self.assertEqual(passed,24)

    def test_nonindependent_seven_points_and_zero_factors_are_sound(self):
        problem=self.tiny();model,_=literal_assignment(problem,[(0,0)]*3+[(1,1),(1,2),(2,1),(2,2)])
        result=subject.validate_decode(problem,model)
        self.assertEqual(len(result['support']),4)
        self.assertTrue(result['all_raw_slices_verified'])
        for variable in (problem['product_variables'][0][0],problem['a_variables'][0][0],problem['inverse_variables'][0][0]):
            bad=list(model);bad[variable]=not bad[variable]
            with self.assertRaises(AssertionError):subject.validate_decode(problem,bad)

    def test_original_backbone_points_and_quotient_syndromes(self):
        # Original rank-one 27 and 16 reduce to 27 and 11; 11 has rank two.
        points=[dict(left=3,right=3,column=27),dict(left=2,right=2,column=16)]
        p=subject.build_problem([1<<i for i in range(6)],2,3,points,[1<<i for i in range(6)])
        self.assertEqual(p['backbone_points'],points)
        for x in range(64):
            q=0
            for t in range(6):
                if x>>t&1:q^=p['quotient_columns'][t]
            self.assertEqual(q==0,x in (0,27,16,27^16))
        self.assertEqual(p['metadata']['cover_budget'],9)

    def test_shape_model_and_backbone_rejections(self):
        for kwargs in [dict(targets=[1,2,4,8],rows=True,columns=2,backbone_points=[]),
                       dict(targets=[1,2,4,8],rows=2,columns=2,backbone_points=[dict(left=0,right=1,column=0)])]:
            with self.assertRaises(ValueError):subject.build_problem(**kwargs)
        p=self.tiny()
        with self.assertRaises(AssertionError):subject.validate_decode(p,[False]*p['nv'])
        with self.assertRaises(ValueError):subject.solve(p,seconds=0)
        result=subject.solve(p,cancelled=lambda:True)
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['worker_started'])
        with patch.object(subject.time,'time',return_value=subject.HARD_DEADLINE+1):
            result=subject.solve(p,deadline_utc='2099-01-01T00:00:00Z')
        self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(result['reason'],'deadline')

    def test_callback_cannot_change_formula_before_spawn(self):
        problem=self.tiny()
        def mutate():
            problem['clauses'].append([])
            return False
        result=subject.solve(problem,cancelled=mutate)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['reason'],'formula_changed')
        self.assertFalse(result['worker_started'])

    @unittest.skipUnless(CMS,'real CryptoMiniSat required')
    def test_private_formula_copy_and_late_caller_mutation(self):
        problem=self.tiny();original=subject.validate_decode
        def mutate_after_worker(private,assignment,assumptions):
            self.assertIsNot(private,problem)
            problem['clauses'].append([])
            return original(private,assignment,assumptions)
        with patch.object(subject,'validate_decode',mutate_after_worker):
            result=subject.solve(problem,seconds=5,memory_mb=256)
        self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(result['reason'],'formula_changed')
        self.assertTrue(result['raw_compact']['all_raw_slices_verified'])
        self.assertTrue(result['worker_reaped'])

    @unittest.skipUnless(CMS,'real CryptoMiniSat required')
    def test_real_worker_sat_all_raw_slices_and_compact_tensor(self):
        p=self.tiny();result=subject.solve(p,seconds=5,memory_mb=256)
        self.assertEqual(result['status'],'SAT',result);self.assertTrue(result['worker_reaped'])
        self.assertEqual(result['worker_exitcode'],0);self.assertFalse(result['publication_eligible'])
        core=[]
        for value in [1,2,4,8]:core.extend((value>>i)&1 for i in range(4))
        result=subject.solve_core(core,[4,2,2],[],space_basis=[1,2,4,8],seconds=5,memory_mb=256)
        self.assertEqual(result['status'],'SAT',result);self.assertTrue(result['all_compact_coefficients_verified'])

    @unittest.skipUnless(CMS,'real CryptoMiniSat required')
    def test_late_model_decode_is_unknown_with_raw_witness(self):
        stopped=[False];original=subject.validate_decode
        def late(*args):
            result=original(*args);stopped[0]=True;return result
        with patch.object(subject,'validate_decode',late):
            result=subject.solve(self.tiny(),seconds=5,memory_mb=256,cancelled=lambda:stopped[0])
        self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete'])
        self.assertTrue(result['raw_compact']['all_raw_slices_verified']);self.assertTrue(result['worker_reaped'])

    @unittest.skipUnless(CMS,'real CryptoMiniSat required')
    def test_strong_d11_b7_fano_only_planted_real_worker(self):
        from tests.fano7_independent_fixture import planted_fano_b7
        f=planted_fano_b7()
        points=[dict(left=p['left'],right=p['right'],column=p['matrix']) for p in f['backbone_rankone_points']]
        problem=subject.build_problem(f['slices'],11,11,points,f['slices'])
        factors=[(p['left'],p['right']) for p in f['fano_rankone_points']]
        model,invertible=literal_assignment(problem,factors)
        self.assertTrue(invertible);self.assertTrue(accepted(problem,model))
        self.assertEqual(len(subject.validate_decode(problem,model)['support']),14)
        assumptions=[]
        for (u,v),us,vs in zip(factors,problem['u_variables'],problem['v_variables']):
            assumptions += [x if u>>i&1 else -x for i,x in enumerate(us)]
            assumptions += [x if v>>i&1 else -x for i,x in enumerate(vs)]
        result=subject.solve_core(f['core'],f['shape'],points,space_basis=f['slices'],seconds=5,memory_mb=256,assumptions=assumptions)
        self.assertEqual(result['status'],'SAT',result)
        self.assertEqual(len(result['products']),14);self.assertTrue(result['all_compact_coefficients_verified'])
        self.assertEqual(problem['metadata']['variables'],1141)
        self.assertEqual(problem['metadata']['native_xors'],516)
        self.assertEqual(problem['metadata']['cnf_clauses'],2733)

    @unittest.skipUnless(CMS,'real CryptoMiniSat required')
    def test_real_unsat_assumptions_never_close_whole_fano_branch(self):
        result=subject.solve(self.tiny(),seconds=5,memory_mb=256,assumptions=[1,-1])
        self.assertEqual(result['status'],'FANO_ASSUMPTIONS_UNSAT',result)
        self.assertFalse(result['fano_branch_complete']);self.assertTrue(result['worker_reaped'])

    def test_timeout_kills_and_reaps_uncooperative_fresh_child(self):
        with patch.object(subject,'worker',stalled_worker):result=subject.solve(self.tiny(),seconds=.03,memory_mb=256)
        self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped'])
        self.assertLess(result['elapsed_seconds'],1.5)


if __name__=='__main__':unittest.main()
