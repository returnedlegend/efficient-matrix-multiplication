"""Merge validated fixed-term streams atomically; these are not algorithms."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,action='append',required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--seconds',type=int,required=True)
a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
deadline=time.monotonic()+a.seconds
config=a.output.parent.parent/'campaign.json'
if config.exists():
    end=datetime.datetime.fromisoformat(json.loads(config.read_text())['deadline_utc'].replace('Z','+00:00')).timestamp()
    deadline=min(deadline,time.monotonic()+max(0,end-time.time()-180))
previous=None
while time.monotonic()<deadline:
    terms=set();sources={}
    for path in a.input:
        raw=path.read_bytes();sources[str(path)]=hashlib.sha256(raw).hexdigest()
        for line in raw.decode().splitlines():
            if not line.strip():continue
            triple=tuple(map(int,line.split()))
            if len(triple)!=3 or any(not 0<x<1<<25 for x in triple):raise ValueError('invalid fixed term')
            terms.add(triple)
    text=''.join(f'{x} {y} {z}\n' for x,y,z in sorted(terms));h=hashlib.sha256(text.encode()).hexdigest()
    if h!=previous:
        tmp=a.output.with_name(a.output.name+'.tmp');tmp.write_text(text);tmp.replace(a.output)
        with a.output.with_suffix('.provenance.jsonl').open('a') as log:
            log.write(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                                     inputs=sources,output_sha256=h,terms=len(terms)))+'\n')
        previous=h
    time.sleep(min(15,max(0,deadline-time.monotonic())))
