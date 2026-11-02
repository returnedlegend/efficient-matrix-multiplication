"""Collect fixed rank-one columns from independently verified native states."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--directory',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--seconds',type=int,required=True)
a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
deadline=time.monotonic()+a.seconds
terms=set();seen=set();samples=0
while time.monotonic()<deadline:
    for f in a.directory.glob('*/phase-*/walk.current.txt'):
        try:raw=f.read_bytes()
        except FileNotFoundError:continue
        h=hashlib.sha256(raw).hexdigest()
        if h in seen:continue
        triples=[tuple(map(int,line.split())) for line in raw.decode().splitlines() if line.strip()]
        if not triples or any(len(t)!=3 or any(not 0<x<1<<25 for x in t) for t in triples):
            raise ValueError('invalid native mask snapshot')
        report=verify_candidate(encode_candidate(triples),random_trials=0)
        if not report['valid']:
            (a.output_dir/'INVALID_SNAPSHOT.json').write_text(json.dumps(report,indent=2)+'\n')
            raise RuntimeError('native intermediate state failed exact tensor verification')
        seen.add(h);samples+=1;terms.update(triples)
        folder=a.output_dir/'samples';folder.mkdir(exist_ok=True)
        (folder/(h+'.txt')).write_bytes(raw)
        with (a.output_dir/'provenance.jsonl').open('a') as log:
            log.write(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),path=str(f),
                snapshot_sha256=h,rank=len(triples),exact_entries_checked=report['exact_entries_checked'],
                valid=True))+'\n')
    text=''.join(f'{x} {y} {z}\n' for x,y,z in sorted(terms))
    tmp=a.output_dir/'terms.txt.tmp';tmp.write_text(text);tmp.replace(a.output_dir/'terms.txt')
    state=dict(samples=samples,unique_terms=len(terms),terms_sha256=hashlib.sha256(text.encode()).hexdigest())
    tmp=a.output_dir/'summary.json.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(a.output_dir/'summary.json')
    time.sleep(min(15,max(0,deadline-time.monotonic())))
print(json.dumps(state))
