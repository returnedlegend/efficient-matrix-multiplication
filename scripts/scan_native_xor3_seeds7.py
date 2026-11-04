"""Bounded query-free input census: exact XOR3 then shared-two-factor fixpoint."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
import os
from pathlib import Path
import resource
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.compact_xor3_seed7 import reduce_shared_two
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts import campaign_native_baseline7 as safe

PREPARED_SHA='2302ae5e82fe7afd1845dd50ffd5c12f17e1efb56b8f4adf1ed09bd31a71e886'
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();campaign=args.campaign.resolve();output=args.output.resolve()
    if output.exists() or output.parent!=campaign:raise ValueError('exclusive new direct scan folder required')
    os.sched_setaffinity(0,{1});resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));started=time.monotonic();cpu=time.process_time()
    guard=CampaignGuard(90,'2026-11-03T19:24:17Z',guard_state=campaign/'operations-v3/state.json',campaign_dir=campaign);guard.check('pre_xor3_scan');poller=CancelPoller(guard)
    def poll():
        if poller.cancelled():guard.check('xor3_scan_cancelled')
    def fresh(barrier):
        try:guard.check(barrier);return True
        except Exception:return False
    path=campaign/'tensor-code-native-corpus-prep-001/prepared.json';raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PREPARED_SHA:raise ValueError('root-pinned prepared corpus differs')
    prepared=json.loads(raw);atoms=list(map(tuple,prepared['atoms']));states=[int(x,16)for x in prepared['seed_states_hex']]
    if len(atoms)!=522 or len(states)!=36:raise ValueError('exact root-approved522/36 corpus required')
    known={safe.base.term_set_sha256([atoms[i]for i in range(522)if state>>i&1]) for state in states}
    # Exclude observed older states from native restarts, without claiming novelty.
    for pattern in ['native-portfolio7-p*/summary.json','native-bandit7-e*/summary.json']:
        for summary in campaign.glob(pattern):
            value=json.loads(summary.read_bytes());known.update(value.get('raw_exports',{}))
    output.mkdir();safe.base.freeze(output/'scan-code.py',Path(__file__).read_bytes());safe.base.freeze(output/'reduction-code.py',(ROOT/'mmsearch/compact_xor3_seed7.py').read_bytes())
    cases=[];hist=Counter();duplicates=Counter();seen={};target=False
    for parents in itertools.combinations(range(36),3):
        poll();state=states[parents[0]]^states[parents[1]]^states[parents[2]]
        initial=tuple(atoms[i]for i in range(522)if state>>i&1)
        reduced,moves=reduce_shared_two(initial,poll);rank=len(reduced);digest=safe.base.term_set_sha256(reduced);hist[rank]+=1
        entry=dict(parents=parents,input_rank=len(initial),reduced_rank=rank,reduction_moves=len(moves),
            term_set_sha256=digest,previously_observed=digest in known)
        cases.append(entry)
        if digest not in seen:seen[digest]=(entry,reduced,moves)
        duplicates[digest]+=1
        if rank<=92:
            candidate=safe.base.encode_candidate(reduced,5,method='exact-xor3-shared-two-fixpoint',
                prepared_sha256=PREPARED_SHA,parent_indices=parents,reduction=moves)
            target=safe.retain_target(output,candidate,fresh,target=92)
            if target:break
    eligible=[row for row in seen.values()if 93<=len(row[1])<=125 and not row[0]['previously_observed']]
    eligible.sort(key=lambda row:(row[0]['reduced_rank'],row[0]['input_rank'],row[0]['parents']))
    # Keep costs low, then spread starts across exact atom supports and parent triples.
    pool=eligible[:512];selected=[]
    if pool:selected.append(pool.pop(0))
    while pool and len(selected)<8:
        chosen=max(range(len(pool)),key=lambda i:(
            min(len(set(pool[i][1])^set(old[1]))for old in selected)-2*(pool[i][0]['reduced_rank']-eligible[0][0]['reduced_rank']),
            len(set(pool[i][0]['parents'])-set.union(*(set(old[0]['parents'])for old in selected))),
            -pool[i][0]['reduced_rank'],tuple(-x for x in pool[i][0]['parents'])))
        selected.append(pool.pop(chosen))
    outputs=[]
    for index,(entry,terms,moves)in enumerate(selected):
        guard.check('pre_selected_full_double_verify');candidate=safe.base.encode_candidate(terms,5,method='exact-xor3-shared-two-fixpoint',
            prepared_sha256=PREPARED_SHA,parent_indices=entry['parents'],reduction=moves)
        payload=safe.base.raw_json(candidate);first=safe.verify_candidate(candidate,random_trials=0);guard.check('post_selected_primary');second=safe.independent(candidate,payload);guard.check('post_selected_independent')
        if not first['valid'] or not second['valid'] or first['exact_entries_checked']!=15625 or second['exact_entries_checked']!=15625 or second['essential_rank']!=len(terms):raise ValueError('selected seed full verification failed')
        filename=f'seeds/seed-{index:02d}.json';safe.base.freeze(output/filename,payload)
        proof=dict(primary=first,independent=second,moves=moves,parent_source_records=[prepared['source_records'][i]for i in entry['parents']])
        safe.base.freeze(output/f'seeds/seed-{index:02d}.proof.json',encoded(proof))
        outputs.append(dict(**entry,file=filename,sha256=hashlib.sha256(payload).hexdigest(),primary=first,independent=second,
            parent_source_byte_hashes=[prepared['source_records'][i]['canonical_certificate_sha256']for i in entry['parents']],
            parent_raw_hashes=[prepared['source_records'][i]['raw_sha256']for i in entry['parents']],
            parent_train_roots=[prepared['source_records'][i]['native_root_id']for i in entry['parents']]))
    guard.check('post_xor3_scan')
    result=dict(status='TARGET_EMITTED_TO_GLOBAL_GUARD'if target else'FINITE_XOR3_REDUCTION_SCAN_COMPLETE',
        source_prepared_sha256=PREPARED_SHA,source_manifest_sha256=prepared['source_manifest_sha256'],
        attempted=len(cases),unique_reduced_states=len(seen),reduced_rank_histogram=dict(sorted(hist.items())),
        minimum_reduced_rank=min(hist),previously_observed_reduced_states=sum(row[0]['previously_observed']for row in seen.values()),
        eligible_unobserved_rank93_to125=len(eligible),selected=outputs,selected_ranks=[row['reduced_rank']for row in outputs],
        maximum_shared_two_reductions=max(row['reduction_moves']for row in cases),elapsed_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,
        guard=guard.observation(),native_queries=0,claim='Exact GF2 XOR3-derived tensors and deterministic exact reductions only; state diversity is not mathematical novelty; no global lower bound.')
    safe.base.freeze(output/'cases.json',encoded(cases));safe.base.freeze(output/'summary.json',encoded(result))
    print(json.dumps({key:value for key,value in result.items()if key not in('selected','guard','reduced_rank_histogram')},sort_keys=True))

if __name__=='__main__':main()
