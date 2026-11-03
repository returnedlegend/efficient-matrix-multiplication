"""Explicit-certificate/full-global-mask inverse F2 cube-polarization audit.

No directory discovery or watcher. Complete patterns may change fixed-cube
inventory; a negative scan is never a rank lower bound or UNSAT.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from mmsearch.inverse_cube_polarization import compress_candidate
from mmsearch.kernel_coset_seeds import exclusive
from mmsearch.recombine import digest
from mmsearch.search import encode_candidate
from mmsearch.slice_compression import canonical_masks,InvalidCertificate
from scripts.scan_slice_compressions import _freeze_first_winner,strict_json


def freeze(path,value):exclusive(path,(json.dumps(value,sort_keys=True,indent=2)+'\n').encode())


def read_source(path,kind,raw=None):
    raw=path.read_bytes() if raw is None else raw
    if kind=='certificate':
        value=strict_json(raw)
        if type(value.get('dimension')) is not int or value['dimension']!=5 or type(value.get('field')) is not int or value['field']!=2:
            raise ValueError('scanner certificate must declare dimension5 and field2 exactly')
    else:
        terms=[]
        for line in raw.decode().splitlines():
            fields=line.split()
            if len(fields)!=3 or any(not v.isdecimal() for v in fields):raise ValueError('full-global masks require three decimal integers per line')
            term=tuple(map(int,fields))
            if any(not 0<=v<1<<25 for v in term):raise ValueError('full-global mask outside exact25bit range')
            terms.append(term)
        if not terms:raise ValueError('empty full-global mask source')
        value=encode_candidate(terms,5,source_format='explicit full-global F2 masks; independently verified before trust')
    canonical,normalization=canonical_masks(value)
    return raw,value,digest(dict(dimension=5,field=2,terms=canonical)),normalization


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,action='append',default=[])
    p.add_argument('--full-global-mask',type=Path,action='append',default=[])
    p.add_argument('--output-dir','--outdir',dest='output_dir',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=120)
    p.add_argument('--memory-mb',type=int,default=512)
    a=p.parse_args(argv)
    if not(a.input or a.full_global_mask) or not math.isfinite(a.seconds) or a.seconds<=0 or not 128<=a.memory_mb<=512:
        p.error('explicit sources, positive finite seconds and memory128..512MiB required')
    resource.setrlimit(resource.RLIMIT_AS,(a.memory_mb*1024**2,a.memory_mb*1024**2))
    started=time.monotonic();start_cpu=time.process_time();deadline=started+a.seconds
    root=a.output_dir;root.mkdir(parents=True,exist_ok=False);code={}
    for name in ('scripts/scan_inverse_cube_polarizations.py','mmsearch/inverse_cube_polarization.py',
        'mmsearch/verify.py','mmsearch/search.py','mmsearch/recombine.py','mmsearch/slice_compression.py',
        'mmsearch/kernel_coset_seeds.py','mmsearch/free_factor_sat.py','mmsearch/recombine_sat.py',
        'mmsearch/__init__.py','scripts/scan_slice_compressions.py','tests/test_inverse_cube_polarization.py'):
        raw=(REPO/name).read_bytes();exclusive(root/'code'/name,raw);code[name]=hashlib.sha256(raw).hexdigest()
    freeze(root/'provenance.json',dict(code_sha256=code,resources=dict(memory_mb=a.memory_mb,wall_seconds=a.seconds,pid=os.getpid(),affinity=sorted(os.sched_getaffinity(0))),
        source_policy='explicit sources only; no unchanged65negative audit rerun unless explicitly supplied',
        scope='F2 only; rank93 is nonnovel; changes fixedcube constraints; negative pattern scan is not a rank lower bound'))
    records=[];seen=set();winner=False;stop_reason='all explicit sources considered'
    for index,(path,kind) in enumerate([(path,'certificate') for path in a.input]+[(path,'full-global-mask') for path in a.full_global_mask]):
        if time.monotonic()>=deadline:stop_reason='wall budget reached';break
        record=dict(source=str(path.resolve()),kind=kind)
        try:
            raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
            snapshot=root/'inputs'/f'{index:04d}-{sha}.raw';exclusive(snapshot,raw)
            record.update(raw_sha256=sha,raw_snapshot=str(snapshot.resolve()))
            raw,value,key,normalization=read_source(path,kind,raw)
            record.update(raw_sha256=hashlib.sha256(raw).hexdigest(),full_term_sha256=key,normalization=normalization)
            if key in seen:record['status']='DUPLICATE_FULL_TERMS';records.append(record);continue
            seen.add(key);directory=root/'sources'/f'{index:04d}-{key[:16]}'
            exclusive(directory/'input.raw',raw);freeze(directory/'input.json',value)
            result=compress_candidate(value,seconds=max(1e-9,deadline-time.monotonic()),stop_at_record=True)
            candidate=result.pop('candidate')
            freeze(directory/'candidate.json',candidate);freeze(directory/'proof.json',result)
            record.update(status='VERIFIED',source_rank=result['source_rank'],final_rank=result['final_rank'],
                applied_moves=len(result['moves']),report=str((directory/'proof.json').resolve()),
                output_raw_sha256=hashlib.sha256((directory/'candidate.json').read_bytes()).hexdigest(),
                exact_entries_checked=result['final_verification']['exact_entries_checked'])
            if result['winner_eligible']:
                record['winner_checksums']=_freeze_first_winner(root,candidate);winner=True
        except Exception as exc:
            record.update(status='ERROR',error=f'{type(exc).__name__}: {exc}')
            if isinstance(exc,InvalidCertificate) and exc.report is not None:record['verification']=exc.report
        records.append(record)
        if winner or (root/'WINNER.json').exists():stop_reason='first exact record frozen; stop';break
    freeze(root/'source-records.json',records)
    summary=dict(status='WINNER' if winner else 'ERROR' if any(r['status']=='ERROR' for r in records) else 'COMPLETE',
        sources_considered=len(records),unique_inputs=len(seen),applied_moves=sum(r.get('applied_moves',0) for r in records),
        best_derived_rank=min((r['final_rank'] for r in records if 'final_rank' in r),default=None),
        winner=winner,stop_reason=stop_reason,elapsed_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-start_cpu,
        scope='Complete inverse patterns only; no negative lower-bound, integer-lift, or novelty-at93 claim')
    freeze(root/'result.json',summary)
    freeze(root/'checksums.json',{str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob('*')) if path.is_file()})
    print(json.dumps(summary,sort_keys=True));return 2 if summary['status']=='ERROR' else 0


if __name__=='__main__':raise SystemExit(main())
