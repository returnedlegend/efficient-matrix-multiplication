from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from mmsearch.fullpassing43 import CampaignBarrier,HARD_DEADLINE,SourceRuntime,guarded_call,solve_cp_core
from mmsearch.compact_eight43 import factor_core,packed_tensor
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.tensor import strassen_candidate
from mmsearch.compact_coset43 import expand_products


class FakeClock:
    def __init__(self):self.mono=0.;self.wall=HARD_DEADLINE-100


class FullPassingControls(unittest.TestCase):
    def fixture(self,root,clock):
        campaign=Path(root)/'campaign';campaign.mkdir();(campaign/'queue_state.json').write_text('{}');guard=campaign/'resource.json'
        ticks=int(Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19])
        state=dict(updated_utc=datetime.fromtimestamp(clock.wall,timezone.utc).isoformat(),pid=os.getpid(),process_identity=dict(start_ticks=ticks),stop_reason=None,campaign_allocated_bytes=0)
        guard.write_text(json.dumps(state));return campaign,guard,state

    def test_legacy_decoder_ignoring_callback_cannot_close_late_negative(self):
        with tempfile.TemporaryDirectory() as root:
            clock=FakeClock();campaign,path,_=self.fixture(root,clock);barrier=CampaignBarrier(campaign,path,1,clock=lambda:clock.mono,utc=lambda:clock.wall)
            def legacy(cancelled):
                clock.mono=2
                return dict(status='LOCAL_UNSAT',complete=True,witness='raw negative retained')
            result=guarded_call(legacy,barrier)
            self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['after_cutoff']);self.assertEqual(result['raw_result']['status'],'LOCAL_UNSAT')

    def test_absolute_cutoff_and_midcall_stop_preserve_raw_sat(self):
        for kind in ['utc','signal']:
            with tempfile.TemporaryDirectory() as root:
                clock=FakeClock();campaign,path,_=self.fixture(root,clock);barrier=CampaignBarrier(campaign,path,1000,clock=lambda:clock.mono,utc=lambda:clock.wall)
                def legacy(cancelled):
                    if kind=='utc':clock.wall=HARD_DEADLINE+1
                    else:barrier.stopped=True
                    return dict(status='SAT',products=[[1,1,1]])
                result=guarded_call(legacy,barrier);self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['after_cutoff']);self.assertEqual(result['raw_result']['products'],[[1,1,1]])

    def test_fresh_storage_live_identity_and_canonical_stops(self):
        with tempfile.TemporaryDirectory() as root:
            clock=FakeClock();campaign,path,state=self.fixture(root,clock);barrier=CampaignBarrier(campaign,path,10,clock=lambda:clock.mono,utc=lambda:clock.wall)
            self.assertIsNone(barrier.check(force=True))
            state['campaign_allocated_bytes']=5*1024**3;path.write_text(json.dumps(state));self.assertIn('5GiB',barrier.check(force=True))
            state['campaign_allocated_bytes']=0;state['process_identity']['start_ticks']+=1;path.write_text(json.dumps(state));self.assertIn('live',barrier.check(force=True))
            state['process_identity']['start_ticks']-=1;state['updated_utc']=datetime.fromtimestamp(clock.wall-61,timezone.utc).isoformat();path.write_text(json.dumps(state));self.assertIn('stale',barrier.check(force=True))
            state['updated_utc']=datetime.fromtimestamp(clock.wall,timezone.utc).isoformat();path.write_text(json.dumps(state));(campaign/'queue_state.json').write_text('{"stop_reason":"root stop"}');self.assertIn('queue',barrier.check(force=True))
            (campaign/'queue_state.json').write_text('{}');(campaign/'guard_stopped.json').write_text('{"pending_stops":[]}');self.assertIn('guard_stopped',barrier.check(force=True))
            (campaign/'guard_stopped.json').unlink();directory=campaign/'a';directory.mkdir();(directory/'WINNER.json').write_text('{}');self.assertIn('winner',barrier.check(force=True))

    def test_source_pair_independence_allows_factor_image_core(self):
        source=strassen_candidate(2);terms=factor_masks(source);ids=[0,2,5];_,_,shape=factor_core(terms,ids);ambient=0
        for i in ids:ambient^=packed_tensor(terms[i],4)
        mask=sum(1<<i for i in ids);case=dict(mask_lo=mask,mask_hi=0,shape=shape,source_local_products=3,residual_sha256=hashlib.sha256(ambient.to_bytes(8,'little')).hexdigest())
        prepared=SourceRuntime(source,small_control=True).prepare(case);result=solve_cp_core(prepared['core'],shape,3,axis=0)
        self.assertEqual(result['status'],'SAT');self.assertEqual(expand_products(result['products'],shape),prepared['core'])

    def test_reviewed_generic_surplus_two_adapter(self):
        core=[0]*32
        for a,b,c in [(0,0,0),(0,1,1),(1,2,2),(1,3,3)]:core[(a*4+b)*4+c]=1
        self.assertEqual(solve_cp_core(core,[2,4,4],3,axis=0)['status'],'LOCAL_UNSAT')
        result=solve_cp_core(core,[2,4,4],4,axis=0);self.assertEqual(result['status'],'SAT');self.assertEqual(expand_products(result['products'],[2,4,4]),core)
        self.assertEqual(result['algorithm'],'reviewed_generic_forced_inside_surplus_two')


if __name__=='__main__':unittest.main()
