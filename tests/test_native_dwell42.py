"""Stepwise exactness and trajectory controls for the unlaunched dwell worker."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from mmsearch.search import encode_candidate,naive_terms
from mmsearch.verify import verify_candidate
from tests.test_native import coefficients,read_terms

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('g++'),'C++ compiler unavailable')
class DwellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory()
        cls.baseline=Path(os.environ.get('DWELL42_BASELINE_BINARY',Path(cls.build.name)/'baseline'))
        cls.binary=Path(os.environ.get('DWELL42_BINARY',Path(cls.build.name)/'dwell'))
        for source,binary in [('native/flip_worker_v2.cpp',cls.baseline),('native/flip_worker_dwell42.cpp',cls.binary)]:
            if not binary.exists():subprocess.run(['g++','-std=c++17','-O2',str(ROOT/source),'-o',str(binary)],check=True,capture_output=True,timeout=12)

    @classmethod
    def tearDownClass(cls):cls.build.cleanup()

    def run_worker(self,directory,n=3,*,name='walk',baseline=False,terms=None,extra=(),trace=True):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        source=directory/'input.txt'
        source.write_text(''.join(' '.join(map(str,t))+'\n' for t in (naive_terms(n) if terms is None else terms)))
        prefix=directory/name
        command=[str(self.baseline if baseline else self.binary),'--input',str(source),'--output',str(prefix),
            '--n',str(n),'--target','0','--max-rank',str(n**3+8),'--seed','19','--steps','1000','--seconds','10',
            '--plus-every','7','--restart-every','173','--archive-every','1','--archive-size','8']
        if trace:command+=['--trace',str(prefix)+'.trace']
        command+=list(extra)
        process=subprocess.run(command,capture_output=True,text=True,timeout=12)
        self.assertEqual(process.returncode,0,process.stderr)
        stats=json.loads(Path(str(prefix)+'.stats.json').read_text())
        return prefix,stats,command

    def frames(self,prefix):
        for line in Path(str(prefix)+'.trace').read_text().splitlines():
            step,kind,accepted,*raw=line.split()
            yield int(step),kind,bool(int(accepted)),[tuple(map(int,t.split(','))) for t in raw]

    def verify_exports(self,prefix,n):
        for path in [Path(str(prefix)+'.best.txt'),Path(str(prefix)+'.current.txt'),*Path(str(prefix)+'.archive').glob('*.txt')]:
            report=verify_candidate(encode_candidate(read_terms(path),n),random_trials=0)
            self.assertTrue(report['valid'],path);self.assertEqual(report['exact_entries_checked'],n**6)

    def test_default_zero_matches_v2_trace_and_original_statistics(self):
        for n,seed in [(2,3),(3,19),(5,23)]:
            with self.subTest(n=n),tempfile.TemporaryDirectory() as tmp:
                common=('--steps','400','--seed',str(seed),'--max-rank',str(n**3+8))
                base,old,_=self.run_worker(tmp,n,name='base',baseline=True,extra=common)
                new,current,_=self.run_worker(tmp,n,name='new',extra=common)
                zero,explicit,_=self.run_worker(tmp,n,name='zero',extra=(*common,'--reduction-dwell','0'))
                self.assertEqual(Path(str(base)+'.trace').read_bytes(),Path(str(new)+'.trace').read_bytes())
                self.assertEqual(Path(str(base)+'.trace').read_bytes(),Path(str(zero)+'.trace').read_bytes())
                for suffix in ('.best.txt','.current.txt'):
                    self.assertEqual(Path(str(base)+suffix).read_bytes(),Path(str(new)+suffix).read_bytes())
                for key,value in old.items():
                    if key!='elapsed_seconds':self.assertEqual(value,current[key],key)
                self.assertEqual(current['reduction_dwell'],0);self.assertEqual(explicit['dwell_steps'],0)

    def test_dwell_really_defers_reductions_and_all_counters_match_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix,stats,_=self.run_worker(tmp,3,extra=('--steps','2000','--restart-every','1000000000','--reduction-dwell','16'))
            previous=list(naive_terms(3));remaining=0;deferred=0;hist={};accepted={'f':0,'p':0,'r':0};maximum=len(previous)
            changes={k:{'up':0,'equal':0,'down':0,'delta_sum':0} for k in accepted}
            best=len(previous);excess_hist={};max_excess=0
            expected={(i*3+j,j*3+k,k*3+i) for i in range(3) for j in range(3) for k in range(3)}
            for step,kind,ok,current in self.frames(prefix):
                rank=len(previous);hist[str(rank)]=hist.get(str(rank),0)+1
                excess=str(rank-best);excess_hist[excess]=excess_hist.get(excess,0)+1
                pairs=any(sum(a==b for a,b in zip(x,y))>=2 for i,x in enumerate(previous) for y in previous[i+1:])
                flips=any(any(a==b for a,b in zip(x,y)) for i,x in enumerate(previous) for y in previous[i+1:])
                if remaining and flips and pairs:
                    deferred+=1;self.assertNotEqual(kind,'r',(step,remaining))
                self.assertEqual(coefficients(current,3),expected,step)
                if ok:
                    accepted[kind]+=1;delta=len(current)-len(previous)
                    changes[kind]['up' if delta>0 else 'down' if delta<0 else 'equal']+=1
                    changes[kind]['delta_sum']+=delta
                if remaining:remaining-=1
                if ok and kind=='p':remaining=16
                best=min(best,len(current));max_excess=max(max_excess,len(current)-best)
                maximum=max(maximum,len(current));previous=current
            self.assertGreater(deferred,0);self.assertEqual(stats['dwell_reductions_deferred'],deferred)
            self.assertEqual(stats['rank_residency_steps'],hist);self.assertEqual(sum(hist.values()),stats['steps'])
            self.assertEqual(stats['max_visited_rank'],maximum)
            self.assertEqual(stats['max_rank_excess'],max_excess);self.assertEqual(stats['rank_excess_residency_steps'],excess_hist)
            self.assertEqual(stats['accepted_by_kind'],dict(flip=accepted['f'],plus=accepted['p'],reduction=accepted['r']))
            self.assertEqual(stats['rank_changes_by_kind'],dict(flip=changes['f'],plus=changes['p'],reduction=changes['r']))
            self.assertGreater(changes['f']['down'],0)  # Inherent flip cancellation remains allowed.
            self.assertEqual(sum(accepted.values()),stats['accepted_moves']);self.assertGreater(stats['dwell_flip_attempts'],0)
            self.verify_exports(prefix,3)

    def test_n2_positive_naive8_reaches7_under_dwell(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix,stats,_=self.run_worker(tmp,2,trace=False,extra=('--target','7','--max-rank','14','--steps','200000','--seed','3','--reduction-dwell','16'))
            self.assertEqual(stats['history'][0]['rank'],8);self.assertEqual(stats['best_rank'],7)
            self.assertTrue(stats['target_reached']);self.verify_exports(prefix,2)

    def test_n3_n5_full_tensor_is_preserved_at_every_bounded_step(self):
        for n,steps in [(3,200),(5,100)]:
            with self.subTest(n=n),tempfile.TemporaryDirectory() as tmp:
                prefix,stats,_=self.run_worker(tmp,n,extra=('--steps',str(steps),'--plus-every','3','--reduction-dwell','12'))
                expected={(i*n+j,j*n+k,k*n+i) for i in range(n) for j in range(n) for k in range(n)}
                for step,kind,ok,terms in self.frames(prefix):
                    self.assertEqual(coefficients(terms,n),expected,(n,step));self.assertLessEqual(len(terms),n**3+8)
                self.assertTrue(stats['tensor_invariant_checked']);self.verify_exports(prefix,n)

    def test_max_rank_cap_and_rejected_moves_remain_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix,stats,_=self.run_worker(tmp,3,extra=('--max-rank','27','--reduction-dwell','100'))
            self.assertLessEqual(stats['max_visited_rank'],27)
            self.assertGreater(stats['rejected_moves'],0)
            self.assertEqual(stats['steps'],stats['accepted_moves']+stats['rejected_moves'])
            self.assertTrue(all(len(terms)<=27 for _,_,_,terms in self.frames(prefix)));self.verify_exports(prefix,3)

    def test_cyclic_arbitrary_tensor_and_orbits_are_preserved(self):
        terms=set()
        for a,b,c in [(1,2,4),(1,2,8),(1,1,1)]:terms.update([(a,b,c),(b,c,a),(c,a,b)])
        expected=coefficients(terms,2)
        with tempfile.TemporaryDirectory() as tmp:
            prefix,stats,_=self.run_worker(tmp,2,terms=sorted(terms),extra=('--allow-arbitrary','--cyclic','--max-rank','30','--steps','400','--reduction-dwell','16'))
            for step,kind,ok,current in self.frames(prefix):
                self.assertEqual(coefficients(current,2),expected,step);s=set(current)
                for a,b,c in current:self.assertIn((b,c,a),s)
            self.assertTrue(stats['cyclic'])

    def test_zero_and_short_wall_clock_budget_still_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix,zero,_=self.run_worker(tmp,3,name='zero',trace=False,extra=('--seconds','0','--steps','1000000000000','--reduction-dwell','100'))
            self.assertEqual(zero['steps'],0);self.assertEqual(zero['rank_residency_steps'],{});self.assertEqual(zero['max_visited_rank'],27)
            prefix,short,_=self.run_worker(tmp,3,name='short',trace=False,extra=('--seconds','.01','--steps','1000000000000','--reduction-dwell','100'))
            self.assertGreater(short['steps'],0);self.assertLess(short['elapsed_seconds'],1)
            self.assertEqual(short['steps']%256,0);self.verify_exports(prefix,3)

    def test_owned_worker_sigterm_checkpoints_without_breaking_tensor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.txt';source.write_text(''.join(' '.join(map(str,t))+'\n' for t in naive_terms(3)));prefix=root/'walk'
            process=subprocess.Popen([str(self.binary),'--input',str(source),'--output',str(prefix),'--n','3','--target','0',
                '--max-rank','35','--seconds','100','--steps','1000000000000','--reduction-dwell','64'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                until=time.monotonic()+2
                while not Path(str(prefix)+'.stats.json').exists() and time.monotonic()<until:time.sleep(.005)
                process.terminate();stdout,stderr=process.communicate(timeout=3)
                self.assertEqual(process.returncode,0,stderr)
                stats=json.loads(Path(str(prefix)+'.stats.json').read_text());self.assertTrue(stats['stopped_by_signal'])
                self.verify_exports(prefix,3)
            finally:
                if process.poll() is None:process.kill();process.communicate()

    def test_negative_dwell_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.txt';source.write_text('1 1 1\n')
            result=subprocess.run([str(self.binary),'--input',str(source),'--output',str(Path(tmp)/'walk'),'--reduction-dwell','-1'],capture_output=True,text=True,timeout=2)
            self.assertNotEqual(result.returncode,0);self.assertIn('nonnegative integer',result.stderr)


if __name__=='__main__':unittest.main()
