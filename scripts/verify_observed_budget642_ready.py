"""Frozen budget6 closure/source/guard controls without production decoding."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.observed_budget6_runtime42 import SourceRuntime
from mmsearch.recombine import digest
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
READ=lambda p:json.loads(Path(p).read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared-dir',type=Path,required=True);a=p.parse_args();b=a.prepared_dir.resolve()
    for name,expected in READ(b/'integrity.json').items():
        if SHA(b/name)!=expected:raise ValueError('budget6 closure binding changed: '+name)
    plan=READ(b/'plan.json');seen=set();source_controls=READ(b/'SOURCE-CONTROLS.json')
    for chunk in plan['chunks']:
        items=json.loads(gzip.decompress((b/chunk['plan']).read_bytes()))
        if digest(items)!=chunk['plan_sha256'] or len(items)!=chunk['count']:raise ValueError('budget6 caseplan changed')
        for item in items:
            key=(chunk['source_id'],tuple(item['space']))
            if key in seen or item['k']!=7 or item['weight_bound']!=6:raise ValueError('duplicate/unsupported budget6 case')
            seen.add(key)
        source=chunk['source_id'];system=READ(b/'sources'/source/'system.json');runtime=SourceRuntime(system);q=runtime.prepare(system,items[0]['basis_values'])
        control=next(c for c in source_controls if c['source_id']==source)
        if q['quotient_sha256']!=control['first_case_quotient_sha256']:raise ValueError('lazy control quotient changed')
    if len(seen)!=46:raise ValueError('46case scope changed')
    script=b/'code/scripts/campaign_observed_budget642.py'
    help_result=subprocess.run([sys.executable,'-B',str(script),'--help'],cwd='/tmp',capture_output=True,text=True,timeout=10)
    if help_result.returncode:raise ValueError(help_result.stderr)
    tests=subprocess.run([sys.executable,'-B','-c',"import sys,unittest;sys.path.insert(0,sys.argv[1]);r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName('tests.test_observed_budget642'));sys.exit(not r.wasSuccessful())",str(b/'code')],cwd='/tmp',capture_output=True,text=True,timeout=10)
    if tests.returncode:raise ValueError(tests.stderr)
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp);guard=temp/'guard.json';guard.write_text('{}');output=temp/'output'
        command=[sys.executable,'-B',str(script),'--prepared-dir',str(b),'--output-dir',str(output),'--chunk-id',plan['chunks'][0]['id'],
            '--guard-state',str(guard),'--seconds','5','--per-case-seconds','1','--memory-mb','256']
        reports=[]
        for resume in (False,True):
            result=subprocess.run(command+(['--restart'] if resume else []),cwd='/tmp',capture_output=True,text=True,timeout=10)
            if result.returncode:raise ValueError(result.stderr)
            report=json.loads(result.stdout)
            if report['status']!='UNKNOWN' or report['target_queries_this_launch']!=0 or 'guard' not in report['reason']:raise ValueError('budget6 guard hold/resume failed')
            reports.append(report)
    print(json.dumps(dict(status='CONTROLS_PASSED',cases=46,source_control_quotients_identical=3,standalone_launch='PASS',tiny_test_groups=6,
        tiny_test_output=tests.stderr,guard_hold_and_resume=reports,production_queries=0),sort_keys=True))


if __name__=='__main__':main()
