#!/usr/bin/env python3
"""Synthetic tiny SAT only: compare fork/spawn under a256MiB child cap."""
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'.xor-deps')]
from mmsearch import local_eliminated42sat as lifecycle
from mmsearch.two_color_affine_sat42 import build_coupled_problem,solve
import pycryptosat  # Match full regression: native extension already loaded in parent.


def memory():
    fields={}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmSize:','VmRSS:')):key,value=line.split(':',1);fields[key+'_kib']=int(value.split()[0])
    return fields


def main():
    problem=build_coupled_problem([0,0],[],1,(0,0,1));clean=solve(problem,seconds=2,memory_mb=256)
    assert clean['status']=='SAT';before=memory();ballast=bytearray(300*1024**2);inflated=memory();fork=solve(problem,seconds=2,memory_mb=256)
    original=lifecycle.mp.get_context
    with patch.object(lifecycle.mp,'get_context',lambda method:original('spawn')):fresh=solve(problem,seconds=2,memory_mb=256)
    report=dict(status='DIAGNOSIS_CONFIRMED' if fork['status']=='ERROR' and fork['worker_exitcode']==-6 and fresh['status']=='SAT' else 'DIAGNOSIS_NOT_CONFIRMED',clean_status=clean['status'],parent_before=before,parent_inflated=inflated,child_limit_mib=256,
        fork={k:fork[k] for k in ['status','worker_exitcode','worker_reaped','error'] if k in fork},spawn={k:fresh[k] for k in ['status','worker_exitcode','worker_reaped','solver_stats'] if k in fresh},
        formula_sha256=problem['metadata']['formula_sha256'],parent_ballast_bytes=len(ballast),production_n5_queries=0,lifecycle_sha256=hashlib.sha256((ROOT/'mmsearch/local_eliminated42sat.py').read_bytes()).hexdigest())
    out=ROOT/'artifacts/marathon7_20261103T122417Z/two-color-fork-heap-diagnostic-v1.json';out.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps(report,sort_keys=True))


if __name__=='__main__':main()
