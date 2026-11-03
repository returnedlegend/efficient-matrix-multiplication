"""Size-guarded restartable k8..10 C3 local-SAT portfolio; skipped is not UNSAT."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import signal
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.cyclic_orbit_sat import nonfixed_orbits,solve_patch,validate_decode_global
from mmsearch.cyclic_orbit_large import (build_large_repair as build_repair,
    choose_large_neighbor_orbits as choose_neighbor_orbits)
from mmsearch.native_bridge import canonical_terms,term_set_sha256
from mmsearch.search import encode_candidate,is_cyclic,orbit_counts
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]


class StopCampaign(BaseException):
    pass


def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    temporary.write_bytes(json_bytes(value));temporary.replace(path)


def tuple_tree(value):
    return tuple(tuple_tree(item) for item in value) if isinstance(value,list) else value


def load_parents(inputs,seed_dirs,output):
    counts=Counter();paths=set()
    for path in inputs:
        path=Path(path).resolve()
        if not path.is_file():
            counts['missing_input']+=1
        else:
            paths.add(path)
    for directory in seed_dirs:
        directory=Path(directory).resolve()
        if not directory.is_dir():
            counts['missing_seed_dir']+=1
        else:
            paths.update(path.resolve() for path in directory.glob('*.json') if path.is_file())
    parents=[];seen=set()
    for path in sorted(paths):
        counts['files_scanned']+=1
        try:
            raw=path.read_bytes();candidate=read_json(raw)
            terms=canonical_terms(candidate)
            if candidate['dimension']!=5 or len(terms)!=95:
                counts['other_rank_or_dimension']+=1;continue
            if not is_cyclic(terms) or orbit_counts(terms)['fixed_cubes']!=2:
                counts['other_cyclic_or_cube_profile']+=1;continue
            canonical_sha=term_set_sha256(terms)
            if canonical_sha in seen:
                counts['duplicate_canonical_parent']+=1;continue
            report=verify_candidate(candidate,random_trials=0)
            normalized_report=verify_candidate(encode_candidate(terms,5),random_trials=0)
            if (not report['valid'] or report['exact_entries_checked']!=15625
                    or not normalized_report['valid']):
                counts['inexact_certificate']+=1;continue
        except (OSError,ValueError,KeyError,TypeError,IndexError):
            counts['unreadable_or_malformed']+=1;continue
        h=hashlib.sha256(raw).hexdigest();seen.add(canonical_sha)
        relative='parents/'+h+'.json';verification='parents/'+h+'.verification.json'
        freeze(output/relative,raw);freeze(output/verification,json_bytes(dict(original=report,canonical=normalized_report)))
        parents.append(dict(source_path=str(path),raw_sha256=h,canonical_sha256=canonical_sha,
                            frozen_path=relative,verification_path=verification,candidate=candidate))
        counts['verified_exact_cyclic95_two_fixed']+=1
    return parents,dict(counts)


def make_plan(parents,k_min,k_max,rng):
    plan=[]
    for index,parent in enumerate(parents):
        count=len(nonfixed_orbits(canonical_terms(parent['candidate'])))
        for k in range(k_min,min(k_max,count)+1):
            plan.extend([index,k,anchor] for anchor in range(count))
    rng.shuffle(plan)
    return plan


def cache_key(parent,indices):
    return parent['raw_sha256']+':'+','.join(map(str,sorted(indices)))


def run_portfolio(parents,output,*,seconds=600,patch_seconds=30,k_min=8,k_max=10,seed=0,
                  backend='cryptominisat',conflicts=500000,memory_mb=1536,koszul=False,resume=False,
                  max_variables=150000,max_clauses=600000,max_estimated_memory_mb=1024,
                  build_fn=None,solver_fn=None,clock=None,install_signals=True):
    """Internal engine also supports planted small-dimension test parents."""
    build_fn=build_fn or build_repair;solver_fn=solver_fn or solve_patch;clock=clock or time.monotonic
    if backend!='cryptominisat':
        raise ValueError('large-branch memory/formula guards require the native-XOR CryptoMiniSat backend')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    started=clock();deadline=started+seconds;rng=random.Random(seed)
    config=dict(patch_seconds=patch_seconds,k_min=k_min,k_max=k_max,seed=seed,backend=backend,
                conflicts=conflicts,memory_mb=memory_mb,koszul=koszul,max_variables=max_variables,
                max_clauses=max_clauses,max_estimated_memory_mb=max_estimated_memory_mb)
    if resume:
        state=read_json((output/'state.json').read_bytes())
        if state['config']!=config or state['parent_hashes']!=[p['raw_sha256'] for p in parents]:
            raise ValueError('resume configuration/parents differ from frozen state')
        rng.setstate(tuple_tree(state['rng']))
    else:
        state=dict(config=config,parent_hashes=[p['raw_sha256'] for p in parents],
                   plan=make_plan(parents,k_min,k_max,rng),cursor=0,seen=[],
                   counts={},attempts=0,full_problems_saved=0,rng=rng.getstate())
    seen=set(state['seen']);counts=Counter(state['counts']);last_save=clock()
    if resume and (output/'cache.jsonl').exists():
        for line in (output/'cache.jsonl').read_text().splitlines():
            try:
                committed=json.loads(line)
            except ValueError:
                continue
            seen.add(committed['cache_key'])
            state['attempts']=max(state['attempts'],committed['attempt'])
            state['cursor']=max(state['cursor'],committed['cursor'])
    if resume and (output/'events.jsonl').exists():
        replay_counts=Counter()
        for line in (output/'events.jsonl').read_text().splitlines():
            try:
                event=json.loads(line)
            except ValueError:
                continue
            seen.add(event['cache_key']);replay_counts[event['status']]+=1
            state['attempts']=max(state['attempts'],event['attempt'])
        counts.update({key:value-counts[key] for key,value in replay_counts.items() if value>counts[key]})
        state['full_problems_saved']=min(2,len(list((output/'problems').glob('first-*.json'))))
    stop=False;busy=False;old_handlers={}
    def interrupted(signum,frame):
        nonlocal stop
        stop=True
        if busy:
            raise StopCampaign
    if install_signals:
        for signum in (signal.SIGINT,signal.SIGTERM):
            old_handlers[signum]=signal.signal(signum,interrupted)
    def save_state(status):
        state.update(seen=sorted(seen),counts=dict(counts),rng=rng.getstate(),status=status)
        atomic_json(output/'state.json',state)
        atomic_json(output/'summary.json',dict(status=status,attempts=state['attempts'],
                    cached_patches=len(seen),plan_cursor=state['cursor'],plan_size=len(state['plan']),
                    counts=dict(counts),elapsed_this_run=clock()-started,
                    scope='Only selected frozen local neighborhoods; no global UNSAT claim.'))
    status='EXHAUSTED_LOCAL_PLAN'
    try:
        save_state('RUNNING')
        if (output/'WINNER.json').exists():
            status='SAT';return dict(status=status,attempts=state['attempts'],counts=dict(counts))
        while state['cursor']<len(state['plan']):
            if stop:
                status='STOPPED';break
            if deadline-clock()<=2:
                status='WALL_BUDGET';break
            parent_index,k,anchor=state['plan'][state['cursor']];state['cursor']+=1
            parent=parents[parent_index]
            terms=canonical_terms(parent['candidate'])
            indices=choose_neighbor_orbits(terms,k,seed=seed,anchor=anchor)
            key=cache_key(parent,indices)
            if key in seen:
                counts['duplicate_patch_skipped']+=1;continue
            seen.add(key);state['attempts']+=1;attempt=state['attempts']
            event=dict(attempt=attempt,parent_raw_sha256=parent['raw_sha256'],
                       parent_index=parent_index,orbit_indices=indices,k=k,anchor=anchor,cache_key=key)
            # Commit before encoding/solving, so a stale 30-second state file
            # cannot cause an unchanged UNKNOWN or interrupted patch to repeat.
            with (output/'cache.jsonl').open('a') as journal:
                journal.write(json.dumps(dict(cache_key=key,attempt=attempt,cursor=state['cursor']),sort_keys=True)+'\n')
            patch_started=clock();problem=None
            try:
                busy=True
                problem=build_fn(parent['candidate'],indices,koszul=koszul,max_variables=max_variables,
                                 max_clauses=max_clauses,max_estimated_memory_mb=max_estimated_memory_mb)
                busy=False
                metadata=problem['metadata'];payload=json_bytes(problem)
                event.update(problem_sha256=hashlib.sha256(payload).hexdigest(),
                             formula_sha256=metadata['formula_sha256'],shared_dimension=metadata['shared_dimension'],
                             flattening_ranks=metadata['flattening_ranks'],lower_bound=metadata['tensor_rank_lower_bound'],
                             nominal_product_cap=metadata['nominal_product_cap'],variables=problem['nv'],
                             cnf_clauses=len(problem['clauses']),native_xors=len(problem['xors']))
                if state['full_problems_saved']<2:
                    freeze(output/'problems'/f'first-{state["full_problems_saved"]:02d}.json',payload)
                    state['full_problems_saved']+=1
                atomic_json(output/'latest_problem.json',problem)
                event['encoding_estimate']=metadata['encoding_estimate']
                event['size_guard_limits']=metadata['size_guard_limits']
                if metadata.get('skipped_too_large'):
                    event.update(status='SKIPPED_TOO_LARGE',reason='; '.join(metadata['size_guard_reasons']))
                elif metadata['lower_bound_rejected']:
                    event.update(status='LOCAL_UNSAT_BOUND',reason='exact tensor-rank lower bound exceeds nominal product cap')
                elif stop or deadline-clock()<=2:
                    event.update(status='UNKNOWN',reason='cleanup reserve reached before solving')
                else:
                    budget=min(patch_seconds,deadline-clock()-2)
                    event['solver_budget_seconds']=budget
                    busy=True
                    solved=solver_fn(problem,seconds=budget,conflicts=conflicts,memory_mb=memory_mb,backend=backend)
                    busy=False
                    event.update(status='LOCAL_UNSAT' if solved['status']=='UNSAT' else solved['status'],
                                 solver=solved.get('solver'),solver_elapsed_seconds=solved.get('elapsed_seconds'),
                                 reason=solved.get('reason',solved.get('error')))
                    if solved['status']=='SAT':
                        candidate,report=validate_decode_global(problem,solved['model'])
                        event.update(actual_rank=len(candidate['terms']),independently_valid=report['valid'],
                                     exact_entries_checked=report['exact_entries_checked'])
                        name=f'SAT-{attempt:06d}'
                        freeze(output/'problems'/(name+'.json'),payload)
                        freeze(output/'sat'/(name+'.model.json'),json_bytes(solved['model']))
                        freeze(output/'sat'/(name+'.candidate.json'),json_bytes(candidate))
                        freeze(output/'sat'/(name+'.verification.json'),json_bytes(report))
                        if len(candidate['terms'])<=92:
                            freeze(output/'WINNER.json',json_bytes(candidate))
                            freeze(output/'WINNER.verification.json',json_bytes(report))
                            freeze(output/'WINNER.verify.py',(ROOT/'mmsearch/verify.py').read_bytes())
                            freeze(output/'WINNER.sha256',(hashlib.sha256(json_bytes(candidate)).hexdigest()+'  WINNER.json\n').encode())
                            status='SAT';stop=True
            except StopCampaign:
                busy=False;event.update(status='UNKNOWN',reason='campaign interrupted; solver child cleaned up')
                status='STOPPED';stop=True
            except Exception as exc:
                busy=False;event.update(status='ERROR',reason=f'{type(exc).__name__}: {exc}')
            event['elapsed_seconds']=clock()-patch_started
            counts[event['status']]+=1
            with (output/'events.jsonl').open('a') as log:
                log.write(json.dumps(event,sort_keys=True,allow_nan=False)+'\n')
            if clock()-last_save>=30 or stop:
                save_state(status if stop else 'RUNNING');last_save=clock()
            if stop:
                break
        return dict(status=status,attempts=state['attempts'],counts=dict(counts),cached_patches=len(seen))
    finally:
        busy=False;save_state(status)
        for signum,handler in old_handlers.items():
            signal.signal(signum,handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,action='append',default=[])
    parser.add_argument('--seed-dir',type=Path,action='append',default=[])
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=600)
    parser.add_argument('--patch-seconds',type=float,default=30)
    parser.add_argument('--k-min',type=int,default=8)
    parser.add_argument('--k-max',type=int,default=10)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--backend',choices=('CMS','cryptominisat'),default='CMS')
    parser.add_argument('--conflicts',type=int,default=500000)
    parser.add_argument('--memory-mb',type=int,default=1536)
    parser.add_argument('--max-variables',type=int,default=150000)
    parser.add_argument('--max-clauses',type=int,default=600000)
    parser.add_argument('--max-estimated-memory-mb',type=int,default=1024)
    parser.add_argument('--koszul',action='store_true')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if (not math.isfinite(args.seconds) or args.seconds<=2 or not math.isfinite(args.patch_seconds)
            or args.patch_seconds<=0 or not 8<=args.k_min<=args.k_max<=10
            or args.conflicts<1 or args.memory_mb<128 or args.max_variables<1
            or args.max_clauses<1 or not 128<=args.max_estimated_memory_mb<=args.memory_mb):
        parser.error('invalid limits; seconds must exceed two-second cleanup reserve')
    started=time.monotonic();output=args.output_dir.resolve()
    if args.resume:
        manifest=read_json((output/'manifest.json').read_bytes());parents=[]
        for name,expected in manifest['code_sha256'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
                raise ValueError(f'code changed since frozen campaign: {name}')
        for item in manifest['parents']:
            raw=(output/item['frozen_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['raw_sha256']:
                raise ValueError('frozen parent checksum changed')
            candidate=read_json(raw);report=verify_candidate(candidate,random_trials=0)
            if not report['valid'] or report['exact_entries_checked']!=15625:
                raise ValueError('frozen parent no longer passes exact verification')
            parents.append(dict(item,candidate=candidate))
    else:
        output.mkdir(parents=True,exist_ok=False)
        parents,counts=load_parents(args.input,args.seed_dir,output)
        names=['scripts/campaign_cyclic_orbit_sat_large.py','mmsearch/cyclic_orbit_large.py','mmsearch/cyclic_orbit_sat.py','mmsearch/compact_sat.py',
               'mmsearch/sat.py','mmsearch/xor_sat.py','mmsearch/search.py','mmsearch/native_bridge.py',
               'mmsearch/sat_neighborhoods.py','mmsearch/koszul.py','mmsearch/verify.py','scripts/freeze_campaign_dictionary.py']
        code={name:(ROOT/name).read_bytes() for name in names}
        manifest=dict(parents=[{key:value for key,value in parent.items() if key!='candidate'} for parent in parents],
                      selection_counts=counts,code_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()},
                      scope='Only frozen exact cyclic95/two-fixed-cube parents; skipped files are not claimed exact.')
        for name,raw in code.items():
            freeze(output/'code'/name,raw)
        freeze(output/'manifest.json',json_bytes(manifest))
    if not parents:
        atomic_json(output/'summary.json',dict(status='NO_VERIFIED_PARENTS',selection_counts=manifest['selection_counts']))
        print(json.dumps(dict(status='NO_VERIFIED_PARENTS')));return 2
    remaining=args.seconds-(time.monotonic()-started)
    result=run_portfolio(parents,output,seconds=max(0,remaining),patch_seconds=args.patch_seconds,
                         k_min=args.k_min,k_max=args.k_max,seed=args.seed,
                         backend='cryptominisat' if args.backend=='CMS' else args.backend,
                         conflicts=args.conflicts,memory_mb=args.memory_mb,koszul=args.koszul,resume=args.resume,
                         max_variables=args.max_variables,max_clauses=args.max_clauses,
                         max_estimated_memory_mb=args.max_estimated_memory_mb)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
