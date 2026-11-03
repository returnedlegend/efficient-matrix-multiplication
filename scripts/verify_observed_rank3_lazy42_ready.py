"""Source/plan/quotient/standalone launch controls, without production decoding."""
import argparse
from datetime import datetime,timezone
import os
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.observed_rank3_lazy42 import SourceRuntime
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.verify import verify_candidate
from mmsearch.recombine import digest
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared-dir',type=Path,required=True);a=p.parse_args();b=a.prepared_dir.resolve()
    bindings=READ(b/'integrity.json')
    for name,expected in bindings.items():
        if SHA(b/name)!=expected:raise ValueError('hash mismatch: '+name)
    plan=READ(b/'plan.json');exclusions=READ(b/'pilot-exclusions.json');seen=set();source_counts={};fullchecks=[];quotient_checks=0
    for source in plan['sources']:
        system=READ(b/'sources'/source/'system.json');runtime=SourceRuntime(system)
        report=verify_candidate(decode_vectors(system,system['baseline_vectors']),random_trials=0)
        if not report['valid'] or report['rank']!=93 or report['exact_entries_checked']!=15625:raise ValueError('invalid source')
        fullchecks.append(dict(source_id=source,verification=report))
        for event in exclusions:
            case=event['case']
            if case['source_id']!=source:continue
            q=runtime.prepare(system,case['basis_values'])
            if q['quotient_sha256']!=case['quotient_sha256']:raise ValueError('cached quotient differs from completed pilot')
            quotient_checks+=1
    excluded={(event['case']['source_id'],tuple(event['case']['space'])) for event in exclusions}
    for chunk in plan['chunks']:
        items=json.loads(gzip.decompress((b/chunk['plan']).read_bytes()))
        if digest(items)!=chunk['plan_sha256'] or len(items)!=chunk['count'] or not 1<=len(items)<=2000:raise ValueError('chunk binding/count invalid')
        for item in items:
            key=(chunk['source_id'],tuple(item['space']))
            if key in seen or key in excluded:raise ValueError('overlap/repeated pilot case')
            seen.add(key)
            if not 4<=item['k']<=6 or item['weight_bound']!=item['k']-1:raise ValueError('unsupported plan case')
        source_counts[chunk['source_id']]=source_counts.get(chunk['source_id'],0)+len(items)
    if len(seen)!=47722 or quotient_checks!=18:raise ValueError('continuation coverage mismatch')
    script=b/'code/scripts/campaign_observed_rank3_lazy42.py'
    done=subprocess.run([sys.executable,'-B',str(script),'--help'],cwd='/tmp',capture_output=True,text=True,timeout=10)
    if done.returncode:raise ValueError(done.stderr)
    with tempfile.TemporaryDirectory() as temporary:
        temporary=Path(temporary);guard=temporary/'guard.json';guard.write_text('{}')
        output=temporary/'hold';chunk=plan['chunks'][0]['id']
        command=[sys.executable,'-B',str(script),'--prepared-dir',str(b),'--output-dir',str(output),'--chunk-id',chunk,
            '--guard-state',str(guard),'--seconds','5','--per-case-seconds','1','--memory-mb','256']
        reports=[]
        for resume in (False,True):
            result=subprocess.run(command+(['--restart'] if resume else []),cwd='/tmp',capture_output=True,text=True,timeout=10)
            if result.returncode:raise ValueError(result.stderr)
            report=json.loads(result.stdout)
            if report['status']!='UNKNOWN' or report['target_queries_this_launch']!=0 or 'guard' not in report['reason']:raise ValueError('guard hold/resume did not preserve UNKNOWN')
            reports.append(report)
        ticks=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
        guard.write_text(json.dumps(dict(updated_utc=datetime.now(timezone.utc).isoformat(),pid=os.getpid(),
            process_identity={'start_ticks':ticks},stop_reason=None,campaign_allocated_bytes=0)))
        sparse=output/'chunks'/chunk/'storage-cap.control'
        with sparse.open('wb') as stream:stream.truncate(128*1024**2-8*1024**2+1)
        result=subprocess.run(command+['--restart'],cwd='/tmp',capture_output=True,text=True,timeout=10)
        if result.returncode:raise ValueError(result.stderr)
        storage_report=json.loads(result.stdout)
        if storage_report['status']!='UNKNOWN' or storage_report['target_queries_this_launch']!=0 or 'storage reserve' not in storage_report['reason']:
            raise ValueError('128MiB chunk hold failed')
        sparse.unlink()
    print(json.dumps(dict(status='CONTROLS_PASSED',source_checks=fullchecks,pilot_quotients_identical=quotient_checks,remaining=len(seen),
        source_remaining=source_counts,chunks=len(plan['chunks']),standalone_launch='PASS',guard_hold_and_resume=reports,chunk_storage_cap_hold=storage_report,target_decoder_queries=0),sort_keys=True))


if __name__=='__main__':main()
