import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mmsearch import compact_rank2_edges43 as decoder
from scripts import marathon7_local_campaign_v5 as worker
from tests import test_marathon7_local as helpers


class PolledRunnerTests(unittest.TestCase):
    def test_closed_n2_positive_and_callback_metrics(self):
        with tempfile.TemporaryDirectory() as d,patch.object(helpers,'worker',worker):
            bundle=helpers.tiny_bundle(d);out=Path(d)/'out';_,r=helpers.invoke(bundle,out,'--small-control')
            self.assertEqual(r['status'],'SMALL_CONTROL_PASSED');self.assertEqual(json.loads((out/'SMALL_CONTROL.verification.json').read_text())['exact_entries_checked'],64)
            self.assertGreater(r['inner_callback_polling']['inner_callbacks'],0);self.assertLessEqual(r['inner_callback_polling']['filesystem_polls'],r['inner_callback_polling']['inner_callbacks'])

    def test_completed_sat_after_cached_clear_hits_forced_postbarrier(self):
        with tempfile.TemporaryDirectory() as d,patch.object(helpers,'worker',worker):
            bundle=helpers.tiny_bundle(d);out=Path(d)/'out';marker=Path(d)/'stop';actual=decoder.solve_core
            def late(*a,**k):
                result=actual(*a,**k);marker.touch();return result
            with patch.object(decoder,'solve_core',late):_,r=helpers.invoke(bundle,out,'--small-control','--stop-marker',str(marker))
            self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',1));self.assertEqual(json.loads((out/'cursor.json').read_text())['next_case'],0)
            raw=json.loads(next(out.glob('*.after-cutoff.raw.json')).read_text());self.assertEqual(raw['raw_decoder_result']['status'],'SAT');self.assertEqual(raw['barrier'],'post_solve')
            self.assertFalse((out/'SMALL_CONTROL.json').exists());self.assertFalse((out/'WINNER.json').exists())
            marker.unlink();_,r=helpers.invoke(bundle,out,'--small-control','--stop-marker',str(marker),'--resume');self.assertEqual(r['status'],'SMALL_CONTROL_PASSED')

    def test_complete_negative_after_cached_clear_is_not_committed(self):
        with tempfile.TemporaryDirectory() as d,patch.object(helpers,'worker',worker):
            bundle=helpers.tiny_bundle(d);out=Path(d)/'out';marker=Path(d)/'stop'
            def late(*a,**k):
                self.assertFalse(k['cancelled']());marker.touch();return dict(status='LOCAL_UNSAT',complete=True)
            with patch.object(decoder,'solve_core',late):_,r=helpers.invoke(bundle,out,'--small-control','--stop-marker',str(marker))
            self.assertEqual(r['status'],'UNKNOWN');self.assertEqual(json.loads((out/'cursor.json').read_text())['next_case'],0);self.assertFalse((out/'completed.jsonl').exists())


if __name__=='__main__':unittest.main()
