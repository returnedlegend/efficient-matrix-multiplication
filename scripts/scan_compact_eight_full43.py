"""Restartable full eight-term-union Koszul scan with compact exact bound records."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.compact_eight43 import (bits,expand_core,opposite_pair_ranks,packed_tensor,
    replace_and_verify,transfer_known_products)
from mmsearch.compact_sat import compress_residual
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.verify import verify_candidate
from mmsearch.recombine import digest
from scripts.verify_record42_independent import verify_bytes


def cpu():
    own=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime+own.ru_stime+children.ru_utime+children.ru_stime


def atomic(path,value):
    temporary=Path(str(path)+'.tmp')
    with temporary.open('w') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    temporary.replace(path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--filter-binary',type=Path,required=True);p.add_argument('--sample-size',type=int);p.add_argument('--counts-json',type=Path)
    p.add_argument('--max-samples-per-pass',type=int,default=981476);p.add_argument('--cpu-seconds',type=float,default=60)
    p.add_argument('--batch-size',type=int,default=200);p.add_argument('--restart',action='store_true')
    a=p.parse_args(argv)
    if (a.sample_size is not None and not 1<=a.sample_size<=981476) or not 1<=a.max_samples_per_pass<=981476 or not 0<a.cpu_seconds<=60 or not 1<=a.batch_size<=500:
        p.error('scan<=981476, passCPU<=60 and bounded batches required')
    started=cpu();wall=time.monotonic();out=a.output_dir;out.mkdir(parents=True,exist_ok=a.restart)
    counts=json.loads(a.counts_json.read_bytes()) if a.counts_json else [244374,248940,256489,231673]
    if len(counts)!=4 or any(type(n) is not int or n<1 for n in counts) or sum(counts)>981476:raise ValueError('invalid four source counts')
    total=sum(counts);a.sample_size=total if a.sample_size is None else a.sample_size
    if a.sample_size>total:raise ValueError('sample exceeds input total')
    sources=[];terms=[];tensors=[];inputs={}
    for s,count in enumerate(counts):
        path=a.inventory/f'source-{s}.json';raw=path.read_bytes();candidate=json.loads(raw);report=verify_candidate(candidate,random_trials=0)
        if not report['valid'] or report['rank']!=93 or report['exact_entries_checked']!=15625:raise AssertionError('source control invalid')
        masks=factor_masks(candidate);ranks=opposite_pair_ranks(masks)
        if ranks!=[93,93,93]:raise AssertionError('factor-span equality precondition not established')
        union=a.inventory/f'unions.source-{s}.k8.txt'
        inputs[str(s)]=dict(source_sha256=hashlib.sha256(raw).hexdigest(),union_sha256=hashlib.sha256(union.read_bytes()).hexdigest(),count=count)
        sources.append(candidate);terms.append(masks);tensors.append([packed_tensor(t) for t in masks])
    old_cases=[]
    for case in json.loads((a.inventory/'portfolio-summary.json').read_text())['cases']:
        data=json.loads((a.inventory/'portfolio'/case['id']/'core.json').read_text())
        old_source=json.loads((a.inventory/f'source-{case["source"]}.json').read_text())
        old_masks=factor_masks(old_source);products=[old_masks[i] for i in data['source_indices']]
        ambient=0
        for product in products:ambient^=packed_tensor(product)
        if ambient!=expand_core(data['core'],data['shape'],data['image_bases']):
            raise AssertionError('old known-product control and core differ')
        old_cases.append(dict(id=case['id'],data=data,products=products,ambient=ambient))
    old_shapes={tuple(sorted(item['data']['shape'])) for item in old_cases}
    config=dict(inputs=inputs,inventory_manifest_sha256=hashlib.sha256((a.inventory/'manifest.json').read_bytes()).hexdigest(),
        total_union_count=total,sample_size=a.sample_size,sampling='Every global ordinal in input source/file order when sample_size=total; custom smaller sizes are explicit control subsets',
        filter_sha256=hashlib.sha256(a.filter_binary.read_bytes()).hexdigest(),
        code_sha256={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in ['scripts/scan_compact_eight_full43.py','mmsearch/compact_eight43.py']},
        arithmetic='ExactGF2 nativep1 Koszul in all3modes, independently checked in Python controls; no SAT call')
    config_hash=digest(config);config_path=out/'config.json'
    if a.restart:
        if json.loads(config_path.read_text())!=config:raise ValueError('sample input/native/code hash changed')
        state=json.loads((out/'cursor.json').read_text())
        if state['config_sha256']!=config_hash:raise ValueError('sampler cursor config mismatch')
    else:
        config_path.write_text(json.dumps(config,indent=2,sort_keys=True)+'\n');config_path.chmod(0o444)
        state=dict(config_sha256=config_hash,next_sample=0,input_source=0,input_next_line=0,input_byte_offset=0,
            committed_log_bytes=0,committed_bounds_bytes=0,processed=0,passing=0,rejected=0,source_counts={},lower_bound_counts={})
        atomic(out/'cursor.json',state)
    if (out/'WINNER.json').exists():
        independent=verify_bytes((out/'WINNER.json').read_bytes())
        proof=json.loads((out/'WINNER.proof.json').read_bytes())
        if not independent['record_eligible'] or any(hashlib.sha256((out/name).read_bytes()).hexdigest()!=h for name,h in proof['files'].items()):raise ValueError('corrupt prior winner/proof')
        print(json.dumps(dict(status='VERIFIED_TARGET',terminal_resume_guard=True)));return 0
    if (out/'ERROR.json').exists() or state.get('last_status')=='ERROR':
        print(json.dumps(dict(status='ERROR',terminal_resume_guard=True)));return 2
    if state.get('last_status')=='VERIFIED_TARGET':raise ValueError('winner cursor is missing marker')
    records=out/'sample.jsonl';records.touch(exist_ok=True)
    with records.open('r+b') as stream:stream.truncate(state['committed_log_bytes'])
    bound_records=out/'all-bounds.bin';bound_records.touch(exist_ok=True)
    if state['committed_bounds_bytes']!=7*state['next_sample']:raise ValueError('bound-record cursor size mismatch')
    with bound_records.open('r+b') as stream:stream.truncate(state['committed_bounds_bytes'])
    header='4\n'+''.join(' '.join(map(str,t))+'\n' for source in terms for t in source)
    cumulative=[0]
    for n in counts:cumulative.append(cumulative[-1]+n)
    current=state['input_source'];line=state['input_next_line'];stream=(a.inventory/f'unions.source-{current}.k8.txt').open('rb')
    stream.seek(state['input_byte_offset']);stop=False
    def stopped(sig,frame):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
    local_processed=0
    def child_limits():
        for kind,soft,hard in [(resource.RLIMIT_CPU,2,3),(resource.RLIMIT_AS,512*1024**2,512*1024**2)]:
            _,inherited=resource.getrlimit(kind);effective=hard if inherited==resource.RLIM_INFINITY else min(hard,inherited)
            resource.setrlimit(kind,(min(soft,effective),effective))
    try:
        while state['next_sample']<a.sample_size and local_processed<a.max_samples_per_pass and not stop:
            if cpu()-started>=a.cpu_seconds-1:break
            batch=[]
            number=min(a.batch_size,a.sample_size-state['next_sample'],a.max_samples_per_pass-local_processed)
            for j in range(state['next_sample'],state['next_sample']+number):
                ordinal=j*total//a.sample_size
                while ordinal>=cumulative[current+1]:
                    stream.close();current+=1;line=0;stream=(a.inventory/f'unions.source-{current}.k8.txt').open('rb')
                target=ordinal-cumulative[current]
                while line<=target:
                    raw=stream.readline()
                    if not raw:raise ValueError('union stream ended before declared count')
                    line+=1
                lo,hi=map(int,raw.split());mask=lo|(hi<<64)
                if mask.bit_count()!=8 or mask>>93:raise ValueError('invalid frozen8term mask')
                batch.append((current,ordinal,lo,hi))
            request=header+str(len(batch))+'\n'+''.join(' '.join(map(str,row))+'\n' for row in batch)
            process=subprocess.run([str(a.filter_binary.resolve())],input=request,text=True,capture_output=True,
                timeout=10,preexec_fn=child_limits)
            if process.returncode:raise RuntimeError('native preprocessor ERROR: '+process.stderr[:1000])
            lines=process.stdout.splitlines()
            if len(lines)!=len(batch):raise AssertionError('native output count mismatch')
            parsed=[]
            for j,(expected,output) in enumerate(zip(batch,lines),state['next_sample']):
                fields=output.split();identity=tuple(map(int,fields[:4]))
                if identity!=expected:raise AssertionError('native mask/source binding mismatch')
                shape=list(map(int,fields[4:7]));flats=list(map(int,fields[7:10]));ranks=list(map(int,fields[10:13]));lower=int(fields[13]);core=int(fields[14],16)
                if flats!=shape:raise AssertionError('actual image dimensions disagree with checked pair-independent source')
                source,ordinal,lo,hi=expected;indices=list(bits(lo|(hi<<64)));ambient=0
                if lower<=7 or tuple(sorted(shape)) in old_shapes:
                    for i in indices:ambient^=tensors[source][i]
                # Exact image dimensions exclude most old controls immediately.
                # An actual match is a constructive upper bound, never a
                # transferred old6->5 negative for the new8->7 question.
                mapping_unknown=False
                if tuple(sorted(shape)) in old_shapes:
                    actual_bases,actual_core,actual_shape,_=compress_residual(sources[source],indices)
                    new_bases=[basis.vectors for basis in actual_bases]
                    for known in old_cases:
                        if tuple(sorted(known['data']['shape']))!=tuple(sorted(actual_shape)):continue
                        transfer=None
                        if known['ambient']==ambient:
                            transfer=dict(products=known['products'],method='identical exact ambient tensor')
                        else:
                            try:
                                transfer=transfer_known_products(known['data']['core'],known['data']['shape'],
                                    known['data']['image_bases'],known['products'],actual_core,actual_shape,new_bases)
                            except ValueError:
                                mapping_unknown=True;continue
                        if transfer is None:continue
                        candidate,verification=replace_and_verify(sources[source],indices,transfer['products'],dict(
                            method='constructive known-small-tensor transfer',known_case=known['id']))
                        independent=verify_bytes(json.dumps(candidate,sort_keys=True).encode())
                        if not independent['record_eligible'] or verification['rank']>91 or verification['exact_entries_checked']!=15625:
                            raise AssertionError('known6 match failed full verified<=91 gate')
                        atomic(out/'WINNER.verification.json',verification)
                        atomic(out/'WINNER.independent.verification.json',independent)
                        atomic(out/'WINNER.match.json',dict(source=source,indices=indices,old_case=known['id'],transfer=transfer))
                        atomic(out/'WINNER.proof.json',dict(files={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['WINNER.verification.json','WINNER.independent.verification.json','WINNER.match.json']}))
                        atomic(out/'WINNER.json',candidate)
                        for path in out.glob('WINNER*'):path.chmod(0o444)
                        state.update(next_sample=j+1,last_status='VERIFIED_TARGET');atomic(out/'cursor.json',state)
                        print(json.dumps(dict(status='VERIFIED_TARGET',rank=verification['rank'],target_SAT_queries=0)),flush=True)
                        return 0
                row=dict(sample_index=j,global_union_ordinal=ordinal,source=source,indices=indices,mask_lo=lo,mask_hi=hi,
                    shape=shape,flattening_ranks=flats,koszul_p1_matrix_ranks=ranks,tensor_rank_lower_bound=lower,
                    target_local_products=7,status='UNKNOWN_KNOWN_CORE_MAP' if mapping_unknown else 'KOSZUL_REJECT' if lower>7 else 'BOUND_PASSED_NOT_EXISTENCE',
                    factor_core_hex=hex(core),residual_sha256=hashlib.sha256(ambient.to_bytes(1954,'little')).hexdigest(),native_cache_hit=bool(int(fields[15])))
                parsed.append(row)
            with records.open('ab') as log:
                for row in parsed:
                    if row['tensor_rank_lower_bound']<=7 or row['status']=='UNKNOWN_KNOWN_CORE_MAP':log.write((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode())
                log.flush();os.fsync(log.fileno());position=log.tell()
            with bound_records.open('ab') as binary:
                for row in parsed:binary.write(bytes(row['shape']+row['koszul_p1_matrix_ranks']+[row['tensor_rank_lower_bound']]))
                binary.flush();os.fsync(binary.fileno());bound_position=binary.tell()
            state['next_sample']+=len(parsed);state['processed']+=len(parsed);local_processed+=len(parsed)
            state['passing']+=sum(row['tensor_rank_lower_bound']<=7 for row in parsed)
            state['rejected']+=sum(row['tensor_rank_lower_bound']>7 for row in parsed)
            source_counts=Counter(state['source_counts']);lower_counts=Counter(state['lower_bound_counts'])
            source_counts.update(str(row['source']) for row in parsed);lower_counts.update(str(row['tensor_rank_lower_bound']) for row in parsed)
            state.update(input_source=current,input_next_line=line,input_byte_offset=stream.tell(),committed_log_bytes=position,committed_bounds_bytes=bound_position,
                source_counts=dict(source_counts),lower_bound_counts=dict(lower_counts),last_pass_cpu_seconds=cpu()-started,
                last_pass_wall_seconds=time.monotonic()-wall)
            atomic(out/'cursor.json',state)
    except Exception as error:
        atomic(out/'ERROR.json',dict(status='ERROR',error_type=type(error).__name__,error=str(error)))
        state['last_status']='ERROR';atomic(out/'cursor.json',state)
        print(json.dumps(dict(status='ERROR',error_type=type(error).__name__,error=str(error))),flush=True)
        return 2
    finally:stream.close()
    report=dict(status='FULL_SCAN_COMPLETE' if state['next_sample']==a.sample_size else 'CHECKPOINTED_PARTIAL_SCAN',
        target_SAT_queries=0,processed_this_pass=local_processed,total_sample_processed=state['processed'],
        passing=state['passing'],rejected=state['rejected'],pass_fraction=state['passing']/max(1,state['processed']),
        full_union_count=total,unsampled_unions=total-state['processed'],sample_size=a.sample_size,
        cpu_seconds_this_pass=cpu()-started,wall_seconds=time.monotonic()-wall,
        rough_full_p1_CPU_seconds=(cpu()-started)*total/local_processed if local_processed else None,
        estimate_scope='Exact preprocessing of the declared input family; complete only at the terminal cursor. Bound records are7bytes/ordinal: shape3,p1ranks3,lower1.',
        config_sha256=config_hash,cursor=state)
    number=len(list(out.glob('report-pass*.json')));path=out/f'report-pass{number:03d}.json'
    path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');path.chmod(0o444)
    print(json.dumps({k:v for k,v in report.items() if k!='cursor'}),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
