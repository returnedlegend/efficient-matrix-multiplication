import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from mmsearch.extend_eight_bulk43 import SourceCache,compact_negative,commit_journal,restore_journal,ensure_room,raw
from mmsearch.compact_coset43 import solve_core
from mmsearch import compact_coset43
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate
from mmsearch.local_guard43 import CampaignHold
from scripts import campaign_extend_eight_bulk43 as worker
from tests.test_local_ten_guard43 import tiny_bundle,invoke


class BulkTests(unittest.TestCase):
    def test_lazy_core_source_cache_and_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);case=json.loads((b/'plan.json').read_text())['cases'][0];cache=SourceCache(b)
            with patch('mmsearch.extend_eight_bulk43.verify_candidate',wraps=verify_candidate) as checked:
                first=cache.core(case);second=cache.core(case);self.assertEqual(first[4:],second[4:]);self.assertEqual(checked.call_count,1)
            self.assertEqual(first[2]['exact_entries_checked'],64)
            with self.assertRaises(ValueError):cache.core(dict(case,shape=[9,9,9]))
            with self.assertRaises(ValueError):cache.core(dict(case,source_sha256='changed'))

    def test_compact_negative_structural_census_and_replay_hash(self):
        core=[(0b100010001>>i)&1 for i in range(9)];r=solve_core(core,[1,3,3],2,axis=0,max_points=49)
        self.assertEqual(r['status'],'LOCAL_UNSAT');c=compact_negative(r)
        self.assertNotIn('bucket_span_ranks',c);self.assertEqual(c['raw_decoder_result_sha256'],digest(r));self.assertEqual(c['bucket_count'],len(r['bucket_span_ranks']))
        bad=dict(r,bucket_span_ranks=r['bucket_span_ranks'][:-1])
        with self.assertRaises(ValueError):compact_negative(bad)
        with self.assertRaises(ValueError):compact_negative(dict(r,complete=False))

    def test_journal_rollforward_and_corrupt_result(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);case={'id':'a'};config=digest('source+config');result=dict(status='LOCAL_UNSAT',complete=True,case='a',config_sha256=config)
            path=out/'result.json';path.write_bytes(raw(result));record=dict(case='a',status='LOCAL_UNSAT',result_file=path.name,result_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            chain=commit_journal(out,0,record,config);values,last=restore_journal(out,[case],config);self.assertEqual((len(values),last),(1,chain))
            path.write_text('{}')
            with self.assertRaises(ValueError):restore_journal(out,[case],config)

    def test_driver_rolls_forward_without_requery_or_core_build(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out'
            with patch('tests.test_local_ten_guard43.worker',worker):
                _,r=invoke(b,out,'--controls-only');self.assertEqual(r['status'],'CONTROLS_PASSED')
                state=json.loads((out/'cursor.json').read_text());state.update(next_case=0,results=[],terminal=False,status='UNKNOWN');(out/'cursor.json').write_text(json.dumps(state))
                with patch.object(SourceCache,'core',side_effect=AssertionError('committed case must not be rebuilt')):
                    _,r=invoke(b,out,'--controls-only','--resume')
                self.assertEqual((r['status'],r['queries_this_invocation']),('CONTROLS_PASSED',0))

    def test_percase_cutoff_raw_witness_open_and_lazy_resume(self):
        with tempfile.TemporaryDirectory() as d:
            b=tiny_bundle(d);out=Path(d)/'out';actual=compact_coset43.solve_core
            def delayed(*args,**kwargs):result=actual(*args,**kwargs);time.sleep(.04);return result
            with patch('tests.test_local_ten_guard43.worker',worker):
                _,r=invoke(b,out,'--small-control','--per-case-seconds','.02',solver=delayed)
                self.assertEqual((r['status'],r['queries_this_invocation']),('UNKNOWN',1));self.assertTrue((out/'current/core.json').exists())
                self.assertEqual(json.loads((out/'cursor.json').read_text())['next_case'],0);self.assertEqual(json.loads(next(out.glob('*.after-cutoff.raw.json')).read_text())['raw_decoder_result']['status'],'SAT')
                _,r=invoke(b,out,'--small-control','--per-case-seconds','1','--resume')
                self.assertEqual(r['status'],'SMALL_CONTROL_PASSED');self.assertFalse((out/'current').exists())
                self.assertEqual(json.loads((out/'cursor.json').read_text())['attempts']['0'],2)

    def test_phase_byte_reserve_is_unknown_hold(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'f').write_bytes(b'x'*95)
            with self.assertRaises(CampaignHold):ensure_room(d,cap=100,reserve=10)


if __name__=='__main__':unittest.main()
