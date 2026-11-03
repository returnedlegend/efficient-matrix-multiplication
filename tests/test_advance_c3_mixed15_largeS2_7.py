import json,tempfile,unittest
from pathlib import Path
from scripts.advance_c3_mixed15_largeS2_7 import audit,budget_ok,sha

def put(p,v):p.write_text(json.dumps(v))
class AdvanceControls(unittest.TestCase):
    def test_boundaries(self):
        self.assertTrue(budget_ok(1560));self.assertFalse(budget_ok(1560.001))
    def test_unknown_and_tamper_do_not_advance(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);out=root/'job';out.mkdir();put(root/'job-job.result.json',dict(exit_code=0,timed_out=False,interrupted=False,cpu_seconds=1))
            row=dict(case='case',status='LOCAL_UNSAT',complete=True,raw_decoder=dict(complete=True));put(out/'case.result.json',row)
            s=dict(config_sha256='pin',status='LARGE_S2_BATCH_LOCAL_UNSAT',stop_reason=None,decoder_calls=1,results=[row]);put(out/'summary.json',s)
            m=dict(config_sha256='pin',summary_sha256=sha(out/'summary.json'),result_files={'case.result.json':sha(out/'case.result.json')});put(out/'result-manifest.json',m)
            self.assertEqual(audit(root,'job',['case'],'pin')['cpu_seconds'],1)
            put(out/'case.result.json',dict(row,status='UNKNOWN'))
            with self.assertRaises(ValueError):audit(root,'job',['case'],'pin')
            row.update(status='UNKNOWN',complete=False);s['results']=[row];put(out/'case.result.json',row);put(out/'summary.json',s);m.update(summary_sha256=sha(out/'summary.json'),result_files={'case.result.json':sha(out/'case.result.json')});put(out/'result-manifest.json',m)
            with self.assertRaises(ValueError):audit(root,'job',['case'],'pin')
if __name__=='__main__':unittest.main()
