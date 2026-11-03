"""Bounded constructive affine inventory: full orientation-specific pair spans."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import resource
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.constructive_affine43 import (ORIENTATIONS,projected_span,pair_column,reduce_span,coordinate_solutions,apply_move,planted_control)
from mmsearch.native_bridge import canonical_terms,term_set_sha256
from mmsearch.search import encode_candidate
from mmsearch.verify import verify_candidate,write_standalone_verifier


def payload(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def freeze(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)
    path.chmod(0o444)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--catalog',type=Path,required=True);p.add_argument('--dictionary',type=Path,required=True);p.add_argument('--wu-system',type=Path,required=True);p.add_argument('--heldout-manifest',type=Path,required=True);p.add_argument('--known-state',type=Path);p.add_argument('--outdir',type=Path,required=True);p.add_argument('--cpu',type=int,default=2);p.add_argument('--cpu-seconds',type=float,default=60);p.add_argument('--memory-mb',type=int,default=1024);p.add_argument('--max-exports',type=int,default=32);args=p.parse_args(argv)
    if not 1<=args.cpu_seconds<=60 or not 64<=args.memory_mb<=1024 or not 0<=args.max_exports<=32:p.error('inventory cap60CPU/1024MiB/32exports')
    os.sched_setaffinity(0,{args.cpu});os.nice(10);resource.setrlimit(resource.RLIMIT_AS,(args.memory_mb*1024**2,args.memory_mb*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    started=time.process_time();args.outdir.mkdir(parents=True,exist_ok=False)
    # Mandatory first executable mathematical control, before source inventory.
    control=planted_control();freeze(args.outdir/'control-n2.json',payload(control));print(json.dumps({'event':'planted_n2_control','valid':True,'rank_before':11,'rank_after':11,'entries':64}),flush=True)
    catalog_raw=args.catalog.read_bytes();catalog=json.loads(catalog_raw);heldout_raw=args.heldout_manifest.read_bytes();heldout=json.loads(heldout_raw);excluded_sources=set(heldout['v43_source_split']['heldout']);known_raw=args.known_state.read_bytes() if args.known_state and args.known_state.exists() else b'';known=json.loads(known_raw) if known_raw else {};dictionary_raw=args.dictionary.read_bytes();dictionary=json.loads(dictionary_raw);system_raw=args.wu_system.read_bytes();system=json.loads(system_raw)
    if len(catalog['initial_pool'])!=16:raise ValueError('approved nonheldout catalog must contain16sources')
    if len(dictionary)!=2458 or system['metadata']['mode_permutation']!=[2,0,1] or len(system['pairs'])!=1553:raise ValueError('expected frozen fullP1553/WU2458-triple dictionary')
    source_records=[];sources=[];seen=set(known.get('seen_terms',[]));basis_records={};basis_objects={};counts=Counter();per_source=[];exports=[];escape_hashes=set();winner=None;complete=True
    for item in catalog['initial_pool']:
        raw=Path(item['path']).read_bytes()
        if sha(raw)!=item['sha256']:raise ValueError('source raw hash changed')
        value=json.loads(raw);terms=set(canonical_terms(value));report=verify_candidate(value,random_trials=0)
        if len(terms)!=93 or not report['valid'] or report['exact_entries_checked']!=15625:raise ValueError('catalog source is not exact93')
        rlkey=sha(json.dumps(sorted(terms),separators=(',',':')).encode())
        if item.get('rl_source_hash')!=rlkey or rlkey in excluded_sources:raise ValueError('catalog source exclusion identity mismatch')
        source_records.append({'path':item['path'],'sha256':item['sha256'],'term_hash':term_set_sha256(terms),'rl_source_hash':rlkey,'verification':report})
        sources.append(terms);seen.add(term_set_sha256(terms))
    # Rebuild every projection from original(u,v,w) triples. Never reuse a WU
    # matrix for another axis. Reversed pairs use their own transposed columns.
    for orientation in ORIENTATIONS:
        pairs,columns,basis=projected_span(dictionary,orientation)
        key=''.join('uvw'[axis] for axis in orientation)
        if orientation==(2,0,1):
            if pairs!=[tuple(pair) for pair in system['pairs']] or len(basis)!=system['metadata']['linear_rank']:raise ValueError('full WU basis does not match frozenP1553 control')
        value={'orientation':list(orientation),'ordered_fixed_axes':list(orientation[:2]),'free_axis':orientation[2],
               'pair_count':len(pairs),'rank':len(basis),'row_bit_convention':'i*25+j for a_i*b_j','pairs':pairs,
               'columns_hex':[hex(column) for column in columns],
               'basis':[{'pivot':pivot,'vector_hex':hex(row),'original_pair_xor_hex':hex(proof)} for pivot,(row,proof) in sorted(basis.items(),reverse=True)]}
        raw=payload(value);freeze(args.outdir/'bases'/(key+'.json'),raw);basis_records[key]={'sha256':sha(raw),'pair_count':len(pairs),'rank':len(basis),'orientation':list(orientation)};basis_objects[key]=(columns,basis)
    stop_at=max(0,args.cpu_seconds-5)
    for source_index,terms in enumerate(sources):
        source=source_records[source_index];ordered=sorted(terms)
        for orientation in ORIENTATIONS:
            if time.process_time()-started>=stop_at:complete=False;break
            a,b,free=orientation;key=''.join('uvw'[axis] for axis in orientation);columns,basis=basis_objects[key];groups=defaultdict(list)
            for term in ordered:groups[term[free]].append(term)
            original_pairs={(term[a],term[b]) for term in terms};outside_before=[pair for pair in original_pairs if reduce_span(pair_column(*pair,25),basis)[0]]
            local=Counter();local['source_pairs_outside_full_projection']=len(outside_before);local['repeated_slices']=sum(len(selected)>=2 for selected in groups.values())
            for delta,selected in sorted(groups.items()):
                if len(selected)<2:continue
                vectors=[term[a] for term in selected]
                for neutral in ordered:
                    if neutral[free]==delta:continue
                    local['neutral_membership_queries']+=1
                    for coordinates in coordinate_solutions(vectors,neutral[a]):
                        if time.process_time()-started>=stop_at:complete=False;break
                        local['eligible_coordinate_witnesses']+=1
                        changed,proof=apply_move(terms,orientation,delta,neutral,coordinates,n=5);h=term_set_sha256(changed);rank=len(changed)
                        if rank<=92:
                            candidate=encode_candidate(changed,5,method='exact-constructive-affine43',proof=proof,source=source,span_scope='record check independent of span membership',target_rank=92)
                            report=verify_candidate(candidate,random_trials=0)
                            if not report['valid'] or report['exact_entries_checked']!=15625 or report['rank']>92:raise AssertionError('candidate record failed independent fullT')
                            freeze(args.outdir/'WINNER.json',payload(candidate));freeze(args.outdir/'WINNER.verification.json',payload(report));freeze(args.outdir/'WINNER.sha256',(sha(payload(candidate))+'  WINNER.json\n').encode());write_standalone_verifier(args.outdir/'WINNER.verify.py')
                            winner={'rank':rank,'path':str(args.outdir/'WINNER.json'),'sha256':sha(payload(candidate))};print(json.dumps({'event':'verified_record',**winner}),flush=True);break
                        local['rank93_proposals']+=rank==93;local['unchanged_termset']+=changed==terms
                        new_pairs=sorted({(term[a],term[b]) for term in changed}-original_pairs);outside=[]
                        for pair in new_pairs:
                            column=pair_column(*pair,25);remainder,witness=reduce_span(column,basis)
                            if remainder:
                                reconstructed=0;bits=witness
                                while bits:
                                    bit=bits&-bits;reconstructed^=columns[bit.bit_length()-1];bits^=bit
                                if column^reconstructed!=remainder:raise AssertionError('outside-span remainder witness failed')
                                outside.append({'pair':list(pair),'column_hex':hex(column),'remainder_hex':hex(remainder),'original_pair_xor_hex':hex(witness)})
                        local['new_pair_columns']+=len(new_pairs);local['new_columns_outside_full_projection']+=len(outside)
                        if outside:local['proposals_with_new_outside_column']+=1
                        qualifies=bool(outside) and not outside_before
                        if not qualifies:continue
                        local['qualifying_full_span_escapes']+=1
                        fresh=h not in escape_hashes;local['unique_qualifying_escape']+=fresh;escape_hashes.add(h)
                        if h in seen:local['duplicate_known_or_exported_state']+=1;continue
                        seen.add(h)
                        if len(exports)>=args.max_exports:local['export_cap_censored']+=1;continue
                        candidate=encode_candidate(changed,5,method='exact-constructive-affine43',source=source,proof=proof,
                            full_dictionary_sha256=sha(dictionary_raw),basis_sha256=basis_records[key]['sha256'],outside_column_witnesses=outside,
                            span_scope='outside the complete frozen dictionary projection for this ordered pair orientation; no algorithm inequivalence/novelty claim')
                        report=verify_candidate(candidate,random_trials=0)
                        if not report['valid'] or report['rank']!=93 or report['exact_entries_checked']!=15625:raise AssertionError('retained93 output failed independent fullT')
                        path=args.outdir/'verified'/(h+'.json');raw=payload(candidate);freeze(path,raw);freeze(args.outdir/'verification'/(h+'.verification.json'),payload(report))
                        exports.append({'path':str(path),'sha256':sha(raw),'term_hash':h,'rank':93,'orientation':list(orientation),'source_index':source_index,'basis_sha256':basis_records[key]['sha256']});local['exports']+=1
                    if winner or not complete:break
                if winner or not complete:break
            counts.update({k:v for k,v in local.items() if k!='source_pairs_outside_full_projection'});per_source.append({'source_index':source_index,'source_sha256':source['sha256'],'orientation':list(orientation),'basis_key':key,'source_in_full_projection_span':not outside_before,'counts':dict(local)})
            if winner or not complete:break
        if winner or not complete:break
    manifest={'format':'constructive-affine43-inventory-v1','status':'WINNER' if winner else 'COMPLETE' if complete else 'CPU_CENSORED','cpu_seconds':time.process_time()-started,'cpu_limit':args.cpu_seconds,'source_count':len(sources),'orientation_count':6,'counts':dict(counts),'per_source_orientation':per_source,'sources':source_records,'bases':basis_records,'exports':exports,'unique_escape_hashes':len(escape_hashes),'winner':winner,'input_hashes':{'catalog_sha256':sha(catalog_raw),'dictionary_sha256':sha(dictionary_raw),'wu_system_sha256':sha(system_raw),'heldout_manifest_sha256':sha(heldout_raw),'known_state_snapshot_sha256':sha(known_raw) if known_raw else None},'source_exclusion':'Uses only16 root-frozen native initial catalog states;4RLheldout sources excluded by that hash-bound catalog.','proof':'For a_j=XOR_i x_i*a_i, selected slice change is a_j*b_j*delta and neutral change is the identical tensor; XOR cancels. No new products are added; zeros/duplicate triples cancel.','scope':'Exact constructive coverage relative to orientation-specific full dictionary pair spans. Possibly reachable by unrestricted flips; no inequivalence, novelty, global UNSAT or new-rank claim without WINNER.'}
    freeze(args.outdir/'manifest.json',payload(manifest));freeze(args.outdir/'SUMMARY.json',payload({'status':manifest['status'],'cpu_seconds':manifest['cpu_seconds'],'counts':dict(counts),'unique_escapes':len(escape_hashes),'exports':len(exports),'bases':basis_records,'winner':winner}))
    for source in (Path(__file__),Path(__file__).resolve().parents[1]/'mmsearch/constructive_affine43.py'):
        freeze(args.outdir/'code'/source.name,source.read_bytes())
    print(json.dumps({'event':'inventory_complete','status':manifest['status'],'cpu_seconds':manifest['cpu_seconds'],'counts':dict(counts),'unique_escapes':len(escape_hashes),'exports':len(exports),'winner':winner}),flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
