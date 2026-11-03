import csv
import json
from pathlib import Path
import tempfile
import unittest
from scripts.collect_rl_campaign_report import collect, Reader, write_snapshot


class CollectorTests(unittest.TestCase):
    def put(self, root, path, value):
        path=root/path; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value)); return path

    def test_statuses_limits_hashes_and_partial_cpu_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.put(root,'queue.json',{'jobs':[{'id':'dictionary-new1','cpu':3,'memory_mb':2048,'seconds':915}]})
            self.put(root,'queue_state.json',{'jobs':{'dictionary-new1':{'status':'completed'}}})
            self.put(root,'dictionary-new1-job.result.json',{'exit_code':0,'cpu_seconds':4.59,'elapsed_seconds':900,
                'cpu':3,'memory_mb':2048,'wall_seconds':915,'command':[]})
            self.put(root,'dictionary-new1/result.json',{'status':'BUDGET_EXHAUSTED','control_status':'SAT'})
            self.put(root,'dictionary-new1/manifest.json',{'code_sha256':{'worker.py':'a'*64},'input_sha256':'b'*64})
            self.put(root,'dictionary-new1/resource_reconstruction.json',{'reconstructed_cpu_seconds':891.78})
            self.put(root,'dictionary-new1/native/known-recovery/runs/x/summary.json',{'status':'DO_NOT_READ'})
            report=collect(root); row=report['jobs'][0]
            self.assertEqual(row['registration_status'],'completed')
            self.assertEqual(row['exit_code'],0)
            self.assertEqual(row['artifact_status'],'result.json:BUDGET_EXHAUSTED')
            self.assertEqual(row['control_status'],'SAT')
            self.assertEqual(row['memory_mb'],2048)
            self.assertIn('manifest.json:code_sha256.worker.py',row['input_code_hash_references'])
            self.assertEqual(report['resource_totals']['sum_reported_cpu_seconds'],4.59)
            self.assertEqual(report['resource_totals']['dictionary_grandchild_reconstruction']['reconstructed_cpu_seconds'],891.78)
            self.assertFalse(any('/native/' in x['path'] for x in report['evidence_files']))

    def test_partial_oversize_and_symlink_inputs_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'bad').write_text('{');(root/'large').write_text('x'*100)
            (root/'link').symlink_to(root/'large');reader=Reader(per_file=32,total=64)
            self.assertEqual(reader.read(root/'bad')[1]['read_status'],'unreadable_or_partial_json')
            self.assertEqual(reader.read(root/'large')[1]['read_status'],'per_file_limit')
            self.assertEqual(reader.read(root/'link')[1]['read_status'],'symlink_skipped')

    def test_repeatable_export_and_job_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.put(root,'queue.json',{'jobs':[{'id':'a'},{'id':'b'}]})
            report=collect(root,max_jobs=1);self.assertTrue(report['bounds']['jobs_truncated'])
            output=root/'snapshot';write_snapshot(report,output);write_snapshot(report,output)
            with (output/'jobs.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],'a')
            self.assertEqual(json.loads((output/'report.json').read_text())['format'],'bounded-campaign-report-v1')

if __name__=='__main__':unittest.main()
