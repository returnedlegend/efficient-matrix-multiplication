#!/usr/bin/env python3
"""Tiny-only adversarial lifecycle controls; never selects the n5 plan."""
import argparse
from datetime import datetime,timezone
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args();root=a.output_dir;root.mkdir(parents=True,exist_ok=False);b=root/'bundle';shutil.copytree(a.bundle,b)
 campaign=root/'campaign';campaign.mkdir();(campaign/'queue_state.json').write_text('{}');guard=campaign/'resource.json';ticks=int(Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19])
 def refresh(storage=0):guard.write_text(json.dumps(dict(pid=os.getpid(),process_identity=dict(start_ticks=ticks),updated_utc=datetime.now(timezone.utc).isoformat(),campaign_allocated_bytes=storage,stop_reason=None)))
 refresh();env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(b/'runtime'));runner=b/'runtime/campaign_fullpassing_v2_43.py';records={}
 def command(out,seconds=5,extra=()):return [sys.executable,str(runner),'--bundle',str(b),'--campaign',str(campaign),'--guard-state',str(guard),'--output-dir',str(out),'--small-control','--seconds',str(seconds),'--memory-mb','256']+list(extra)
 def run(label,cmd,expected,refresh_guard=True):
  if refresh_guard:refresh()
  result=subprocess.run(cmd,cwd='/tmp',env=env,capture_output=True,text=True)
  if result.returncode:raise AssertionError((label,result.stderr))
  value=json.loads(result.stdout)
  if value['status']!=expected:raise AssertionError((label,value))
  records[label]=dict(command=cmd,stdout=result.stdout,stderr=result.stderr);return value
 run('positive',command(root/'positive'),'SMALL_CONTROL_PASSED');run('positive-resume',command(root/'positive',extra=['--restart']),'SMALL_CONTROL_PASSED')
 for kind in ['late-negative','late-sat','late-proof']:
  out=root/kind;args=command(out,.04)[2:]
  source='''import sys,time,importlib.util
from pathlib import Path
b=Path(sys.argv[1]);args=sys.argv[2:];sys.path.insert(0,str(b/'runtime'))
import mmsearch.fullpassing43 as cp
spec=importlib.util.spec_from_file_location('private_worker',b/'runtime/campaign_fullpassing_v2_43.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
kind=KIND
original=cp.solve_cp_core
if kind!='late-proof':
 def legacy(core,shape,target,axis,cancelled=None):
  time.sleep(.1)
  return {'status':'LOCAL_UNSAT','complete':True,'legacy_raw':'deliberate late stub, not a mathematical certificate'} if kind=='late-negative' else original(core,shape,target,axis,cancelled=lambda:False)
 cp.solve_cp_core=legacy
else:
 old=w.atomic
 def delayed(path,value):
  if path.name=='SMALL_CONTROL.verification.json':time.sleep(.1)
  return old(path,value)
 w.atomic=delayed
sys.argv=['control']+args
raise SystemExit(w.main())
'''.replace('KIND',repr(kind))
  result=subprocess.run([sys.executable,'-c',source,str(b)]+args,cwd='/tmp',env=env,capture_output=True,text=True)
  if result.returncode or json.loads(result.stdout)['status']!='UNKNOWN':raise AssertionError((kind,result.stderr,result.stdout))
  cd=out/'chunks/tiny'
  if (cd/'results.jsonl').stat().st_size or (out/'SMALL_CONTROL.json').exists():raise AssertionError('late result closed or published')
  files=list((cd/'attempts').glob('*after-cutoff.json.gz'));raw=json.loads(gzip.decompress(files[0].read_bytes()))
  if len(files)!=1 or not raw['after_cutoff'] or raw['raw_result'] is None or not raw['source_sha256'] or not raw['core']['core_sha256']:raise AssertionError('late raw witness/provenance missing')
  if kind=='late-proof' and (not raw['candidate'] or raw['full_verification']['exact_entries_checked']!=64):raise AssertionError('late proof not retained')
  records[kind]=dict(stdout=result.stdout,private_memory_patch=source,closed_negative=False,raw_archive=str(files[0]))
  run(kind+'-resume',command(out,extra=['--restart']),'SMALL_CONTROL_PASSED')
 for kind,expected in [('chunk-cap','UNKNOWN'),('error-stop','ERROR')]:
  out=root/kind;args=command(out)[2:]
  source='''import sys,importlib.util
from pathlib import Path
b=Path(sys.argv[1]);sys.path.insert(0,str(b/'runtime'))
import mmsearch.fullpassing43 as cp
spec=importlib.util.spec_from_file_location('private_worker',b/'runtime/campaign_fullpassing_v2_43.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
kind=KIND
if kind=='chunk-cap':w.allocated=lambda _:128*1024**2
else:
 def broken(*args,**kwargs):raise RuntimeError('deliberate tiny control failure')
 cp.solve_cp_core=broken
sys.argv=['control']+sys.argv[2:]
raise SystemExit(w.main())
'''.replace('KIND',repr(kind))
  result=subprocess.run([sys.executable,'-c',source,str(b)]+args,cwd='/tmp',env=env,capture_output=True,text=True);value=json.loads(result.stdout)
  if value['status']!=expected or result.returncode!=(2 if kind=='error-stop' else 0):raise AssertionError((kind,result.stdout,result.stderr))
  records[kind]=dict(stdout=result.stdout,private_memory_patch=source)
  if kind=='chunk-cap':
   if value['queries']:raise AssertionError('storage cap dispatched decoder')
   run(kind+'-resume',command(out,extra=['--restart']),'SMALL_CONTROL_PASSED')
  else:
   if value['queries']!=1:raise AssertionError('ERROR dispatch was not counted')
   result=subprocess.run(command(out,extra=['--restart']),cwd='/tmp',env=env,capture_output=True,text=True)
   if result.returncode!=2 or json.loads(result.stdout)['queries']!=0:raise AssertionError('ERROR resume did not stop')
   records['error-stop-resume']=dict(stdout=result.stdout,returncode=result.returncode)
 # Valid JSON with the wrong shape may appear after the decoder starts.
 # These are memory-only tiny adapters; the frozen files are never changed.
 for destination in ['queue','resource']:
  for value in [None,[]]:
   label=destination+('-null' if value is None else '-list');target=campaign/'queue_state.json' if destination=='queue' else guard
   refresh();(campaign/'queue_state.json').write_text('{}');target.write_text(json.dumps(value))
   before=run('before-'+label,command(root/('before-'+label)),'UNKNOWN',False)
   if before['queries']:raise AssertionError('malformed external state dispatched decoder')
   (campaign/'queue_state.json').write_text('{}');run('before-'+label+'-resume',command(root/('before-'+label),extra=['--restart']),'SMALL_CONTROL_PASSED')
   for rawstatus in (['SAT','LOCAL_UNSAT'] if destination=='queue' else ['SAT']):
    name='after-'+label+'-'+rawstatus.lower();out=root/name;args=command(out)[2:];refresh();(campaign/'queue_state.json').write_text('{}')
    source='''import sys,importlib.util,json
from pathlib import Path
b=Path(sys.argv[1]);sys.path.insert(0,str(b/'runtime'))
import mmsearch.fullpassing43 as cp
original=cp.solve_cp_core
def noncooperative(core,shape,target,axis,cancelled=None):
 Path(STATE_PATH).write_text(json.dumps(BAD_STATE))
 return {'status':'LOCAL_UNSAT','complete':True,'stub':'deliberately artificial tiny raw negative'} if RAW_STATUS=='LOCAL_UNSAT' else original(core,shape,target,axis,cancelled=lambda:False)
cp.solve_cp_core=noncooperative
spec=importlib.util.spec_from_file_location('private_worker',b/'runtime/campaign_fullpassing_v2_43.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
sys.argv=['control']+sys.argv[2:]
raise SystemExit(w.main())
'''.replace('STATE_PATH',repr(str(target))).replace('BAD_STATE',repr(value)).replace('RAW_STATUS',repr(rawstatus))
    result=subprocess.run([sys.executable,'-c',source,str(b)]+args,cwd='/tmp',env=env,capture_output=True,text=True)
    if result.returncode or json.loads(result.stdout)['status']!='UNKNOWN':raise AssertionError((name,result.stdout,result.stderr))
    cd=out/'chunks/tiny';files=list((cd/'attempts').glob('*after-cutoff.json.gz'));retained=json.loads(gzip.decompress(files[0].read_bytes()))
    if (cd/'results.jsonl').stat().st_size or (out/'SMALL_CONTROL.json').exists() or len(files)!=1:raise AssertionError('malformed postcall result closed/published')
    if not retained['after_cutoff'] or retained['raw_result']['status']!=rawstatus or not retained['core']['core_sha256'] or not retained['source_sha256']:raise AssertionError('postcall raw decision/provenance lost')
    if rawstatus=='SAT' and not retained['raw_result'].get('products'):raise AssertionError('raw SAT products lost')
    records[name]=dict(stdout=result.stdout,private_memory_patch=source,closed_negative=False,raw_archive=str(files[0]))
    (campaign/'queue_state.json').write_text('{}');run(name+'-resume',command(out,extra=['--restart']),'SMALL_CONTROL_PASSED')
 run('source-control',command(root/'source-control',extra=['--controls-only']),'CONTROLS_PASSED')
 cd=root/'source-control/chunks/tiny';before=(cd/'results.jsonl').read_bytes();(cd/'results.jsonl').open('ab').write(b'uncommitted-tail')
 run('journal-tail-recovery',command(root/'source-control',extra=['--controls-only','--restart']),'CONTROLS_PASSED')
 if (cd/'results.jsonl').read_bytes()!=before:raise AssertionError('uncommitted journal tail retained')
 archive=next((cd/'attempts').glob('*.json.gz'));archive.chmod(0o644);archive.write_bytes(archive.read_bytes()+b'corrupt')
 result=subprocess.run(command(root/'source-control',extra=['--controls-only','--restart']),cwd='/tmp',env=env,capture_output=True,text=True)
 if result.returncode==0 or 'archive changed' not in result.stderr:raise AssertionError('corrupt completed proof accepted')
 records['corrupt-prior']=dict(exit=result.returncode,stderr=result.stderr)
 refresh(5*1024**3);value=run('5GiB-hold',command(root/'guard-hold'),'UNKNOWN',False)
 if value['queries']:raise AssertionError('resource hold dispatched')
 run('guard-hold-resume',command(root/'guard-hold',extra=['--restart']),'SMALL_CONTROL_PASSED')
 (root/'REPORT.json').write_text(json.dumps(dict(status='PASS',n5_decoder_queries=0,records=records),indent=2));print(json.dumps(dict(status='PASS',groups=list(records),n5_decoder_queries=0)))

if __name__=='__main__':main()
