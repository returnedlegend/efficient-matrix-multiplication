#!/usr/bin/env python3
"""Disabled-by-default v2 atom-extension preparation. No search or SAT mode."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.tensor_code7 import strict_load
from mmsearch.tensor_code7_extension import (PREPARED_SCHEMA,authenticate_base,build_extension,
    raw_sha,validate_extension_prepared)
from scripts.tensor_code7 import Guard,Stop,runtime,write_json

CODE = ("mmsearch/tensor_code7_extension.py","scripts/tensor_code7_extension.py",
        "tests/test_tensor_code7_extension.py","research/tensor_code7_extension.md",
        "scripts/tensor_code7_extension.schema.json")


def code_hashes():
    names=set(CODE)
    for module in tuple(sys.modules.values()):
        name=getattr(module,"__file__",None)
        if name:
            path=Path(name).resolve()
            if path.is_relative_to(REPO) and path.suffix==".py" and path.relative_to(REPO).parts[0] in ("mmsearch","scripts"):
                names.add(str(path.relative_to(REPO)))
    return {name:raw_sha((REPO/name).read_bytes()) for name in sorted(names)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-prepared',type=Path)
    p.add_argument('--base-sha256')
    p.add_argument('--witnesses',type=Path)
    p.add_argument('--witnesses-sha256')
    p.add_argument('--source-manifest',type=Path)
    p.add_argument('--source-manifest-sha256')
    p.add_argument('--approved-root',type=Path)
    p.add_argument('--campaign-dir',type=Path)
    p.add_argument('--campaign-sha256')
    p.add_argument('--guard-state',type=Path)
    p.add_argument('--hard-utc',default='2026-11-03T19:24:17Z')
    p.add_argument('--seconds',type=float,default=120)
    p.add_argument('--outdir',type=Path)
    p.add_argument('--authorize-extension-preparation',action='store_true')
    p.add_argument('--qa-approval',choices=('root-reviewed',))
    a=p.parse_args(argv)
    if not a.authorize_extension_preparation or a.qa_approval!='root-reviewed':
        print(json.dumps(dict(schema=PREPARED_SCHEMA,status='DISABLED_PENDING_ROOT_EXTENSION_QA',
            production_inputs_read=False,extension_generated=False,search_called=False,sat_called=False),sort_keys=True))
        return 0
    for key in ('base_prepared','base_sha256','witnesses','witnesses_sha256','source_manifest',
                'source_manifest_sha256','approved_root','campaign_dir','campaign_sha256','guard_state','outdir'):
        if getattr(a,key) is None:p.error('enabled preparation requires --'+key.replace('_','-'))
    guard=Guard(a.hard_utc,a.seconds,a.campaign_dir,a.guard_state,a.campaign_sha256)
    try:
        guard('pre_dispatch')
    except Stop as exc:
        print(json.dumps(dict(schema=PREPARED_SCHEMA,status='UNKNOWN',complete=False,
            stop_reason=str(exc),production_inputs_read=False,extension_generated=False,
            search_called=False,sat_called=False),sort_keys=True))
        return 0
    os.sched_setaffinity(0,{3})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    root=a.outdir.resolve()
    if root.is_relative_to(a.base_prepared.resolve().parent) or root.is_relative_to(a.approved_root.resolve()):
        raise ValueError("new output must not mutate immutable base/source packages")
    root.mkdir(parents=True,exist_ok=False)
    base_raw=a.base_prepared.read_bytes();witness_raw=a.witnesses.read_bytes()
    if raw_sha(base_raw)!=a.base_sha256 or raw_sha(witness_raw)!=a.witnesses_sha256:
        raise ValueError('base/witness input differs from root-reviewed raw hash')
    (root/'inputs').mkdir();(root/'inputs/base-prepared.json').write_bytes(base_raw)
    (root/'inputs/extension-witnesses.json').write_bytes(witness_raw)
    scratch=root/'source-recheck';scratch.mkdir()
    code=code_hashes()
    for name,expected in code.items():
        target=root/'code'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((REPO/name).read_bytes())
        if raw_sha(target.read_bytes())!=expected:raise ValueError("code changed while snapshotting")
    write_json(root/'launch.json',dict(schema=PREPARED_SCHEMA,code_sha256=code,runtime=runtime(),
        arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()}),exclusive=True)
    exit_code=0
    try:
        base,receipt=authenticate_base(a.base_prepared,a.base_sha256,a.source_manifest,
            a.source_manifest_sha256,a.approved_root,scratch,guard)
        expected=base.get("lifecycle_config",{})
        actual=dict(campaign_sha256=a.campaign_sha256,campaign_dir=str(a.campaign_dir.resolve()),
            guard_state=str(a.guard_state.resolve()),deadline_utc=guard.hard.isoformat())
        if any(expected.get(key)!=value for key,value in actual.items()):
            raise ValueError("extension campaign/resource/deadline config differs from approved base")
        # Preserve the immutable approved base package rather than altering it.
        shutil.copytree(a.base_prepared.resolve().parent,root/'base')
        guard("post_base_snapshot")
        document=build_extension(base,strict_load(witness_raw),a.base_sha256,a.witnesses_sha256,guard,receipt)
        validate_extension_prepared(document,base,strict_load(witness_raw),a.base_sha256,a.witnesses_sha256,guard,receipt)
        guard('pre_prepared_publication')
        write_json(root/'prepared.json',document,exclusive=True)
        guard('post_prepared_publication')
        result=dict(status='PREPARED_EXTENSION_NO_SEARCH',complete=True,extension_generated=True,
            search_called=False,sat_called=False,dictionary_size=document['dictionary_size'],
            new_atom_count=document['new_atom_count'],rank=document['rank'],nullity=document['nullity'],
            parity_broken=document['parity_broken'],odd_kernel_basis_count=document['odd_kernel_basis_count'],
            prepared_sha256=raw_sha((root/'prepared.json').read_bytes()))
    except Stop as exc:
        if (root/'prepared.json').exists():(root/'prepared.json').rename(root/'after-cutoff-raw-prepared.json')
        result=dict(status='UNKNOWN',complete=False,stop_reason=str(exc),search_called=False,sat_called=False)
    except Exception as exc:
        result=dict(status="FAILED_CLOSED",complete=False,extension_generated=False,
            error_type=type(exc).__name__,error=str(exc),search_called=False,sat_called=False)
        exit_code=2
    result.update(schema=PREPARED_SCHEMA,runtime=runtime(),code_sha256=code)
    write_json(root/'result.json',result,exclusive=True)
    write_json(root/'checksums.json',{str(f.relative_to(root)):raw_sha(f.read_bytes()) for f in sorted(root.rglob('*')) if f.is_file()},exclusive=True)
    print(json.dumps(result,sort_keys=True));return exit_code


if __name__=='__main__':raise SystemExit(main())
