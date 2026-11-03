"""Tiny exact-tensor controls for the separate default-disabled hold worker."""
import collections
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from mmsearch.search import naive_terms
from tests.test_native import coefficients
from tests import test_native_dwell42 as helpers

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('g++'),'C++ compiler unavailable')
class HoldRankTests(unittest.TestCase):
    run_worker=helpers.DwellTests.run_worker
    frames=helpers.DwellTests.frames
    verify_exports=helpers.DwellTests.verify_exports

    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory()
        cls.baseline=Path(os.environ.get('HOLD_BASELINE_BINARY',Path(cls.build.name)/'burst'))
        cls.binary=Path(os.environ.get('HOLD_BINARY',Path(cls.build.name)/'hold'))
        for source,binary in [('native/flip_worker_plus_burst42.cpp',cls.baseline),('native/flip_worker_dwell_hold_rank.cpp',cls.binary)]:
            if not binary.exists():subprocess.run(['g++','-std=c++17','-O2',str(ROOT/source),'-o',str(binary)],check=True,capture_output=True,timeout=20)

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def test_default_flag_zero_and_dwell_zero_preserve_byte_trace_and_old_stats(self):
        for n,dwell,k in [(2,0,1),(2,128,4),(3,128,1),(3,1024,8)]:
            with self.subTest(n=n,dwell=dwell,k=k),tempfile.TemporaryDirectory() as tmp:
                extra=('--steps','500','--reduction-dwell',str(dwell),'--plus-burst',str(k))
                old,stats,_=self.run_worker(tmp,n,name='old',baseline=True,extra=extra)
                new,current,_=self.run_worker(tmp,n,name='new',extra=extra)
                explicit,zero,_=self.run_worker(tmp,n,name='zero',extra=(*extra,'--dwell-hold-rank','0'))
                for prefix in [new,explicit]:
                    self.assertEqual(Path(str(old)+'.trace').read_bytes(),Path(str(prefix)+'.trace').read_bytes())
                    for suffix in ['.best.txt','.current.txt']:self.assertEqual(Path(str(old)+suffix).read_bytes(),Path(str(prefix)+suffix).read_bytes())
                for key,value in stats.items():
                    if key!='elapsed_seconds':self.assertEqual(value,current[key],key);self.assertEqual(value,zero[key],key)
                if dwell==0:
                    on,onstats,_=self.run_worker(tmp,n,name='onD0',extra=(*extra,'--dwell-hold-rank','1'))
                    self.assertEqual(Path(str(old)+'.trace').read_bytes(),Path(str(on)+'.trace').read_bytes())
                    for key,value in stats.items():
                        if key!='elapsed_seconds':self.assertEqual(value,onstats[key],key)
                    self.assertEqual(onstats['hold_active_steps'],0)

    def test_all_step_full_tensor_floor_and_rejection_identity(self):
        for n,k in [(2,1),(2,4),(3,1),(3,4)]:
            with self.subTest(n=n,k=k),tempfile.TemporaryDirectory() as tmp:
                dwell=64
                prefix,stats,_=self.run_worker(tmp,n,extra=('--steps','1600','--plus-every','3','--restart-every','1000000000','--plus-burst',str(k),'--reduction-dwell',str(dwell),'--dwell-hold-rank','1'))
                previous=list(naive_terms(n));expected=coefficients(previous,n);clock=remaining=attempts=0;counts=collections.Counter()
                for step,kind,ok,current in self.frames(prefix):
                    before=len(previous);after=len(current)
                    if remaining and (before>=n**3+8 or attempts>=8*k):remaining=0
                    forcing=remaining>0;dwelling=not forcing and clock>0
                    if dwelling:
                        counts['active_steps']+=1
                        if before==n**3+8:counts['steps_at_rank_cap']+=1
                        if kind=='f':
                            counts['flip_attempts']+=1
                            self.assertGreaterEqual(after,before,(n,k,step))
                        if ok and after<before:counts['active_rank_loss_moves']+=1;counts['active_rank_loss']+=before-after
                    if not ok:self.assertEqual(current,previous,(n,k,step))
                    if forcing:
                        attempts+=1
                        if ok:remaining-=1
                        if remaining and attempts>=8*k:remaining=0
                    elif ok and kind=='p' and k>1:remaining=k-1;attempts=0
                    if dwelling:
                        clock-=1
                        if not clock:counts['window_expirations']+=1
                    if ok and kind=='p':
                        counts['windows_started']+=1
                        if clock:counts['window_renewals']+=1
                        clock=dwell
                    self.assertEqual(coefficients(current,n),expected,(n,k,step))
                    previous=current
                for key,count in counts.items():self.assertEqual(stats['hold_'+key],count,key)
                self.assertEqual(stats['dwell_remaining'],clock)
                self.assertGreater(stats['hold_rejected_downward_flips'],0)
                self.assertGreaterEqual(stats['hold_prevented_rank_loss'],stats['hold_rejected_downward_flips'])
                self.assertEqual(stats['steps'],1600);self.verify_exports(prefix,n)

    def test_state_rejection_is_atomic_including_all_indices_and_fingerprint(self):
        # Serialize every slot, free/active order, map membership and bucket order.
        harness=r'''
#define main hold_worker_main
#include "SOURCE"
#undef main
#include <cassert>
static std::string signature(const State&s){
 std::ostringstream o;
 for(const auto&v:s.slots){for(auto x:v.term)o<<x<<',';for(auto x:v.sp)o<<x<<',';for(auto x:v.pp)o<<x<<',';o<<v.active_pos<<';';}
 for(auto v:s.active)o<<v<<',';o<<'|';for(auto v:s.free)o<<v<<',';o<<'|';
 std::vector<std::pair<Term,int>> look(s.lookup.begin(),s.lookup.end());std::sort(look.begin(),look.end());
 for(auto v:look){for(auto x:v.first)o<<x<<',';o<<v.second<<';';}
 for(auto idx:{&s.singles,&s.pairs}){for(auto v:idx->eligible)o<<v<<',';std::vector<U> keys;for(auto&v:idx->map)keys.push_back(v.first);std::sort(keys.begin(),keys.end());for(auto k:keys){auto&b=idx->map.at(k);o<<k<<':'<<b.eligible<<':';for(auto v:b.ids)o<<v<<',';o<<';';}}
 o<<s.fingerprint.x<<','<<s.fingerprint.y;return o.str();
}
int main(){State s;Term x{1,2,4},y{1,2,8},f{1,0,4},g{1,2,12};s.add(x);s.add(y);auto before=signature(s);int prospective=-1;
 assert(!s.apply({x,y,f,g},100,2,&prospective));assert(prospective==1);assert(signature(s)==before);
 assert(!s.apply({x,y,f,g},1,2,&prospective));assert(signature(s)==before);
 assert(!s.apply({x,x,y,y},100,2,&prospective));assert(prospective==2);assert(signature(s)==before);
 assert(s.apply({x,y,f,g},100,-1,&prospective));assert(s.snapshot()==Terms({g}));
}
'''.replace('SOURCE',str(ROOT/'native/flip_worker_dwell_hold_rank.cpp'))
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'atomic.cpp';source.write_text(harness);binary=Path(tmp)/'atomic'
            subprocess.run(['g++','-std=c++17','-O1',str(source),'-o',str(binary)],check=True,capture_output=True,timeout=20)
            subprocess.run([str(binary)],check=True,capture_output=True,timeout=2)

    def test_restart_caps_timeout_and_invalid_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix,stats,_=self.run_worker(tmp,3,extra=('--steps','1600','--max-rank','28','--plus-every','3','--restart-every','17','--plus-burst','8','--reduction-dwell','1024','--dwell-hold-rank','1'))
            self.assertGreater(stats['hold_restart_events'],0);self.assertGreater(stats['hold_window_renewals'],0)
            self.assertGreater(stats['burst_rank_capped'],0);self.assertLessEqual(stats['max_visited_rank'],28)
            self.assertEqual(stats['steps'],1600);self.verify_exports(prefix,3)
            prefix,stats,_=self.run_worker(tmp,3,name='timeout',trace=False,extra=('--seconds','.01','--steps','1000000000000','--reduction-dwell','1000000000000','--dwell-hold-rank','1'))
            self.assertLess(stats['elapsed_seconds'],1);self.assertGreater(stats['steps'],0);self.assertEqual(stats['steps']%256,0);self.verify_exports(prefix,3)
            for invalid in ['-1','2','true','1.0']:
                result=subprocess.run([str(self.binary),'--input',str(Path(tmp)/'input.txt'),'--output',str(Path(tmp)/'invalid'),'--dwell-hold-rank',invalid],capture_output=True,text=True,timeout=2)
                self.assertNotEqual(result.returncode,0)

if __name__=='__main__':unittest.main()
