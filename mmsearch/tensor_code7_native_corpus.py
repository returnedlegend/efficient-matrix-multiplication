"""New native-export corpus contract. The affine-only loader is unchanged.

Native outputs inherit run-level provenance only from exact root-train inputs,
pinned producer CPP/binaries/config, registered output bytes, and fresh complete
F2 tensor checks. Inventory rank labels never establish verified seed rank.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass,asdict
import json
from pathlib import Path
import re

from mmsearch.tensor_code7 import (atom_from_term,digest,prepare,second_check,strict_load,term_from_atom)
from mmsearch.tensor_code7_extension import authenticate_base,raw_sha
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes

SOURCES_SCHEMA='tensor_code7.native_corpus_sources.v1'
PREPARED_SCHEMA='tensor_code7.native_corpus_prepared.v1'
ALLOWED_RUNS=('baseline-native300-001','hold-rank-pilot-s01-flag0-K4-D128',
 'hold-rank-pilot-s01-flag1-K4-D128','hold-rank-pilot-s02-flag0-K4-D128','hold-rank-pilot-s02-flag1-K4-D128')
PLUS_CPP_SHA='b65f0bda48a0c217d66d65a4db21e286c93448128373c439e8d66c3b8d8c8c1f'
HOLD_CPP_SHA='81388f969701b852b11575392d8734ec40f13d56ba5c7aa5e4a50733d2ed0222'
BINARY_SHA={'baseline-native300-001':'6e7d6c63fa262bfc50acfe92fbe9c11adb74426e3868a5a6f7ad8d1bf569ac19'}
HOLD_BINARY_SHA='3d20e4539cbd9966353629c396ef91cbc3994a5e88773fa51a3f919da6945244'


@dataclass(frozen=True)
class NativeReceipt:
 sources_manifest_sha256: str
 authority_prepared_sha256: str
 authority_anchors_sha256: str
 export_raw_hashes: tuple
 root_ids: tuple


def native_bytes(atoms):
 return ''.join(f'{a} {b} {c}\n' for a,b,c in sorted(atoms)).encode()


def identities(atoms):
 return dict(term_set_sha256=raw_sha(native_bytes(atoms)),rl_source_sha256=digest(sorted(atoms)))


def parse_native(raw,n=5):
 if len(raw)>1024**2:raise ValueError('native export exceeds schema byte limit')
 try:lines=raw.decode('ascii').splitlines()
 except UnicodeError as exc:raise ValueError('native text must be ASCII') from exc
 atoms=[]
 for line in lines:
  if not re.fullmatch(r'[1-9][0-9]* [1-9][0-9]* [1-9][0-9]*',line):raise ValueError('native rows require three canonical nonzero decimal masks')
  atom=tuple(map(int,line.split()));term_from_atom(atom,n);atoms.append(atom)
 if not atoms or len(set(atoms))!=len(atoms):raise ValueError('empty or duplicate native products')
 if raw!=native_bytes(atoms):raise ValueError('native rows must be sorted canonical lines with terminal LF')
 return tuple(atoms)


def parse_json_candidate(raw,n=5):
 value=strict_load(raw)
 if type(value.get('dimension')) is not int or value['dimension']!=n or type(value.get('field')) is not int or value['field']!=2:
  raise ValueError('literal matching dimension/F2 required')
 atoms=tuple(sorted(atom_from_term(t,n) for t in value['terms']))
 if not atoms or len(set(atoms))!=len(atoms):raise ValueError('empty or duplicate candidate products')
 return atoms,value


def candidate_from_atoms(atoms,n=5):
 return dict(dimension=n,field=2,terms=[term_from_atom(atom,n) for atom in atoms])


def choose_diverse(records,load_atoms,max93=32,max94=4,old_atoms=()):
 """Deterministic metadata selection only; source ranks are verified later."""
 if type(max93) is not int or not 1<=max93<=32 or type(max94) is not int or not 1<=max94<=4:raise ValueError('corpus source caps exceeded')
 unique={}
 for record in sorted(records,key=lambda r:(r['run'],r['identity'],r['raw_sha256'])):
  unique.setdefault(record['identity'],record)
 pool={key:(record,frozenset(load_atoms(record))) for key,record in unique.items()}
 chosen=[];used=set();union=set();old=set(old_atoms)
 def take(key):
  record,atoms=pool[key];chosen.append(record);used.add(key);union.update(atoms)
 def score(key):
  record,atoms=pool[key]
  distance=min((len(atoms^pool[x][1]) for x in used),default=len(atoms)*2)
  return (distance,len(atoms-union),len(atoms-old),key)
 # Cover every producer branch before the global farthest-first pass.
 for run in sorted({r['run'] for r in unique.values()}):
  if len(chosen)>=max93:break
  keys=[key for key,(rec,atoms) in pool.items() if rec['run']==run and rec['rank']==93 and key not in used]
  if keys:take(max(keys,key=score))
 while len(chosen)<max93:
  keys=[key for key,(rec,atoms) in pool.items() if rec['rank']==93 and key not in used]
  if not keys:break
  take(max(keys,key=score))
 rank93_count=len(chosen)
 for _ in range(max94):
  keys=[key for key,(rec,atoms) in pool.items() if rec['rank']==94 and key not in used]
  if not keys:break
  # Prefer interaction with selected93 atoms; no state objective is scored.
  key=max(keys,key=lambda key:(len(pool[key][1]&union),-len(pool[key][1]-union),key));take(key)
 return chosen,dict(rank93_selected=rank93_count,rank94_selected=len(chosen)-rank93_count,
  union_atoms=len(union),old_atom_overlap=len(union&old),new_atoms_relative_old=len(union-old),
  private_atoms=sum(sum(atom in pool[r['identity']][1] for r in chosen)==1 for atom in union),
  by_run=dict(Counter(r['run'] for r in chosen)),policy='cover all5 producer branches, farthest-first93; interaction-first94',
  full_tensor_checks_performed=False,optimization_called=False)


def command_pairs(command):
 if type(command) is not list or len(command)%2!=1 or any(type(x) is not str for x in command):raise ValueError('strict executable plus flag/value pairs required')
 pairs={}
 for flag,value in zip(command[1::2],command[2::2]):
  if not flag.startswith('--') or flag in pairs:raise ValueError('duplicate/invalid native command flag')
  pairs[flag]=value
 allowed={'--input','--output','--n','--target','--max-rank','--seed','--steps','--seconds','--checkpoint-seconds',
  '--archive-size','--archive-every','--plus-every','--restart-every','--plus-burst','--reduction-dwell','--dwell-hold-rank'}
 if set(pairs)-allowed or pairs.get('--n')!='5' or pairs.get('--target')!='92':raise ValueError('native command has unknown inputs/modes')
 return pairs


def load_sources(manifest,manifest_sha256,campaign_root,scratch,freeze,guard):
 """Authenticate every selected run/export; then freshly double-check it."""
 if type(manifest) is not dict or set(manifest)!={'schema','dimension','field','authority','runs','selected','selection','scope'}:raise ValueError('unexpected native source contract fields')
 if manifest.get('schema')!=SOURCES_SCHEMA or type(manifest.get('dimension')) is not int or manifest['dimension']!=5 or type(manifest.get('field')) is not int or manifest['field']!=2:
  raise ValueError('wrong native corpus contract')
 root=Path(campaign_root).resolve();auth=manifest['authority']
 base,receipt=authenticate_base(auth['base_prepared']['path'],auth['base_prepared']['sha256'],auth['anchors']['path'],
  auth['anchors']['sha256'],auth['approved_root'],scratch,guard)
 anchors=strict_load(freeze(auth['anchors'],'source-anchors'))
 known={(row['sha256'],row['identity']['rl_source_sha256']):row for row in anchors['known_input_train_states']}
 prohibited=set(anchors['prohibited_identities']['heldout'])|set(anchors['prohibited_identities']['evaluation'])
 approval=strict_load(freeze(auth['root_source_approval'],'root-source-approval'))
 if approval.get('approved_manifest_sha256')!=auth['anchors']['sha256'] or approval.get('heldout_evaluation_excluded') is not True:raise ValueError('root source eligibility approval differs')
 if set(manifest['runs'])-set(ALLOWED_RUNS):raise ValueError('unapproved native producer family')
 contexts={}
 for name,run in manifest['runs'].items():
  guard('pre_native_provenance')
  directory=Path(run['directory']).resolve()
  if directory!=root/name:raise ValueError('producer outside explicit C7 run')
  m=strict_load(freeze(run['manifest'],name+'-manifest'));summary=strict_load(freeze(run['summary'],name+'-summary'))
  input_raw=freeze(run['input'],name+'-input');input_atoms,_=parse_json_candidate(input_raw)
  input_id=identities(input_atoms);key=(raw_sha(input_raw),input_id['rl_source_sha256'])
  if key not in known:raise ValueError('native input is not an authoritative original train root')
  if input_id['rl_source_sha256'] in prohibited:raise ValueError('heldout/evaluation native root rejected')
  claimed=m.get('source_sha256',m.get('source',{}).get('raw_sha256'))
  if claimed!=key[0]:raise ValueError('producer source claim differs from exact train certificate')
  text=freeze(run['native_input'],name+'-native-input')
  if parse_native(text)!=input_atoms:raise ValueError('native input text differs from source certificate')
  expected_binary=BINARY_SHA.get(name,HOLD_BINARY_SHA)
  binary=freeze(run['binary'],name+'-binary')
  if raw_sha(binary)!=expected_binary or m['binary_sha256']!=expected_binary:raise ValueError('native binary differs from approved producer')
  command=summary.get('command',m.get('command'));pairs=command_pairs(command)
  if Path(command[0]).resolve()!=Path(run['binary']['path']).resolve() or Path(pairs['--input']).resolve()!=Path(run['native_input']['path']).resolve() or Path(pairs['--output']).resolve()!=directory/'native/walk':raise ValueError('native command source/output binding differs')
  if name=='baseline-native300-001':
   ready=strict_load(freeze(run['ready_manifest'],name+'-ready'))
   pins=ready['runtime_code_sha256']
   if m['code_sha256']!=pins['scripts/campaign_native_baseline7.py'] or ready['binary_sha256']!=expected_binary:raise ValueError('baseline ready/runtime binding differs')
   source_audit=freeze(run['source_audit'],name+'-source-audit')
   if raw_sha(source_audit)!=m['source_audit_sha256']:raise ValueError('baseline source audit differs')
  else:pins=m['runtime_code_sha256']
  if pins!=run['runtime_code_sha256']:raise ValueError('producer code registry differs')
  for relative,pin in pins.items():
   freeze(dict(path=str(Path(run['runtime_root'])/relative),sha256=pin),name+'-'+relative)
  cpp_pins=set()
  for cpp in run['cpp']:
   cpp_pins.add(raw_sha(freeze(cpp,name+'-cpp')))
  if PLUS_CPP_SHA not in cpp_pins or (name!='baseline-native300-001' and HOLD_CPP_SHA not in cpp_pins):raise ValueError('producer CPP closure missing')
  registry=strict_load(freeze(run['export_registry'],name+'-export-registry'))
  contexts[name]=(m,registry,known[key],directory)
 sources=manifest['selected']
 if any(type(row.get('rank')) is not int or row['rank'] not in (93,94) for row in sources):raise ValueError('literal93/94 source ranks required')
 counts=Counter(row['rank'] for row in sources)
 if len(sources)>36 or not 1<=counts[93]<=32 or not 1<=counts[94]<=4 or sum(counts.values())!=counts[93]+counts[94]:raise ValueError('native source rank/count policy violated')
 candidates=[];records=[];seen=set()
 for index,record in enumerate(sources):
  guard('pre_selected_native_source')
  name=record['run'];m,registry,source,directory=contexts[name]
  path=Path(record['path']).resolve()
  expected_dir=directory/('.raw-native-returns' if record['kind']=='native-text' else 'verified')
  if path.parent!=expected_dir:raise ValueError('selected export outside registered run namespace')
  raw=freeze(dict(path=str(path),sha256=record['raw_sha256']),f'export-{index:02d}')
  if record['kind']=='native-text':
   atoms=parse_native(raw)
   if registry.get(record['raw_sha256'])!=[record['raw_sha256'],record['rank']]:raise ValueError('raw export absent from pinned registry')
  elif record['kind']=='verified-json':
   atoms,value=parse_json_candidate(raw)
   if digest(value.get('metadata',{}).get('parent'))!=digest(m):raise ValueError('JSON export producer parent differs')
   table={row[0]:row for row in registry['certificates'][name]}
   entry=table.get(path.stem)
   if not entry or entry[1]!=record['raw_sha256'] or entry[2]!=record['rank']:raise ValueError('JSON export absent from pinned registry')
   prior=freeze(dict(path=str(path.with_name(path.stem+'.verification.json')),sha256=entry[3]),f'prior-check-{index:02d}')
   prior_report=strict_load(prior)
   if prior_report.get('valid') is not True or prior_report.get('rank')!=record['rank'] or prior_report.get('exact_entries_checked')!=15625:raise ValueError('prior export report inconsistent')
  else:raise ValueError('unknown native export encoding')
  identity=identities(atoms)
  if len(atoms)!=record['rank'] or identity['term_set_sha256']!=record['identity'] or identity['rl_source_sha256']!=record['rl_identity']:raise ValueError('native export canonical identity/rank differs')
  if identity['rl_source_sha256'] in prohibited:raise ValueError('heldout/evaluation identity collision excluded')
  if identity['term_set_sha256'] in seen:raise ValueError('duplicate corpus source')
  seen.add(identity['term_set_sha256']);candidate=candidate_from_atoms(atoms)
  primary=verify_candidate(candidate,random_trials=8,seed=index)
  encoded=(json.dumps(candidate,sort_keys=True,indent=2)+'\n').encode();independent=verify_bytes(encoded)
  guard('post_native_full15625_checks')
  if not primary['valid'] or primary['exact_entries_checked']!=15625 or not independent['valid'] or independent['exact_entries_checked']!=15625 or independent['essential_rank']!=len(atoms):raise ValueError('fresh native full-tensor verification failed')
  candidates.append(candidate);records.append(dict(index=index,rank=len(atoms),identity=identity,run=name,
   native_root_id=source['id'],producer_manifest_sha256=manifest['runs'][name]['manifest']['sha256'],
   raw_sha256=record['raw_sha256'],canonical_certificate_sha256=raw_sha(encoded),primary=primary,independent=independent))
 native_receipt=NativeReceipt(manifest_sha256,receipt.base_prepared_sha256,receipt.source_manifest_sha256,
  tuple(row['raw_sha256'] for row in records),tuple(row['native_root_id'] for row in records))
 return candidates,records,base,native_receipt


def build_prepared(candidates,source_records,source_manifest_sha256,old406,guard=None,receipt=None):
 production=bool(candidates and candidates[0].get('dimension')==5)
 if production:
  if not isinstance(receipt,NativeReceipt) or receipt.sources_manifest_sha256!=source_manifest_sha256 or receipt.export_raw_hashes!=tuple(row['raw_sha256'] for row in source_records):raise ValueError('native production build requires fresh authenticated source receipt')
 document=prepare(candidates,cap=5000,guard=guard)
 document['schema']=PREPARED_SCHEMA
 old={tuple(a) for a in old406['atoms']};new={tuple(a) for a in document['atoms']}
 cycles=[int(z,16) for z in document['kernel_hex']]
 document.update(source_manifest_sha256=source_manifest_sha256,source_records=source_records,
  seed_rank_policy='Only fresh verified native93/94 train descendants',parity_broken=any(z.bit_count()&1 for z in cycles),
  old406_comparison=dict(old_atoms=len(old),shared_atoms=len(old&new),new_atoms=len(new-old),old_atoms_not_selected=len(old-new)),
  scope='Exact whole native-export atom code; no source inventory rank, novelty or lower-minimum claim.')
 document['native_source_receipt']=json.loads(json.dumps(asdict(receipt))) if receipt else None
 if production and set(document['seed_weights'])!={93,94}:raise ValueError('production native corpus must contain both verified93 and94')
 if not document['parity_broken']:raise AssertionError('verified93/94 feasible states require an odd kernel direction')
 return document


def load_root_pinned_native(prepared_path,prepared_sha256,manifest_path,manifest_sha256,campaign_root,scratch,freeze,guard):
 raw=Path(prepared_path).read_bytes();manifest_raw=Path(manifest_path).read_bytes()
 if raw_sha(raw)!=prepared_sha256 or raw_sha(manifest_raw)!=manifest_sha256:raise ValueError('native prepared/manifest root pin differs')
 manifest=strict_load(manifest_raw)
 candidates,records,old,receipt=load_sources(manifest,manifest_sha256,campaign_root,scratch,freeze,guard)
 expected=build_prepared(candidates,records,manifest_sha256,old,guard,receipt)
 document=strict_load(raw)
 if digest(document)!=digest(expected):raise ValueError('native prepared differs from authenticated complete reconstruction')
 return document
