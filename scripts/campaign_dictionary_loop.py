"""Bounded sequential dictionary expansion with recorded, meaningful retries."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--dictionary',type=Path,required=True)
p.add_argument('--baseline',type=Path,required=True)
p.add_argument('--extra-terms',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--seconds',type=int,required=True)
a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
deadline=time.monotonic()+a.seconds
config=a.output_dir.parent/'campaign.json'
if config.exists():
    end=datetime.datetime.fromisoformat(json.loads(config.read_text())['deadline_utc'].replace('Z','+00:00')).timestamp()
    deadline=min(deadline,time.monotonic()+max(0,end-time.time()-240))
history=[];previous=None;previous_status=None;phase=0
while deadline-time.monotonic()>5:
    raw=a.extra_terms.read_bytes();h=hashlib.sha256(raw).hexdigest()
    if h==previous and previous_status=='UNSAT':
        time.sleep(min(15,max(0,deadline-time.monotonic())))
        continue
    folder=a.output_dir/f'phase-{phase:03d}';folder.mkdir()
    extras=folder/'extras.txt';extras.write_bytes(raw)
    budget=min((300,600,900)[min(phase,2)],int(deadline-time.monotonic())-3)
    encoding=('cardnetwrk','seqcounter','totalizer')[phase%3]
    command=[sys.executable,'scripts/campaign_dictionary_preprocessed.py',
             '--dictionary',str(a.dictionary),'--baseline',str(a.baseline),
             '--extra-terms',str(extras),'--output-dir',str(folder/'solve'),
             '--seconds',str(budget),'--conflicts',str(10000000*(phase+1)),
             '--memory-mb','1536','--encoding',encoding]
    meta=dict(phase=phase,command=command,extra_terms_sha256=h,
              controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              reason='new fixed-term dictionary snapshot' if h!=previous else 'new cardinality encoding and larger budget')
    (folder/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
    with (folder/'worker.log').open('w') as log:
        process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=budget+10)
    result_path=folder/'solve/result.json'
    result=json.loads(result_path.read_text()) if result_path.exists() else dict(status='ERROR',reason='missing solver result')
    meta.update(exit_code=process.returncode,result={k:result.get(k) for k in
                ('status','dictionary_size','control_status','total_elapsed_seconds','formula_sha256')})
    history.append(meta);(a.output_dir/'summary.json').write_text(json.dumps(dict(phases=history),indent=2)+'\n')
    print(json.dumps(meta),flush=True)
    previous=h;previous_status=result['status'];phase+=1
    if result['status'] in ('SAT','ERROR') or process.returncode:break
