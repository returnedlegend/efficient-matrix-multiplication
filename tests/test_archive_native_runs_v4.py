import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from scripts import archive_native_runs_v4 as archive
from scripts import native_maintenance_v4 as maintenance
from tests.test_campaign_operations_v3 import schoolbook,policy


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True)+'\n');path.chmod(0o444)


def completed(root,name='done'):
    run=root/name;run.mkdir(parents=True)
    candidate=schoolbook()
    write(run/'input.json',candidate)
    write(run/'verified/candidate.json',candidate)
    write(run/'verified/report.json',{'valid':True,'rank':125,'exact_entries_checked':15625})
    write(run/'manifest.json',{'dimension':5,'target_rank':92,'input_sha256':archive.sha256_file(run/'input.json')})
    write(run/'result.json',{'status':'ok','run_dir':str(run.resolve()),'best_rank':125,'best_candidate':candidate,
          'current_candidate':candidate,'candidates':[{'path':str((run/'verified/candidate.json').resolve()),
          'sha256':archive.sha256_file(run/'verified/candidate.json'),'rank':125,
          'verification_path':str((run/'verified/report.json').resolve())}]})
    terms=[]
    for term in candidate['terms']:
        terms.append(' '.join(str(sum(x<<i for i,x in enumerate(term[a]))) for a in ('u','v','w')))
    (run/'walk.best.txt').write_text('\n'.join(terms)+'\n')
    (run/'walk.archive').mkdir();(run/'walk.archive/0.txt').write_text('\n'.join(terms)+'\n')
    (run/'worker.log').write_bytes(b'lossless opaque\x00\xff')
    old=time.time()-120
    for p in run.rglob('*'):
        if p.is_file():os.utime(p,(old,old))
    return run


class NativeArchiveTests(unittest.TestCase):
    def test_all_three_root_forms_archive_restore_and_preserve_best_manifest(self):
        for kind in ('native/runs','native/record/runs','native/known-recovery/runs'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);runs=root/kind;run=completed(runs)
                originals={p.relative_to(runs):p.read_bytes() for p in run.rglob('*') if p.is_file()}
                result=archive.archive_runs(runs,root/'archives',max_runs=1,remove_after_verify=True)
                self.assertEqual(result['removed_runs'],1);self.assertFalse(run.exists())
                manifest=json.loads(Path(result['manifest']).read_text())
                info=manifest['runs'][0]
                self.assertEqual(info['best_rank'],125);self.assertEqual(info['preserved_manifest']['target_rank'],92)
                self.assertEqual(info['distinct_candidates'],1);self.assertGreater(len(info['candidate_audits']),4)
                self.assertEqual(len(info['best_certificate']['terms']),125)
                destination=root/'restored'/kind
                archive.restore_runs(result['archive'],result['manifest'],destination)
                for name,raw in originals.items():self.assertEqual((destination/name).read_bytes(),raw)

    def test_invalid_unlisted_archive_candidate_blocks_every_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runs=root/'native/record/runs';run=completed(runs)
            (run/'walk.archive/unlisted.txt').write_text('1 1 1\n')
            old=time.time()-120;os.utime(run/'walk.archive/unlisted.txt',(old,old))
            with self.assertRaisesRegex(ValueError,'exhaustive candidate audit failed'):
                archive.archive_runs(runs,root/'archives',remove_after_verify=True)
            self.assertTrue(run.exists());self.assertFalse((root/'archives').exists())

    def test_invalid_unlisted_json_and_embedded_candidate_fail_closed(self):
        for where in ('unlisted','embedded'):
            with self.subTest(where=where),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);runs=root/'native/runs';run=completed(runs)
                fake={'dimension':5,'field':2,'terms':[[1,1,1]]}
                if where=='unlisted':write(run/'verified/unlisted.json',fake)
                else:
                    p=run/'result.json';p.chmod(0o644);value=json.loads(p.read_text());value['current_candidate']=fake;write(p,value)
                old=time.time()-120
                for p in run.rglob('*'):
                    if p.is_file():os.utime(p,(old,old))
                with self.assertRaisesRegex(ValueError,'exhaustive candidate audit failed'):
                    archive.archive_runs(runs,root/'archives',remove_after_verify=True)
                self.assertTrue(run.exists())

    def test_active_recent_and_explicit_winner_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runs=root/'native/runs';active=runs/'active';active.mkdir(parents=True)
            recent=completed(runs,'recent');os.utime(recent/'worker.log',None)
            winner=completed(runs,'winner');write(winner/'WINNER.json',schoolbook())
            old=time.time()-120;os.utime(winner/'WINNER.json',(old,old))
            result=archive.archive_runs(runs,root/'archives',remove_after_verify=True)
            self.assertEqual(result['runs'],0);self.assertEqual(result['removed_runs'],0)
            self.assertTrue(active.exists() and recent.exists() and winner.exists())
            self.assertEqual(result['skipped'],{'active_or_incomplete':1,'too_recent':1,'explicit_record_marker':1})

    def test_archive_failure_never_removes_and_batch_byte_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runs=root/'native/runs';one=completed(runs,'a');two=completed(runs,'b')
            raw=sum(p.stat().st_size for p in one.rglob('*') if p.is_file())
            result=archive.archive_runs(runs,root/'archives',max_runs=1000,max_raw_bytes=raw+100,remove_after_verify=True)
            self.assertEqual(result['removed_runs'],1);self.assertTrue(two.exists())
            with mock.patch.object(archive,'verify_bundle',side_effect=ValueError('bad persisted bundle')):
                with self.assertRaisesRegex(ValueError,'bad persisted bundle'):
                    archive.archive_runs(runs,root/'archives2',remove_after_verify=True)
            self.assertTrue(two.exists())

    def test_record_is_preserved_before_any_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runs=root/'native/runs';run=completed(runs)
            fake={'dimension':5,'field':2,'terms':[[1,1,1]]}
            write(run/'verified/record.json',fake);old=time.time()-120;os.utime(run/'verified/record.json',(old,old))
            # Architecture control only: no actual<=92 identity is known.
            with mock.patch.object(archive,'verify_candidate',return_value={'valid':True,'exact_entries_checked':15625}),mock.patch.object(
                archive,'verify_bytes',return_value={'record_eligible':True,'exact_entries_checked':15625}):
                result=archive.archive_runs(runs,root/'archives',remove_after_verify=True)
            self.assertEqual(result['status'],'record_preserved');self.assertTrue(run.exists())
            self.assertFalse((root/'archives').exists())

    def test_symlink_root_and_non_native_root_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);real=root/'real/native/runs';real.mkdir(parents=True);(root/'link').symlink_to(root/'real')
            for path in (root/'link/native/runs',root/'unrelated/runs'):
                with self.assertRaises(ValueError):archive.runs_root(path)

    def test_dynamic_discovery_alternates_current_and_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);current=root/'current';prior=root/'prior';current.mkdir();prior.mkdir();policy(current)
            value=json.loads((current/'campaign.json').read_text());value['prior_campaign']=str(prior);write(current/'campaign.json',value)
            a=current/'learned/native/record/runs';b=prior/'old/native/runs'
            a.mkdir(parents=True);b.mkdir(parents=True)
            callback=mock.Mock(side_effect=lambda *a,**k:{'runs':0,'removed_runs':0})
            for _ in range(2):maintenance.phase(current,{'discover_all_native':True},archiver=callback,free_bytes=15*1024**3)
            self.assertEqual([call.args[0] for call in callback.call_args_list],[a,b])
            self.assertEqual(callback.call_args.kwargs['max_raw_bytes'],512*1024**2)

    def test_even_sized_source_pools_have_independent_round_robin_cursors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);current=root/'current';prior=root/'prior';current.mkdir();prior.mkdir();policy(current)
            value=json.loads((current/'campaign.json').read_text());value['prior_campaign']=str(prior);write(current/'campaign.json',value)
            current_roots=[current/f'c{i}/native/record/runs' for i in range(2)]
            old_roots=[prior/f'o{i}/native/runs' for i in range(2)]
            for path in current_roots+old_roots:path.mkdir(parents=True)
            callback=mock.Mock(side_effect=lambda *a,**k:{'runs':0,'removed_runs':0})
            for _ in range(4):maintenance.phase(current,{'discover_all_native':True},archiver=callback,free_bytes=15*1024**3)
            self.assertEqual([call.args[0] for call in callback.call_args_list],
                             [current_roots[0],old_roots[0],current_roots[1],old_roots[1]])


if __name__=='__main__':unittest.main()
