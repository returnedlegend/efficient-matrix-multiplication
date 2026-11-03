"""Catalogue observed3D palettes, then freeze a small bounded-decoder sample."""
from collections import Counter
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.observed_plane42 import validate_active_certificate
from mmsearch.observed_rank342 import observed_space_plan,prepare_space
from mmsearch.free_factor_sat import decode_vectors
from mmsearch.recombine import digest
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--per-k-sample',type=int,default=2);p.add_argument('--seed',type=int,default=424701)
    args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);rng=random.Random(args.seed);start=time.monotonic()
    inventory=[];sources=[];selected=[]
    for directory in sorted((args.source_dir/'cases').iterdir()):
        if not directory.is_dir():continue
        system_raw=(directory/'system.json').read_bytes();system=read_json(system_raw);certificate=read_json((directory/'active-certificate.json').read_bytes())
        validate_active_certificate(system,certificate)
        report=verify_candidate(decode_vectors(system,system['baseline_vectors']),random_trials=0)
        if not certificate['independent'] or certificate['rank']!=93 or not report['valid'] or report['rank']!=93 or report['exact_entries_checked']!=15625:
            raise ValueError('exact independent active93 source required')
        source_id=directory.name;freeze(out/'sources'/source_id/'system.json',system_raw)
        freeze(out/'sources'/source_id/'active-certificate.json',json_bytes(certificate));freeze(out/'sources'/source_id/'baseline.verification.json',json_bytes(report))
        plan=observed_space_plan(system);raw=json_bytes(plan);compressed=gzip.compress(raw,compresslevel=1,mtime=0)
        freeze(out/'catalogs'/(source_id+'.json.gz'),compressed)
        counts=Counter(item['k'] for item in plan);sample=[]
        for k in (6,5,4):
            indices=[i for i,item in enumerate(plan) if item['k']==k]
            sample.extend(rng.sample(indices,min(len(indices),args.per_k_sample)))
        for ordinal in sample:
            item=plan[ordinal];q=prepare_space(system,item['basis_values'])
            if q['target_rank']!=3 or q['k']!=item['k']:raise AssertionError('observed-space target-rank/plan mismatch')
            case_id=source_id+'-'+digest(item['space'])[:16];path=out/'quotients'/(case_id+'.json.gz')
            freeze(path,gzip.compress(json_bytes(q),compresslevel=1,mtime=0))
            selected.append(dict(id=case_id,source_id=source_id,space=item['space'],basis_values=item['basis_values'],observed_generators=item['observed_generators'],
                k=item['k'],weight_bound=q['weight_bound'],target_rank=3,full_case_supported=q['weight_bound']<=5,
                quotient=str(path.relative_to(out)),quotient_sha256=q['quotient_sha256'],full_catalog_ordinal=ordinal,
                source_system_sha256=digest(system)))
        inventory.append(dict(source_id=source_id,system_sha256=digest(system),raw_system_sha256=hashlib.sha256(system_raw).hexdigest(),
            pair_count=len(system['pairs']),observed_values=len(set(system['baseline_vectors'])-{0}),active_rank=93,
            observed_space_catalogued=len(plan),k_histogram=dict(counts),cheap_rank_bound_closed_k3=counts[3],
            necessary_rank_proof='Active columns independent and observed generators have rank3, so target quotient rank3; k3/budget2 is impossible.',
            unsupported_nonclosed_budget6_or_more=sum(count for k,count in counts.items() if k>=7),
            sampled_cases=len(sample),catalog_content_sha256=digest(plan),catalog_compressed_sha256=hashlib.sha256(compressed).hexdigest(),
            decoder_queries=0))
        sources.append(source_id)
    selected.sort(key=lambda case:(-case['k'],case['source_id'],case['id']))
    freeze(out/'cases.json',json_bytes(selected));freeze(out/'CATALOG-METRICS.json',json_bytes(inventory))
    code=[]
    for name in ('mmsearch','scripts'):code.extend(sorted((ROOT/name).rglob('*.py')))
    code.append(ROOT/'tests/test_observed_rank342.py');closure={}
    for path in code:
        name=str(path.relative_to(ROOT));raw=path.read_bytes();freeze(out/'code'/name,raw);closure[name]=hashlib.sha256(raw).hexdigest()
    freeze(out/'code/tests/__init__.py',b'');closure['tests/__init__.py']=hashlib.sha256(b'').hexdigest();freeze(out/'launch-closure.json',json_bytes(closure))
    bindings={str(path.relative_to(out)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.rglob('*')) if path.is_file()}
    freeze(out/'integrity.json',json_bytes(bindings))
    command=[sys.executable,'-B',str(out/'code/scripts/verify_observed_rank342_ready.py'),'--prepared-dir',str(out)]
    done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=30)
    if done.returncode:raise ValueError(done.stderr)
    print(done.stdout);print(json.dumps(dict(status='PREPARED',sources=len(sources),sampled_cases=len(selected),
        source_catalogued=sum(item['observed_space_catalogued'] for item in inventory),target_decoder_queries=0,elapsed_seconds=time.monotonic()-start)))
    return 0


if __name__=='__main__':raise SystemExit(main())
