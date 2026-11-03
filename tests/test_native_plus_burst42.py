"""Synthetic exactness/dynamics controls; no production rank93 target queries."""
import collections,json,os
from pathlib import Path
import shutil,subprocess,tempfile,unittest
from mmsearch.search import naive_terms
from tests.test_native import coefficients
from tests.test_native_dwell42 import DwellTests

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('g++'),'C++ compiler unavailable')
class PlusBurstTests(DwellTests):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory()
        cls.baseline=Path(os.environ.get('BURST42_BASELINE_BINARY',Path(cls.build.name)/'dwell'))
        cls.binary=Path(os.environ.get('BURST42_BINARY',Path(cls.build.name)/'burst'))
        for source,binary in [('native/flip_worker_dwell42.cpp',cls.baseline),('native/flip_worker_plus_burst42.cpp',cls.binary)]:
            if not binary.exists():subprocess.run(['g++','-std=c++17','-O2',str(ROOT/source),'-o',str(binary)],check=True,capture_output=True,timeout=12)

    def test_K1_nonzero_dwell_matches_all_old_fields_and_byte_trace(self):
        for n,dwell in [(2,128),(3,1024),(5,128)]:
            with self.subTest(n=n),tempfile.TemporaryDirectory() as tmp:
                extra=('--steps','256','--reduction-dwell',str(dwell))
                p,old,_=self.run_worker(tmp,n,name='old',baseline=True,extra=extra)
                q,new,_=self.run_worker(tmp,n,name='new',extra=extra)
                z,explicit,_=self.run_worker(tmp,n,name='explicit',extra=(*extra,'--plus-burst','1'))
                self.assertEqual(Path(str(p)+'.trace').read_bytes(),Path(str(q)+'.trace').read_bytes())
                self.assertEqual(Path(str(p)+'.trace').read_bytes(),Path(str(z)+'.trace').read_bytes())
                for key,value in old.items():
                    if key!='elapsed_seconds':self.assertEqual(value,new[key],key);self.assertEqual(value,explicit[key],key)
                self.assertEqual(new['plus_burst'],1);self.assertEqual(new['burst_forced_attempts'],0)

    def test_forced_burst_and_dwell_counters_reconstruct_and_full_tensor(self):
        for n,k,dwell in [(2,4,128),(2,8,1024),(3,4,128),(3,8,1024),(5,4,128),(5,8,1024)]:
            with self.subTest(n=n),tempfile.TemporaryDirectory() as tmp:
                cap=n**3+8;p,s,_=self.run_worker(tmp,n,extra=('--steps','400','--plus-every','3','--restart-every','1000000000','--plus-burst',str(k),'--reduction-dwell',str(dwell)))
                previous=list(naive_terms(n));expected=coefficients(previous,n);rem=attempts=window_accepted=clock=0;origin=0
                counts=collections.Counter();changes=collections.Counter();initial_delta=0;netmax=0;maxaccepted=0;dwellcounts=collections.Counter()
                for step,kind,ok,current in self.frames(p):
                    before=len(previous);after=len(current);delta=after-before
                    if rem and before>=cap:counts['rank_capped']+=1;rem=0
                    if rem and attempts>=8*k:counts['attempt_capped']+=1;rem=0
                    forcing=rem>0;dwelling=not forcing and clock>0
                    if forcing:self.assertEqual(kind,'p')
                    if dwelling:
                        dwellcounts['steps']+=1
                        flips=any(any(a==b for a,b in zip(x,y)) for i,x in enumerate(previous) for y in previous[i+1:])
                        pairs=any(sum(a==b for a,b in zip(x,y))>=2 for i,x in enumerate(previous) for y in previous[i+1:])
                        if not flips:dwellcounts['fallback']+=1
                        if flips and pairs:dwellcounts['deferred']+=1;self.assertNotEqual(kind,'r')
                    if forcing:
                        counts['forced_attempts']+=1;attempts+=1
                        if ok:
                            counts['forced_accepted']+=1;window_accepted+=1;rem-=1
                            changes['up' if delta>0 else 'down' if delta<0 else 'equal']+=1;changes['delta_sum']+=delta
                            maxaccepted=max(maxaccepted,window_accepted);netmax=max(netmax,after-origin)
                            if not rem:counts['completed']+=1
                        else:counts['failed_attempts']+=1
                        if rem and attempts>=8*k:counts['attempt_capped']+=1;rem=0
                    elif ok and kind=='p':
                        rem=k-1;attempts=0;window_accepted=1;counts['started']+=1;origin=before;initial_delta+=delta
                        maxaccepted=max(maxaccepted,window_accepted);netmax=max(netmax,after-origin)
                    if dwelling:
                        if kind=='f':dwellcounts['flip_attempts']+=1
                        clock-=1
                    if ok and kind=='p':
                        if clock:dwellcounts['rearmed']+=1
                        clock=dwell;dwellcounts['windows']+=1
                    self.assertEqual(coefficients(current,n),expected,(n,step));self.assertLessEqual(after,cap);previous=current
                for suffix,counter in [('windows_started','started'),('windows_completed','completed'),('forced_attempts','forced_attempts'),('forced_accepted','forced_accepted'),('failed_attempts','failed_attempts'),('rank_capped','rank_capped'),('attempt_capped','attempt_capped')]:self.assertEqual(s['burst_'+suffix],counts[counter],suffix)
                self.assertEqual(s['burst_remaining'],rem);self.assertEqual(s['burst_window_attempts'],attempts);self.assertEqual(s['burst_window_accepted'],window_accepted)
                self.assertEqual(s['burst_initial_rank_delta_sum'],initial_delta);self.assertEqual(s['burst_max_net_rank_gain'],netmax);self.assertEqual(s['burst_max_accepted_pluses'],maxaccepted)
                self.assertEqual(s['burst_forced_rank_changes'],{k:changes[k] for k in ['up','equal','down','delta_sum']})
                for name,key in [('dwell_steps','steps'),('dwell_windows_started','windows'),('dwell_windows_rearmed','rearmed'),('dwell_reductions_deferred','deferred'),('dwell_flip_attempts','flip_attempts'),('dwell_no_flip_fallback_steps','fallback')]:self.assertEqual(s[name],dwellcounts[key],name)
                self.assertEqual(s['dwell_remaining'],clock);self.assertGreater(s['burst_forced_accepted'],0);self.verify_exports(p,n)

    def test_capped_bursts_never_stall_and_short_timeout_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,s,_=self.run_worker(tmp,3,extra=('--steps','2000','--plus-every','3','--max-rank','28','--plus-burst','8','--reduction-dwell','1024'))
            self.assertEqual(s['steps'],2000);self.assertLessEqual(s['max_visited_rank'],28);self.assertGreater(s['burst_rank_capped'],0)
            self.assertLessEqual(s['burst_window_attempts'],64);self.verify_exports(p,3)
            p,s,_=self.run_worker(tmp,3,name='timeout',trace=False,extra=('--seconds','.01','--steps','1000000000000','--plus-burst','8','--reduction-dwell','1024'))
            self.assertLess(s['elapsed_seconds'],1);self.assertGreater(s['steps'],0);self.assertEqual(s['steps']%256,0);self.verify_exports(p,3)

    def test_positive_n2_and_invalid_burst_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,s,_=self.run_worker(tmp,2,trace=False,extra=('--target','7','--max-rank','16','--steps','200000','--seed','3','--plus-burst','4','--reduction-dwell','128'))
            self.assertEqual(s['best_rank'],7);self.verify_exports(p,2)
            for invalid in ['0','-1','65','4.5']:
                args=[str(self.binary),'--input',str(Path(tmp)/'input.txt'),'--output',str(Path(tmp)/'invalid'),'--plus-burst',invalid]
                result=subprocess.run(args,capture_output=True,text=True,timeout=2);self.assertNotEqual(result.returncode,0)

    def test_real_attempt_cap_and_restart_cancellation_full_tensor(self):
        with tempfile.TemporaryDirectory() as tmp:
            p,s,_=self.run_worker(tmp,2,extra=('--steps','2000','--plus-every','3','--restart-every','1000000000','--max-rank','9','--plus-burst','8','--reduction-dwell','128','--cyclic'))
            self.assertGreater(s['burst_attempt_capped'],0);self.assertLessEqual(s['burst_window_attempts'],64)
            self.assertEqual(s['burst_windows_started'],s['burst_windows_completed']+s['burst_attempt_capped']+s['burst_rank_capped']+int(s['burst_remaining']>0))
            expected=coefficients(naive_terms(2),2)
            for step,kind,ok,terms in self.frames(p):
                self.assertEqual(coefficients(terms,2),expected,step)
                for a,b,c in terms:self.assertIn((b,c,a),terms)
            self.verify_exports(p,2)
            p,s,_=self.run_worker(tmp,3,name='restart',extra=('--steps','400','--restart-every','5','--plus-every','3','--plus-burst','8','--reduction-dwell','1024'))
            self.assertGreater(s['burst_restart_cancellations'],0)
            self.assertEqual(s['burst_windows_started'],s['burst_windows_completed']+s['burst_attempt_capped']+s['burst_rank_capped']+s['burst_restart_cancellations']+int(s['burst_remaining']>0))
            self.verify_exports(p,3)

if __name__=='__main__':unittest.main()
