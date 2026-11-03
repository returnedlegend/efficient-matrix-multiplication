import copy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from mmsearch.fullpassing43 import HARD_DEADLINE
from mmsearch.fullpassing_guardv2_43 import CampaignBarrier,guarded_call


class TypedGuardControls(unittest.TestCase):
    def fixture(self,root):
        campaign=Path(root)/'campaign';campaign.mkdir();queue=campaign/'queue_state.json';queue.write_text('{}');guard=campaign/'resource.json';now=HARD_DEADLINE-100
        ticks=int(Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19])
        state=dict(updated_utc=datetime.fromtimestamp(now,timezone.utc).isoformat(),pid=os.getpid(),process_identity=dict(start_ticks=ticks),campaign_allocated_bytes=0,stop_reason=None)
        guard.write_text(json.dumps(state));barrier=CampaignBarrier(campaign,guard,10,clock=lambda:0,utc=lambda:now)
        return queue,guard,state,barrier

    def test_null_list_queue_before_and_after_call_preserve_raw(self):
        for malformed in [None,[]]:
            for rawstatus in ['SAT','LOCAL_UNSAT']:
                with tempfile.TemporaryDirectory() as root:
                    queue,guard,state,barrier=self.fixture(root)
                    def legacy(cancelled):
                        queue.write_text(json.dumps(malformed))
                        return dict(status=rawstatus,complete=True,witness='preserve me')
                    result=guarded_call(legacy,barrier)
                    self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['after_cutoff']);self.assertEqual(result['raw_result']['witness'],'preserve me')
                    self.assertEqual(result['raw_result']['status'],rawstatus)
                    called=[]
                    result=guarded_call(lambda **kw:called.append(True),barrier)
                    self.assertEqual(result['status'],'UNKNOWN');self.assertIsNone(result['raw_result']);self.assertEqual(called,[])

    def test_resource_objects_and_fields_are_checked_before_access(self):
        bad=[None,[],{'updated_utc':123},{'updated_utc':None},{'process_identity':[]},{'process_identity':None},
             {'pid':'123'},{'pid':True},{'campaign_allocated_bytes':'0'},{'campaign_allocated_bytes':None},
             {'process_identity':{'start_ticks':'123'}},{'updated_utc':'2026-11-03T00:00:00'}]
        for patch in bad:
            with tempfile.TemporaryDirectory() as root:
                queue,guard,state,barrier=self.fixture(root)
                malformed=patch if patch is None or isinstance(patch,list) else dict(copy.deepcopy(state),**patch)
                def legacy(cancelled):
                    guard.write_text(json.dumps(malformed))
                    return dict(status='LOCAL_UNSAT',complete=True,witness='raw decision')
                result=guarded_call(legacy,barrier)
                self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['after_cutoff']);self.assertEqual(result['raw_result']['witness'],'raw decision')
                guard.write_text(json.dumps(state));self.assertIsNone(barrier.check(force=True))


if __name__=='__main__':unittest.main()
