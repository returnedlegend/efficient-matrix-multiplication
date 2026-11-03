"""Bounded deterministic depth3 constructive BFS with exact joint compression."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import heapq
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.constructive_affine43 import ORIENTATIONS,projected_span,coordinate_solutions,apply_move
from mmsearch.constructive_affine_bfs43 import extend_with_parent,difference_witnesses,composed_control
from mmsearch.kernel_quartet_frontier import compress_export
from mmsearch.native_bridge import canonical_terms,term_set_sha256
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate,write_standalone_verifier


def raw(value):return (json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
def sha(value):return hashlib.sha256(value).hexdigest()
def freeze(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(payload)
    path.chmod(0o444)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roots',type=Path,required=True);p.add_argument('--dictionary',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--known-state',type=Path);p.add_argument('--outdir',type=Path,required=True);p.add_argument('--cpu',type=int,default=2);p.add_argument('--cpu-seconds',type=float,default=60);p.add_argument('--memory-mb',type=int,default=1024);p.add_argument('--max-states',type=int,default=512);p.add_argument('--max-exports',type=int,default=32);p.add_argument('--depth',type=int,default=3);args=p.parse_args(argv)
    if not 1<=args.cpu_seconds<=60 or not 64<=args.memory_mb<=1024 or not 4<=args.max_states<=512 or not 0<=args.max_exports<=32 or not 0<=args.depth<=3:p.error('bounds:depth3/states512/exports32/60CPU/1024MiB')
    os.sched_setaffinity(0,{args.cpu});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(args.memory_mb*1024**2,args.memory_mb*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(60,60));start=time.process_time();args.outdir.mkdir(parents=True,exist_ok=False)
    campaign_policy=json.loads((args.campaign/'campaign.json').read_text());deadline=dt.datetime.fromisoformat(campaign_policy['deadline_utc'].replace('Z','+00:00')).timestamp()
    stopping=False
    def stop(_signum,_frame):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    def marker():
        if stopping:return 'EXTERNAL_SIGNAL'
        if time.time()>=deadline:return 'DEADLINE'
        if (args.campaign/'guard_stopped.json').exists() or (args.campaign/'WINNER.json').exists():return 'CAMPAIGN_STOP'
        for path in args.campaign.glob('*/WINNER.json'):
            if path.parent.resolve()!=args.outdir.resolve():return 'OTHER_WINNER'
        q=args.campaign/'queue_state.json'
        if q.exists() and json.loads(q.read_text()).get('stop_reason'):return 'QUEUE_STOP'
        if time.process_time()-start>=max(0,args.cpu_seconds-5):return 'CPU_CENSORED'
        return None
    initial_marker=marker()
    if initial_marker:
        freeze(args.outdir/'SUMMARY.json',raw({'status':initial_marker,'visited':0,'winner':None}));print(json.dumps({'status':initial_marker}));return 0
    roots_payload=args.roots.read_bytes();roots_manifest=json.loads(roots_payload);prior_control_path=args.roots.parent/'control-n2.json';control_payload=prior_control_path.read_bytes();control=composed_control(json.loads(control_payload));freeze(args.outdir/'control-composed-n2.json',raw(control));print(json.dumps({'event':'composed_control','valid':True,'ranks':control['ranks'],'fixed_point':True}),flush=True)
    dictionary_payload=args.dictionary.read_bytes();dictionary=json.loads(dictionary_payload)
    known_payload=args.known_state.read_bytes() if args.known_state and args.known_state.exists() else b'';known=json.loads(known_payload) if known_payload else {};known_hashes=set(known.get('seen_terms',[]))|{item['term_hash'] for item in roots_manifest['sources']}
    full={};basis_info={}
    for orientation in ORIENTATIONS:
        key=''.join('uvw'[axis] for axis in orientation);pairs,columns,basis=projected_span(dictionary,orientation)
        value={'orientation':list(orientation),'pair_count':len(pairs),'rank':len(basis),'pairs':pairs,
               'columns_hex':[hex(x) for x in columns],'basis':[{'pivot':pivot,'vector_hex':hex(row),'original_column_xor_hex':hex(proof)} for pivot,(row,proof) in sorted(basis.items(),reverse=True)]}
        payload=raw(value);freeze(args.outdir/'bases/full'/(key+'.json'),payload);basis_info[key]={'sha256':sha(payload),'pairs':len(pairs),'rank':len(basis),'orientation':list(orientation)};full[key]=(columns,basis)
    if len(dictionary)!=2499 or basis_info['wuv']['pairs']!=1565 or basis_info['wuv']['rank']!=375:raise ValueError('expected new fullP1565 dictionary version')
    nodes={};heap=[];compression_cache={};counts=Counter();edges=[];winner=None;end_reason=None;complete_nodes=[];root_refs=[]
    def winner_freeze(candidate,report,origin):
        nonlocal winner
        independent=verify_candidate(candidate,random_trials=0)
        if not independent['valid'] or independent['exact_entries_checked']!=15625 or independent['rank']>92:raise AssertionError('record failed fullT')
        value=dict(candidate);value['metadata']={**candidate.get('metadata',{}),'record_origin':origin,'target_rank':92}
        payload=raw(value);freeze(args.outdir/'WINNER.json',payload);freeze(args.outdir/'WINNER.verification.json',raw(independent));freeze(args.outdir/'WINNER.sha256',(sha(payload)+'  WINNER.json\n').encode());write_standalone_verifier(args.outdir/'WINNER.verify.py');winner={'rank':independent['rank'],'sha256':sha(payload),'path':str(args.outdir/'WINNER.json'),'origin':origin};print(json.dumps({'event':'verified_record',**winner}),flush=True)
    def compress_checked(terms,origin):
        h=term_set_sha256(terms)
        if len(terms)<=92:
            candidate=encode_candidate(terms,5,method='constructive-affine-bfs43-raw',origin=origin);report=verify_candidate(candidate,random_trials=0);winner_freeze(candidate,report,origin);return None
        if h in compression_cache:counts['compression_cache_hits']+=1;return compression_cache[h]
        candidate,report,trace=compress_export(encode_candidate(terms,5))
        if not report['valid'] or report['exact_entries_checked']!=15625:raise AssertionError('compressed state failed fullT')
        changed=set(canonical_terms(candidate));counts['joint_compression_calls']+=1;counts['compression_product_reductions']+=len(terms)-len(changed)
        if len(changed)<=92:winner_freeze(candidate,report,origin);return None
        if len(changed)!=93 or not trace['fixed_point']:raise AssertionError('retained state lacks rank93 joint fixed point')
        value=(changed,report,trace);compression_cache[h]=value
        final_hash=term_set_sha256(changed)
        if final_hash not in compression_cache:compression_cache[final_hash]=value
        return value
    def retain(terms,report,trace,*,depth,parent,proof,difference,basis_ref,root=None):
        h=term_set_sha256(terms)
        if h in nodes:return h,False
        if len(nodes)>=args.max_states:return h,False
        candidate=encode_candidate(terms,5,method='deterministic-constructive-affine-bfs43',depth=depth,parent=parent,move=proof,
            parent_augmented_basis=basis_ref,fresh_outside_column_witnesses=difference,root=root,scope='rank93 research state; no novelty or global rank claim')
        independent=verify_candidate(candidate,random_trials=0)
        if not independent['valid'] or independent['rank']!=93 or independent['exact_entries_checked']!=15625:raise AssertionError('retained BFS state failed independent fullT')
        path=args.outdir/'states'/(h+'.json');freeze(path,raw(candidate));freeze(args.outdir/'verification'/(h+'.verification.json'),raw(independent));freeze(args.outdir/'compression'/(h+'.json'),raw(trace))
        node={'term_hash':h,'path':str(path),'sha256':sha(raw(candidate)),'depth':depth,'parent':parent,'root':root,
              'fresh_escape_columns':len(difference),'difference_witnesses':difference,'parent_basis':basis_ref,'known_at_start':h in known_hashes,'rank':93}
        nodes[h]=node;heapq.heappush(heap,(depth,-len(difference),h));counts['retained_states']+=1
        return h,True
    for item in roots_manifest['exports']:
        end_reason=marker()
        if end_reason:break
        payload=Path(item['path']).read_bytes()
        if sha(payload)!=item['sha256']:raise ValueError('root export bytes changed')
        terms=set(canonical_terms(json.loads(payload)));root_report=verify_candidate(encode_candidate(terms,5),random_trials=0)
        if not root_report['valid'] or len(terms)!=93:raise ValueError('root is not exact93')
        compressed=compress_checked(terms,{'root':item['term_hash']})
        if winner:break
        terms,report,trace=compressed;h,_=retain(terms,report,trace,depth=0,parent=None,proof=None,difference=[],basis_ref=None,root=item['term_hash']);root_refs.append({'original':item,'compressed_term_hash':h})
    while heap and not winner and not end_reason:
        end_reason=marker()
        if end_reason:break
        depth,negative_priority,parent_hash=heapq.heappop(heap);parent_node=nodes[parent_hash]
        if depth>=args.depth:counts['depth_boundary_states']+=1;continue
        parent_terms=set(canonical_terms(json.loads(Path(parent_node['path']).read_text())));ordered=sorted(parent_terms);expanded=True
        for orientation in ORIENTATIONS:
            end_reason=marker()
            if end_reason:expanded=False;break
            a,b,free=orientation;key=''.join('uvw'[axis] for axis in orientation);parent_pairs=sorted({(term[a],term[b]) for term in parent_terms});full_columns,full_basis=full[key];columns,basis,added=extend_with_parent(full_columns,full_basis,parent_pairs)
            augmentation={'orientation':list(orientation),'full_basis_sha256':basis_info[key]['sha256'],'parent_term_hash':parent_hash,
                'full_column_count':len(full_columns),'parent_pairs':parent_pairs,'full_rank':len(full_basis),'augmented_rank':len(basis),'added_basis_rows':added}
            augmentation_payload=raw(augmentation);augmentation_path=args.outdir/'bases/parents'/parent_hash/(key+'.json');freeze(augmentation_path,augmentation_payload);basis_ref={'path':str(augmentation_path),'sha256':sha(augmentation_payload),'orientation':list(orientation),'full_rank':len(full_basis),'augmented_rank':len(basis)}
            groups=defaultdict(list)
            for term in ordered:groups[term[free]].append(term)
            for delta,selected in sorted(groups.items()):
                if len(selected)<2:continue
                vectors=[term[a] for term in selected]
                for neutral in ordered:
                    if neutral[free]==delta:continue
                    counts['membership_queries']+=1
                    for coordinate in coordinate_solutions(vectors,neutral[a]):
                        end_reason=marker()
                        if end_reason:expanded=False;break
                        counts['attempted_moves']+=1;changed,move=apply_move(parent_terms,orientation,delta,neutral,coordinate,n=5);raw_rank=len(changed)
                        compressed=compress_checked(changed,{'parent':parent_hash,'depth':depth+1,'move':move})
                        if winner:expanded=False;break
                        end_reason=marker()
                        if end_reason:expanded=False;break
                        changed,report,trace=compressed;child_hash=term_set_sha256(changed);difference,new_pair_count=difference_witnesses(changed,parent_terms,orientation,columns,basis)
                        counts['fresh_outside_column_proposals']+=bool(difference);counts['fresh_outside_columns']+=len(difference)
                        edge={'parent':parent_hash,'child':child_hash,'depth':depth+1,'move':move,'new_pair_columns':new_pair_count,'fresh_outside_columns':len(difference),'basis':basis_ref,'raw_after_move_rank':raw_rank,'compressed_rank':len(changed),'duplicate':child_hash in nodes}
                        edges.append(edge)
                        if child_hash in nodes:counts['duplicate_states']+=1;continue
                        if len(nodes)>=args.max_states:end_reason='STATE_CAP';expanded=False;break
                        _,accepted=retain(changed,report,trace,depth=depth+1,parent=parent_hash,proof=move,difference=difference,basis_ref=basis_ref,root=parent_node['root'])
                        counts['new_child_states']+=accepted
                        if len(nodes)>=args.max_states:end_reason='STATE_CAP';expanded=False;break
                    if winner or end_reason:break
                if winner or end_reason:break
            if winner or end_reason:break
        if expanded:complete_nodes.append(parent_hash)
    exports=[]
    if not winner:
        candidates=[node for node in nodes.values() if node['depth']>0 and not node['known_at_start']]
        candidates.sort(key=lambda node:(-bool(node['fresh_escape_columns']),-node['fresh_escape_columns'],node['depth'],node['term_hash']))
        for node in candidates[:args.max_exports]:
            source=Path(node['path']);target=args.outdir/'exports'/source.name;freeze(target,source.read_bytes());exports.append({**node,'export_path':str(target)})
    status='WINNER' if winner else end_reason or 'COMPLETE_DEPTH_FAMILY'
    manifest={'format':'constructive-affine43-bfs-v1','status':status,'cpu_seconds':time.process_time()-start,'limits':{'cpu':args.cpu_seconds,'memory_mib':args.memory_mb,'max_depth':args.depth,'states':args.max_states,'exports':args.max_exports},'counts':dict(counts),'visited_states':len(nodes),'exports':exports,'tree':list(nodes.values()),'edges':edges,'roots':root_refs,'full_bases':basis_info,'fully_expanded_nodes':complete_nodes,'unexpanded_frontier':len(heap),'winner':winner,'input_hashes':{'root_manifest_sha256':sha(roots_payload),'reused_control_sha256':sha(control_payload),'dictionary_sha256':sha(dictionary_payload),'known_state_sha256':sha(known_payload) if known_payload else None},'claims':'Only this deterministic bounded constructive/compression tree. COMPLETE_DEPTH_FAMILY means all legal coordinate moves from visited nodes below depth limit were expanded; STATE_CAP/CPU/stop are partial, never exhaustive global claims. Every retained state fullT verified. Rank93 ties prioritize fresh column departure from full frozen projection PLUS current parent pairs; inherited escapes receive no fresh-departure credit. No novelty/inequivalence/rank92 claim absent WINNER.'}
    freeze(args.outdir/'manifest.json',raw(manifest));freeze(args.outdir/'SUMMARY.json',raw({'status':status,'cpu_seconds':manifest['cpu_seconds'],'counts':dict(counts),'visited_states':len(nodes),'exports':len(exports),'depth_counts':dict(Counter(node['depth'] for node in nodes.values())),'fully_expanded_nodes':len(complete_nodes),'unexpanded_frontier':len(heap),'winner':winner}))
    dependencies=['scripts/bfs_constructive_affine43.py','mmsearch/constructive_affine_bfs43.py','mmsearch/constructive_affine43.py','mmsearch/kernel_quartet_frontier.py','mmsearch/pair_column_compression.py','mmsearch/slice_compression.py','mmsearch/free_factor_sat.py','mmsearch/free_factor_kernel.py','mmsearch/search.py','mmsearch/verify.py','mmsearch/native_bridge.py'];code={}
    for name in dependencies:
        source=Path(__file__).resolve().parents[1]/name;payload=source.read_bytes();freeze(args.outdir/'code'/name,payload);code[name]=sha(payload)
    freeze(args.outdir/'provenance.json',raw({'command':sys.argv,'python':sys.version,'code_sha256':code,'input_hashes':manifest['input_hashes'],'cpu_seconds':manifest['cpu_seconds']}))
    print(json.dumps({'event':'bfs_complete','status':status,'cpu_seconds':manifest['cpu_seconds'],'visited':len(nodes),'exports':len(exports),'depth_counts':dict(Counter(node['depth'] for node in nodes.values())),'counts':dict(counts),'winner':winner}),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
