#!/usr/bin/env python3
"""Tiny schoolbook-drop-one repair landscape only; no production input option."""
import argparse
import itertools
import json
import os
from pathlib import Path
import resource
import sys
import time
REPO=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True;sys.path.insert(0,str(REPO))
from mmsearch.binary_small_slot_repair7 import repair_slots,propose_slot_sets
from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import atom_from_term


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
    os.sched_setaffinity(0,{1})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    a.outdir.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    exact=[atom_from_term(t,2) for t in naive_candidate(2)['terms']]
    core=[sum(((u>>i)&1)*((v>>j)&1)*((w>>k)&1) for u,v,w in exact)%2 for i in range(4) for j in range(4) for k in range(4)]
    approx=exact[1:];results=[]
    for size in (3,4,6):
        for slots in itertools.combinations(range(7),size):
            if time.monotonic()-started>=55:break
            result=repair_slots(core,[4,4,4],approx,slots,timeout_seconds=2)
            results.append(result)
    counts={}
    for r in results:counts.setdefault(str(len(r['selected_slots'])),{}).setdefault(r['status'],0);counts[str(len(r['selected_slots']))][r['status']]+=1
    summary=dict(status='KNOWN_N2_TINY_SLOT_LANDSCAPE',source_products=8,approximation_slots=7,
        original_missing_source_index=0,initial_loss=1,calls=len(results),counts_by_selected_slots=counts,
        elapsed_seconds=time.monotonic()-started,cpu_affinity=sorted(os.sched_getaffinity(0)),nice=os.getpriority(os.PRIO_PROCESS,0),
        address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],publication_eligible=False,
        production_n5_slot_calls=0,no_new_matrix_multiplication_claim=True)
    for name,value in [('summary.json',summary),('results.json',results),('input.json',dict(core=core,shape=[4,4,4],factors=approx))]:
        (a.outdir/name).write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(summary,sort_keys=True))
if __name__=='__main__':main()
