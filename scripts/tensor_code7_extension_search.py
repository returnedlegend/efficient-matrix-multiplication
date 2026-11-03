#!/usr/bin/env python3
"""Disabled heuristic proposal for authenticated extension-prepared v2 only."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import random
import resource
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.tensor_code7 import (Walk,checked_candidate,choose_move,fundamental_kernel,
    rng_restore,strict_load,validate_kernel,xor_columns)
from mmsearch.tensor_code7_extension import PREPARED_SCHEMA,load_root_pinned_extension,raw_sha
from scripts.tensor_code7 import Stop,runtime,save_candidate,write_json
from scripts.tensor_code7_extension import code_hashes
from scripts.tensor_code7_extension_select import DirectGuard

SCHEMA='tensor_code7.extension_search.v1'
SAFE_STAGING_SHA256='8f40b6c0b1b58a8efa4a57583dc99c68aa79b7c56965ce93fc3374e95822e2da'
EXTRA_CODE=('scripts/tensor_code7_extension_search.py','tests/test_tensor_code7_extension_search.py',
            'research/tensor_code7_extension_search.md')
sha=raw_sha


class InnerPoll:
    """Clocks/signals every call; live guard at most0.1s apart, force per stage."""
    def __init__(self,guard):
        self.guard=guard;self.last=-float('inf');self.hard=guard.hard
        self.started=guard.started;self.seconds=guard.seconds;self.canonical=guard.canonical
    def __call__(self,barrier='loop'):
        if self.guard.canonical.signal_stop:raise Stop('stop_signal:'+barrier)
        now=time.monotonic()
        if now-self.guard.started>=self.guard.seconds:raise Stop('invocation_wall_cutoff:'+barrier)
        if datetime.now(timezone.utc).timestamp()>=self.guard.hard.timestamp()-3:raise Stop('hard_utc_postcheck_reserve:'+barrier)
        if barrier!='loop' or now-self.last>=.1:
            self.guard(barrier);self.last=time.monotonic()


def move_generators(columns,basis,document):
    """Keep the complete basis and directly expose authenticated small circuits."""
    answer=list(basis);seen=set(answer)
    for record in document.get('odd_relation_certificates',[]):
        cycle=int(record['cycle_hex'],16)
        if cycle.bit_count()!=5 or xor_columns(columns,cycle):
            raise ValueError('invalid authenticated five-term move certificate')
        if cycle not in seen:answer.append(cycle);seen.add(cycle)
    return answer


def lifecycle_config(args,guard):
    return dict(prepared_sha256=args.prepared_sha256,base_prepared_sha256=args.base_sha256,
        witness_manifest_sha256=args.witnesses_sha256,source_manifest_sha256=args.source_manifest_sha256,
        campaign_sha256=args.campaign_sha256,campaign_dir=str(args.campaign_dir.resolve()),
        guard_state=str(args.guard_state.resolve()),deadline_utc=guard.hard.isoformat())


def search_main(args,root,guard,hashes):
    raw=args.prepared.read_bytes()
    if sha(raw)!=args.prepared_sha256:raise ValueError('extension prepared differs from root pin')
    document=strict_load(raw)
    if document.get('schema')!=PREPARED_SCHEMA or type(document.get('dimension')) is not int or document['dimension']!=5 or type(document.get('field')) is not int or document['field']!=2:
        raise ValueError('production search requires literal n5/F2 extension schema v2')
    scratch=root/'source-recheck';scratch.mkdir()
    atoms,columns,seeds,cycles,derivation=load_root_pinned_extension(args.prepared,args.prepared_sha256,
        args.base_prepared,args.base_sha256,args.witnesses,args.witnesses_sha256,
        args.source_manifest,args.source_manifest_sha256,args.approved_root,scratch,guard)
    if any(state.bit_count()!=93 for state in seeds):raise ValueError('only original padded weight93 seeds permitted')
    base=strict_load(args.base_prepared.read_bytes())
    config=lifecycle_config(args,guard)
    expected=base.get('lifecycle_config',{})
    for key in ('campaign_sha256','campaign_dir','guard_state','deadline_utc'):
        if expected.get(key)!=config[key]:raise ValueError('extension search lifecycle differs from approved base')
    guard('post_authenticated_loader')
    prepared_sha=sha(raw)
    (root/'inputs').mkdir()
    for name,payload in [('prepared.json',raw),('base-prepared.json',args.base_prepared.read_bytes()),
        ('witnesses.json',args.witnesses.read_bytes()),('source-manifest.json',args.source_manifest.read_bytes())]:
        (root/'inputs'/name).write_bytes(payload)
    write_json(root/'derivation-receipt.json',derivation,exclusive=True)
    params = {"seed": args.seed, "temporary_excess": args.temporary_excess,
              "samples": args.samples, "restart_after": args.restart_after,
              "max_restarts": args.max_restarts, "winner_weight": 92, "certified_five_term_moves": True}
    rng = random.Random(args.seed)
    source = seeds[0]
    walk = Walk(source, source)
    order = list(range(len(columns)))
    saved = []
    resumed = False
    terminal_late = False
    if args.resume:
        checkpoint = strict_load(args.resume.read_bytes())
        if checkpoint["schema"] != SCHEMA or checkpoint["prepared_sha256"] != prepared_sha or checkpoint["code_sha256"] != hashes or checkpoint["parameters"] != params:
            raise ValueError("checkpoint input/code/parameter mismatch")
        if checkpoint.get("lifecycle_config") != config:
            raise ValueError("checkpoint lifecycle configuration differs")
        walk = Walk.from_json(checkpoint["cursor"])
        rng = rng_restore(checkpoint["rng_state"])
        order = checkpoint["basis_order"]
        cycles, rank = fundamental_kernel(columns, order, guard)
        if rank != document["rank"]:
            raise AssertionError("reordered rank changed")
        terminal_late = checkpoint.get("publication_eligibility") == "late_raw_only"
        if walk.best.bit_count() <= 92 and checkpoint.get("publication_eligibility") not in ("eligible_within_budget", "late_raw_only"):
            raise ValueError("terminal checkpoint lacks explicit publication eligibility")
        resumed = True
    target = int(document["target_hex"], 16)
    if xor_columns(columns, walk.state) != target or xor_columns(columns, walk.best) != target:
        raise ValueError("checkpoint state failed exact equations")
    generators = move_generators(columns,cycles,document)
    ceiling = min(x.bit_count() for x in seeds)+args.temporary_excess
    if walk.state.bit_count() > ceiling:
        raise ValueError("checkpoint exceeds temporary bound")
    last_checkpoint = 0.0
    winner = False
    status = "UNKNOWN"
    stop_reason = None
    pending_cursor = pending_rng = pending_order = None

    def checkpoint():
        if xor_columns(columns, walk.state) != target or xor_columns(columns, walk.best) != target:
            raise AssertionError("checkpoint invariant failure")
        write_json(root/"checkpoint.json", {"schema": SCHEMA, "prepared_sha256": prepared_sha,
            "code_sha256": hashes, "parameters": params, "cursor": walk.to_json(), "basis_order": order,
            "rng_state": rng.getstate(), "runtime": runtime(), "resumed": resumed, "lifecycle_config": config,
            "publication_eligibility": "eligible_within_budget" if winner else "late_raw_only" if (terminal_late or stop_reason is not None) and walk.best.bit_count() <= 92 else "pending"})

    try:
        checkpoint()
        if walk.best.bit_count() <= 92:
            if terminal_late:
                raise Stop("terminal_late_raw_witness_no_publication")
            guard("terminal_resume")
            saved.append(save_candidate(root, "first-record-evidence", atoms, walk.best, 5,
                         {"schema": SCHEMA, "terminal_resume": True, "cursor": walk.to_json(),
                          "prepared_sha256": prepared_sha, "novelty_claim": False}, guard=guard))
            winner = True
            status = "FROZEN_DOUBLE_CHECKED_LE92_STOP"
        while not winner and walk.restart < args.max_restarts:
            guard()
            pending_cursor = walk.to_json()
            pending_order = list(order)
            pending_rng = rng.getstate()
            rng_before = pending_rng
            move = None
            try:
                move, kind = choose_move(walk.state, generators, rng, ceiling, args.samples, guard=guard)
                guard("post_solve")
            except Stop as exc:
                rng.setstate(rng_before)
                write_json(root/f"after-cutoff-raw-move-{walk.step:08d}.json", {
                    "status": "UNKNOWN", "complete": False, "after_cutoff": True,
                    "no_within_budget_claim": True, "stop_reason": str(exc),
                    "state_before_hex": hex(walk.state), "proposed_move_hex": hex(move) if move else None,
                    "proposed_state_hex": hex(walk.state^move) if move else None}, exclusive=True)
                raise
            walk.step += 1
            walk.no_improvement += 1
            if move is not None:
                # All basis combinations have Az=0; check before applying too.
                if xor_columns(columns, move):
                    raise AssertionError("proposed move is outside full tensor kernel")
                walk.state ^= move
                walk.moves += 1
                if walk.state.bit_count() > ceiling:
                    raise AssertionError("temporary bound violated")
                guard("post_exact_move")
            if walk.state.bit_count() < walk.best.bit_count():
                walk.best = walk.state
                walk.no_improvement = 0
                evidence = {"schema": SCHEMA, "prepared_sha256": prepared_sha, "state_hex": hex(walk.best),
                            "cursor": walk.to_json(), "move_kind": kind, "code_sha256": hashes,
                            "runtime": runtime(), "novelty_claim": False}
                name = "first-record-evidence" if walk.best.bit_count() <= 92 else f"improvement-{len(saved):04d}"
                saved.append(save_candidate(root, name, atoms, walk.best, 5, evidence, guard=guard))
                if walk.best.bit_count() <= 92:
                    winner = True
                    status = "FROZEN_DOUBLE_CHECKED_LE92_STOP"
                    pending_cursor = pending_rng = pending_order = None
                    checkpoint()
                    break
            if move is None or walk.no_improvement >= args.restart_after:
                walk.restart += 1
                walk.state = seeds[rng.randrange(len(seeds))]
                walk.no_improvement = 0
                rng.shuffle(order)
                cycles, rank = fundamental_kernel(columns, order, guard)
                if rank != document["rank"]:
                    raise AssertionError("reorder rank changed")
                validate_kernel(columns, cycles)
                generators = move_generators(columns,cycles,document)
            guard("post_iteration")
            pending_cursor = pending_rng = pending_order = None
            if time.monotonic()-last_checkpoint >= 5:
                checkpoint()
                last_checkpoint = time.monotonic()
        if not winner:
            stop_reason = "MAX_RESTARTS"
    except Stop as exc:
        stop_reason = str(exc)
        if pending_cursor is not None:
            walk = Walk.from_json(pending_cursor)
            rng.setstate(pending_rng)
            order = pending_order
    finally:
        checkpoint()
    # Postchecks after a hold are diagnostic only and cannot create eligibility.
    _candidate, postcheck = checked_candidate(atoms, walk.best, 5)
    write_json(root/"postcheck.json", postcheck, exclusive=True)
    return {"status": status, "stop_reason": stop_reason, "complete": winner, "winner": winner, "search_called": True, "saved": saved,
            "best_weight": walk.best.bit_count(), "final_weight": walk.state.bit_count(),
            "cursor": walk.to_json(), "parameters": params, "rank": document["rank"],
            "nullity": document["nullity"], "dictionary_size": len(atoms), "prepared_sha256": prepared_sha,
            "resumed": resumed, "postcheck_passed": True, "novelty_claim": False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path);p.add_argument('--prepared-sha256')
    p.add_argument('--base-prepared',type=Path);p.add_argument('--base-sha256')
    p.add_argument('--witnesses',type=Path);p.add_argument('--witnesses-sha256')
    p.add_argument('--source-manifest',type=Path);p.add_argument('--source-manifest-sha256')
    p.add_argument('--approved-root',type=Path);p.add_argument('--campaign-dir',type=Path)
    p.add_argument('--campaign-sha256');p.add_argument('--guard-state',type=Path)
    p.add_argument('--hard-utc',default='2026-11-03T19:24:17Z');p.add_argument('--seconds',type=float,default=120)
    p.add_argument('--seed',type=int,default=20261103140701);p.add_argument('--temporary-excess',type=int,default=12)
    p.add_argument('--samples',type=int,default=256);p.add_argument('--restart-after',type=int,default=64)
    p.add_argument('--max-restarts',type=int,default=1000000000);p.add_argument('--resume',type=Path)
    p.add_argument('--outdir',type=Path);p.add_argument('--authorize-search',action='store_true')
    p.add_argument('--qa-approval',choices=('root-reviewed',));a=p.parse_args(argv)
    if not a.authorize_search or a.qa_approval!='root-reviewed':
        print(json.dumps(dict(schema=SCHEMA,status='DISABLED_PENDING_ROOT_EXTENSION_SEARCH_QA',
            production_inputs_read=False,search_called=False),sort_keys=True));return 0
    for key in ('prepared','prepared_sha256','base_prepared','base_sha256','witnesses','witnesses_sha256',
                'source_manifest','source_manifest_sha256','approved_root','campaign_dir','campaign_sha256','guard_state','outdir'):
        if getattr(a,key) is None:p.error('enabled query requires --'+key.replace('_','-'))
    if not 0<=a.temporary_excess<=12 or not 0<=a.samples<=4096 or a.restart_after<1 or a.max_restarts<1:p.error('reviewed bounds exceeded')
    direct=DirectGuard(a);guard=InnerPoll(direct)
    try:guard('pre_dispatch')
    except Stop as exc:
        print(json.dumps(dict(schema=SCHEMA,status='UNKNOWN',complete=False,stop_reason=str(exc),
            production_inputs_read=False,search_called=False),sort_keys=True));return 0
    if sha((REPO/'scripts/tensor_code7.py').read_bytes())!=SAFE_STAGING_SHA256:raise ValueError('safe staging library differs from reviewed pin')
    os.sched_setaffinity(0,{3})
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
    root=a.outdir.resolve()
    if any(root.is_relative_to(path.resolve().parent) for path in (a.prepared,a.base_prepared)) or root.is_relative_to(a.approved_root.resolve()):
        raise ValueError('query output must not mutate frozen inputs')
    root.mkdir(parents=True,exist_ok=False)
    hashes=code_hashes();hashes.update({name:sha((REPO/name).read_bytes()) for name in EXTRA_CODE})
    for name,expected in hashes.items():
        target=root/'code'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((REPO/name).read_bytes())
        if sha(target.read_bytes())!=expected:raise ValueError('code changed during snapshot')
    write_json(root/'launch.json',dict(schema=SCHEMA,runtime=runtime(),code_sha256=hashes,
        arguments={key:str(value) if isinstance(value,Path) else value for key,value in vars(a).items()}),exclusive=True)
    exit_code=0
    try:result=search_main(a,root,guard,hashes)
    except Stop as exc:result=dict(status='UNKNOWN',complete=False,stop_reason=str(exc),search_called=False)
    except Exception as exc:
        result=dict(status='FAILED_CLOSED',complete=False,error_type=type(exc).__name__,error=str(exc),search_called=False);exit_code=2
    result.update(schema=SCHEMA,runtime=runtime(),code_sha256=hashes,elapsed_seconds=time.monotonic()-direct.started)
    write_json(root/'result.json',result,exclusive=True)
    write_json(root/'checksums.json',{str(path.relative_to(root)):sha(path.read_bytes()) for path in sorted(root.rglob('*')) if path.is_file()},exclusive=True)
    print(json.dumps(result,sort_keys=True));return exit_code


if __name__=='__main__':raise SystemExit(main())
