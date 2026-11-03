"""Freeze a short kernel dictionary plus a verified independent wide complement."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import decode_checked,pair_column
from mmsearch.free_factor_kernel_wide import modal_admissibility,native_input,validate_circuit
from mmsearch.sat_neighborhoods import gf2_rank
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-prepared',type=Path,required=True)
    parser.add_argument('--complement',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=116593)
    args=parser.parse_args();started=time.monotonic()
    base=args.base_prepared.resolve();complement=args.complement.resolve();out=args.outdir.resolve()
    system=read_json((base/'system.json').read_bytes());baseline,report=decode_checked(system,system['baseline_vectors'])
    if system['metadata']['dimension']!=5 or report['rank']!=93 or report['exact_entries_checked']!=15625:
        raise ValueError('wide preparation requires exact5x5 baseline93')
    short=read_json((base/'circuits.json').read_bytes());extra=read_json((complement/'circuits.json').read_bytes())
    combined=read_json((complement/'combined-circuits.json').read_bytes())
    if combined!=short+extra:raise ValueError('combined circuit order differs from source prefix/complement')
    columns=[pair_column(pair,25) for pair in system['pairs']]
    for circuit in combined:validate_circuit(columns,circuit['support'])
    span=gf2_rank([sum(1<<g for g in c['support']) for c in combined])
    base_span=gf2_rank([sum(1<<g for g in c['support']) for c in short])
    if span!=system['metadata']['linear_nullity'] or span-base_span!=len(extra):
        raise ValueError('wide complement does not independently complete the full linear kernel')
    admissibility=modal_admissibility(system['baseline_vectors'],extra)
    provenance=dict(read_json((base/'preparation.json').read_bytes())['provenance'],
                    seed=args.seed,base_prepared=str(base),wide_complement=str(complement))
    counts=Counter(c['class_id'] for c in combined)
    summary=dict(pair_count=len(columns),baseline_active=report['rank'],retained={str(k):v for k,v in counts.items()},
                 circuit_count=len(combined),short_circuits=len(short),independent_wide_complement=len(extra),
                 linear_rank=system['metadata']['linear_rank'],linear_nullity=system['metadata']['linear_nullity'],
                 circuit_span_rank=span,base_span_rank=base_span,orientation=system['metadata']['orientation'],
                 max_support=max(len(c['support']) for c in combined),
                 scope='Full kernel linear span only; bounded-active/headroom graph connectivity is not proved.')
    out.mkdir(parents=True,exist_ok=False)
    artifacts={'system.json':(base/'system.json').read_bytes(),'system.audit.json':(base/'system.audit.json').read_bytes(),
               'circuits.json':json_bytes(combined),'kernel_input.txt':native_input(system,combined)}
    for name,raw in artifacts.items():freeze(out/name,raw)
    freeze(out/'modal-admissibility.json',json_bytes(admissibility))
    freeze(out/'baseline.verification.json',json_bytes(report))
    sources={}
    for name in ('summary.json','proofs.json','final-span.audit.json','checksums.json'):
        raw=(complement/name).read_bytes();freeze(out/'complement-proof'/name,raw)
        sources[str(complement/name)]=hashlib.sha256(raw).hexdigest()
    for name in ('dictionary.json','baseline.json'):freeze(out/'inputs'/name,(base/'inputs'/name).read_bytes())
    names=['scripts/prepare_kernel_wide.py','scripts/campaign_kernel_walk_wide.py','mmsearch/free_factor_kernel_wide.py',
           'native/free_factor_kernel_worker_wide.cpp','scripts/campaign_kernel_walk_v2.py','mmsearch/free_factor_kernel.py',
           'mmsearch/free_factor_sat.py','mmsearch/sat_neighborhoods.py','mmsearch/verify.py']
    code={name:(ROOT/name).read_bytes() for name in names}
    for name,raw in code.items():freeze(out/'code'/name,raw)
    preparation=dict(provenance=provenance,circuits=summary,source_proof_sha256=sources,
                      input_sha256=hashlib.sha256(artifacts['kernel_input.txt']).hexdigest(),
                      artifacts_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in artifacts.items()},
                      code_sha256={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()},
                      baseline_active_groups=[g for g,w in enumerate(system['baseline_vectors']) if w],
                      preparation_seconds=time.monotonic()-started)
    freeze(out/'preparation.json',json_bytes(preparation))
    print(dict(status='PREPARED',circuits=summary,initial_modal_admissible_counts=admissibility['counts'],
               preparation_seconds=time.monotonic()-started))


if __name__=='__main__':main()
