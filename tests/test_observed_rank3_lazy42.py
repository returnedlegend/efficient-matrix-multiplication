import copy
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from mmsearch.observed_rank3_lazy42 import SourceRuntime,FreshGuard,decode_rank3,search_bounded,chain_read,chain_append,logical
from mmsearch.observed_rank3_checkpoint42 import append_checkpoint,save_checkpoint,load_checkpoint
from mmsearch.observed_rank342 import prepare_space
from mmsearch.free_factor_sat import build_system
from mmsearch.search import encode_candidate
from mmsearch.recombine import digest


def small_system():
    original=[(9,9,9),(12,1,10),(1,10,12),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
    split=original[1:]+[(1,9,9),(8,9,9)]
    return build_system(split+[(9,9,0)],2,'uv',encode_candidate(split,2))


class LazyTests(unittest.TestCase):
    def test_cached_quotient_identical_and_full_small_lift(self):
        system=small_system();runtime=SourceRuntime(system);q=runtime.prepare(system,[9,10,12])
        self.assertEqual(q,prepare_space(system,[9,10,12]))
        result=decode_rank3(list(map(lambda x:int(x,16),q['column_syndromes_hex'])),list(map(lambda x:int(x,16),q['targets_hex'])),5,1)
        answer=runtime.decode_hit(system,q,result['entries'])
        self.assertEqual((answer['verification']['rank'],answer['verification']['exact_entries_checked']),(7,64))
        with self.assertRaises(AssertionError):runtime.prepare(copy.deepcopy(system),[9,10,12])

    def test_logical_hash_replay_and_streamed_resume(self):
        h=[1,2,4,8,16,32];t=[3,12,48]
        a=decode_rank3(h,t,5,1);b=decode_rank3(h,t,5,1)
        self.assertEqual(a['cursor'],b['cursor'])
        q=dict(column_syndromes_hex=list(map(hex,h)),targets_hex=list(map(hex,t)),weight_bound=5,quotient_sha256='tiny')
        with tempfile.TemporaryDirectory() as d:
            cursor=None
            for i in range(3):
                r=search_bounded(q,1,256,cursor,on_progress=lambda rec,state:append_checkpoint(d,'tiny',rec,state),branch_budget=1)
                save_checkpoint(d,'tiny',r.get('cursor'));cursor=load_checkpoint(d,'tiny')
                self.assertEqual(cursor['next_branch'],i+1);self.assertTrue(r['worker_reaped'])
            self.assertEqual(r['status'],'NO_ONE_SUBSPACE_GAIN');self.assertEqual(cursor,a['cursor'])
        self.assertEqual(digest(logical({'elapsed_seconds':1,'x':{'elapsed_seconds':2,'n':3}})),digest({'x':{'n':3}}))

    def test_guard_clean_holds(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'guard.json';ticks=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
            state=dict(updated_utc=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),process_identity={'start_ticks':ticks},stop_reason=None,campaign_allocated_bytes=0)
            def check(data):
                path.write_text(json.dumps(data));return FreshGuard(path).check()
            self.assertIsNone(check(state))
            self.assertIn('5GiB',check(dict(state,campaign_allocated_bytes=5*1024**3)))
            self.assertIn('stale',check(dict(state,updated_utc=(datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat())))
            self.assertIn('identity',check(dict(state,process_identity={'start_ticks':ticks+1})))
            self.assertIn('stop',check(dict(state,stop_reason='manual hold')))
            path.unlink();self.assertIn('unavailable',FreshGuard(path).check())

    def test_result_journal_crash_rollforward_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'results.jsonl';initial=digest('source+chunk')
            chain=chain_append(path,{'index':0,'status':'negative'},initial)
            events,last=chain_read(path,initial);self.assertEqual(last,chain);self.assertEqual(len(events),1)
            chain=chain_append(path,{'index':1,'status':'negative'},chain)
            self.assertEqual(len(chain_read(path,initial)[0]),2)
            with self.assertRaises(ValueError):chain_read(path,'changed-source')
            with path.open('a') as stream:stream.write('{')
            with self.assertRaises(ValueError):chain_read(path,initial)


if __name__=='__main__':unittest.main()
