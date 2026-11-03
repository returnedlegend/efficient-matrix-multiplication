from pathlib import Path
import tempfile
import unittest
from scripts.marathon7_batch_hold import hold_batch
from scripts.prepare_local_ten43 import freeze,read


class ScopedHoldTests(unittest.TestCase):
    def test_only_unstarted_authorized_jobs_disabled_and_marker_blocks_running(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d);b=c/'batch';b.mkdir()
            def job(name):return dict(id=name,enabled=True,cpu=2,memory_mb=1024,seconds=330,command=['python3','worker.py'])
            original=[job('authorized-running'),job('authorized-next'),job('unrelated')]
            freeze(c/'queue.json',dict(jobs=original));freeze(c/'queue_state.json',dict(jobs={'authorized-running':{'status':'running'}}));freeze(b/'PROPOSAL.json',dict(jobs=original[:2]));freeze(b/'manifest.json',dict(files={}))
            result=hold_batch(c,b,'test case UNKNOWN');after=read(c/'queue.json')['jobs']
            self.assertEqual(result['disabled_unstarted_ids'],['authorized-next']);self.assertEqual(after[0],original[0]);self.assertEqual(after[2],original[2]);self.assertFalse(after[1]['enabled']);self.assertTrue((b/'BATCH-HOLD.json').exists())
            self.assertEqual(hold_batch(c,b,'duplicate request'),result)


if __name__=='__main__':unittest.main()
