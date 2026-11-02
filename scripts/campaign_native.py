"""Run bounded native phases and independently verify a capped seed portfolio."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.search import decode_candidate,encode_candidate,is_cyclic
from mmsearch.verify import verify_candidate,write_standalone_verifier


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(path)


def drain_final_best(prefix, output_dir, metadata, n=5, target=92):
    """A successful native process can exit between periodic polling scans."""
    path=prefix.with_suffix('.best.txt')
    if not path.exists():return False
    triples=[tuple(map(int,line.split())) for line in path.read_text().splitlines() if line.strip()]
    if not triples or len(triples)>target:return False
    if any(len(t)!=3 or any(not 0<=x<1<<(n*n) for x in t) for t in triples):
        raise ValueError('malformed final native candidate')
    candidate=encode_candidate(triples,n,method='native-final-target',parent=metadata)
    report=verify_candidate(candidate,random_trials=64)
    if not report['valid']:raise RuntimeError('final native target failed independent verification')
    save(output_dir/'WINNER.json',candidate)
    save(output_dir/'WINNER.verification.json',report)
    write_standalone_verifier(output_dir/'WINNER.verify.py')
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--input',type=Path,default=Path('artifacts/km93_f2.json'))
    p.add_argument('--pool',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=int,required=True)
    p.add_argument('--phase-seconds',type=int,default=600)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--cyclic',action='store_true')
    args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    exported=args.output_dir/'verified';exported.mkdir(exist_ok=True)
    deadline=time.monotonic()+args.seconds
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    sources=[args.input]+sorted(args.pool.glob('*.json'))
    rng=random.Random(args.seed);rng.shuffle(sources)
    binary_sha=hashlib.sha256(args.binary.read_bytes()).hexdigest()
    phases=[];seen={f.stem for f in exported.glob('*.json')};phase=0
    while time.monotonic()<deadline and not stopped:
        source=sources[phase%len(sources)]
        candidate=json.loads(source.read_text())
        terms=decode_candidate(candidate)
        if len(terms)!=93 or not verify_candidate(candidate,random_trials=0)['valid']:
            raise ValueError('invalid phase seed')
        if args.cyclic and not is_cyclic(terms):
            phase+=1
            continue
        folder=args.output_dir/f'phase-{phase:03d}';folder.mkdir(exist_ok=True)
        inp=folder/'input.txt'
        inp.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms))
        prefix=folder/'walk'
        budget=max(1,min(args.phase_seconds,int(deadline-time.monotonic())))
        command=[str(args.binary.resolve()),'--input',str(inp),'--output',str(prefix),'--n','5',
                 '--target','92','--max-rank',str(97+(phase%3)*2),'--seed',str(args.seed+phase*1009),
                 '--steps','100000000000','--seconds',str(budget),'--checkpoint-seconds','15',
                 '--archive-size','256','--archive-every','1000',
                 '--plus-every',str((100,250,1000)[phase%3]),
                 '--restart-every',str((50000,200000,1000000)[phase%3])]
        if args.cyclic:command.append('--cyclic')
        meta=dict(phase=phase,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  binary_sha256=binary_sha,command=command,cyclic=args.cyclic,
                  wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        save(folder/'manifest.json',meta)
        with (folder/'worker.log').open('w') as log:
            proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            last_scan=0
            while proc.poll() is None and not stopped:
                if time.monotonic()-last_scan>=15:
                    last_scan=time.monotonic()
                    paths=[prefix.with_suffix('.best.txt')]
                    archives=list(folder.glob('walk.archive/*.txt'))
                    rng.shuffle(archives);paths+=archives[:8]
                    for path in paths:
                        try:
                            triples=[tuple(map(int,line.split())) for line in path.read_text().splitlines() if line.strip()]
                            if any(len(t)!=3 or any(not 0<x<1<<25 for x in t) for t in triples):continue
                            if len(triples)>93:continue
                            code=';'.join(','.join(map(str,t)) for t in sorted(triples))
                            h=hashlib.sha256(code.encode()).hexdigest()
                            if h in seen or (len(seen)>=128 and len(triples)==93):continue
                            d=encode_candidate(triples,5,method='native-exact-flip-checkpoint',
                                               parent=meta,path=str(path),term_set_sha256=h)
                            report=verify_candidate(d,random_trials=4)
                            if not report['valid']:raise RuntimeError('native checkpoint tensor verification failed')
                            save(exported/(h+'.json'),d);seen.add(h)
                            if len(triples)<=92:
                                save(args.output_dir/'WINNER.json',d)
                                save(args.output_dir/'WINNER.verification.json',report)
                                write_standalone_verifier(args.output_dir/'WINNER.verify.py')
                                stopped=True
                                break
                        except FileNotFoundError:pass
                time.sleep(1)
            if proc.poll() is None:
                proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        if drain_final_best(prefix,args.output_dir,meta):stopped=True
        meta.update(exit_code=proc.returncode,verified_portfolio_size=len(seen))
        phases.append(meta);save(args.output_dir/'summary.json',dict(phases=phases,verified=len(seen),stopped=stopped))
        phase+=1
    print(json.dumps(dict(phases=len(phases),verified=len(seen),stopped=stopped)),flush=True)


if __name__=='__main__':main()
