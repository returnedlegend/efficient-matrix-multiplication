"""Prepare or solve one exact C3 orbit-local repair of a cyclic rank95 seed."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.cyclic_orbit_sat import (build_repair,choose_neighbor_orbits,solve_patch,
                                     validate_decode_global)
from mmsearch.native_bridge import canonical_terms
from mmsearch.search import orbit_counts
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--k',type=int,choices=range(2,8),default=3)
    parser.add_argument('--orbit-indices',help='comma-separated indices in sorted nonfixed orbit representatives')
    parser.add_argument('--anchor',type=int)
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--seconds',type=float,default=10)
    parser.add_argument('--conflicts',type=int,default=100000)
    parser.add_argument('--memory-mb',type=int,default=1536)
    parser.add_argument('--backend',choices=('auto','cryptominisat','cadical'),default='auto')
    parser.add_argument('--koszul',action='store_true')
    parser.add_argument('--no-symmetry',action='store_true')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds<=0 or args.conflicts<1 or args.memory_mb<128:
        parser.error('positive finite seconds/conflicts and memory-mb >=128 required')
    started=time.monotonic();raw=args.input.read_bytes();candidate=read_json(raw)
    terms=canonical_terms(candidate)
    indices=([int(value) for value in args.orbit_indices.split(',')] if args.orbit_indices else
             choose_neighbor_orbits(terms,args.k,seed=args.seed,anchor=args.anchor))
    problem=build_repair(candidate,indices,symmetry=not args.no_symmetry,koszul=args.koszul)
    root=args.output_dir.resolve();root.mkdir(parents=True,exist_ok=False)
    code_paths=[Path(__file__).resolve(),Path(__file__).resolve().parents[1]/'mmsearch/cyclic_orbit_sat.py',
                Path(__file__).resolve().parents[1]/'mmsearch/compact_sat.py',
                Path(__file__).resolve().parents[1]/'mmsearch/sat.py',
                Path(__file__).resolve().parents[1]/'mmsearch/xor_sat.py',
                Path(__file__).resolve().parents[1]/'mmsearch/search.py',
                Path(__file__).resolve().parents[1]/'mmsearch/native_bridge.py',
                Path(__file__).resolve().parents[1]/'mmsearch/sat_neighborhoods.py',
                Path(__file__).resolve().parents[1]/'mmsearch/koszul.py',
                Path(__file__).resolve().parents[1]/'mmsearch/verify.py',
                Path(__file__).resolve().parents[1]/'scripts/freeze_campaign_dictionary.py']
    code={str(path.relative_to(Path(__file__).resolve().parents[1])):path.read_bytes() for path in code_paths}
    manifest=dict(source_path=str(args.input.resolve()),source_sha256=hashlib.sha256(raw).hexdigest(),
                  code_sha256={name:hashlib.sha256(data).hexdigest() for name,data in code.items()},
                  orbit_indices=indices,seconds_budget=args.seconds,conflict_budget=args.conflicts,
                  memory_mb=args.memory_mb,backend=args.backend,prepare_only=args.prepare_only)
    artifacts={'input.json':raw,'problem.json':json_bytes(problem),'manifest.json':json_bytes(manifest)}
    artifacts.update({'code/'+name:data for name,data in code.items()})
    remaining=args.seconds-(time.monotonic()-started)
    if args.prepare_only:
        result=dict(status='PREPARED',lower_bound_rejected=problem['metadata']['lower_bound_rejected'])
    elif remaining<=0:
        result=dict(status='UNKNOWN',reason='preparation exhausted total wall budget')
    else:
        result=solve_patch(problem,seconds=remaining,conflicts=args.conflicts,memory_mb=args.memory_mb,backend=args.backend)
        if result['status']=='SAT':
            full,report=validate_decode_global(problem,result['model'])
            artifacts['candidate.json']=json_bytes(full)
            artifacts['verification.json']=json_bytes(report)
            artifacts['verify.py']=code['mmsearch/verify.py']
            result.update(global_essential_rank=len(full['terms']),global_profile=orbit_counts(canonical_terms(full)),
                          exact_entries_checked=report['exact_entries_checked'],independently_valid=report['valid'])
            if len(full['terms'])<=92:
                artifacts['WINNER.json']=json_bytes(full)
                artifacts['WINNER.verification.json']=json_bytes(report)
    result.update(elapsed_seconds=time.monotonic()-started,problem=problem['metadata'])
    artifacts['result.json']=json_bytes(result)
    checksums={}
    for name,data in artifacts.items():
        freeze(root/name,data);checksums[name]=hashlib.sha256(data).hexdigest()
    freeze(root/'checksums.json',json_bytes(checksums))
    print(json.dumps({key:value for key,value in result.items() if key not in ('model','problem','replacement_terms')},sort_keys=True))
    return 2 if result['status']=='ERROR' else 0


if __name__=='__main__':
    raise SystemExit(main())
