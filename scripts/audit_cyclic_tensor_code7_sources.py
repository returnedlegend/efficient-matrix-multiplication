"""Read-only eligibility/exactness audit of the three historical C3 seeds.

Reads only their root-approved training payloads after metadata/registry gates.
No orbit dictionary, column matrix, elimination, decoder or search is built.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.audit_burst_long42 import exact_check
from scripts.verify_record42_independent import verify_bytes
from mmsearch.verify import verify_candidate

SOURCE_HASHES=(
 '56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b',
 '897eb861a5df9fe79ca8cc875696f5b20afa23800e223e76655e8c437cab583f',
 '590f4968948970268b17b6dafd6a09534c44638db97ce6d80d6c7f66a2588b73')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def select(obj,selector):
 for key in selector:obj=obj[key]
 return obj

def audit(anchor_dir,approval_path,old_branch):
 manifest_path=anchor_dir/'manifest.json';mraw=manifest_path.read_bytes();manifest=json.loads(mraw);approval=read(approval_path)
 if approval['owner']!='root' or approval['approved_manifest_sha256']!=sha(mraw) or approval['heldout_evaluation_excluded'] is not True or 'known_input_train_states' not in approval['approved_groups']:raise ValueError('root source approval differs')
 registries={};pins={str(manifest_path.relative_to(ROOT)):sha(mraw),str(approval_path.relative_to(ROOT)):sha(approval_path.read_bytes())}
 for name in ['native_armed','native_initial_plan','v43_split','heldout_declaration']:
  item=manifest['registries'][name];path=Path(item['path']);payload=path.read_bytes()
  if sha(payload)!=item['sha256'] or sha(Path(item['origin_path']).read_bytes())!=item['origin_sha256']:raise ValueError('eligibility registry pin differs')
  registries[name]=json.loads(payload);pins[str(path.relative_to(ROOT))]=sha(payload)
 branch_path=old_branch/'manifest.json';branch_raw=branch_path.read_bytes();branch=json.loads(branch_raw);pins[str(branch_path.relative_to(ROOT))]=sha(branch_raw)
 if branch['cyclic'] is not True:raise ValueError('historical branch is not C3')
 blocked=set(manifest['prohibited_identities']['heldout'])|set(manifest['prohibited_identities']['evaluation'])
 if not blocked or set(registries['heldout_declaration']['heldout_source_term_hashes'])-blocked:raise ValueError('prohibited split identities missing')
 results=[]
 for digest in SOURCE_HASHES:
  anchor=next(item for item in manifest['known_input_train_states'] if item['sha256']==digest);node=manifest['nodes'][anchor['id']]
  if not all(anchor.get(k) is True and node.get(k) is True for k in ['root_approved_train','heldout_excluded','evaluation_excluded']):raise ValueError('source is not explicitly train approved')
  if node['node_type']!='native_initial_train' or node['parent_ids'] or anchor['id']!=anchor['root_id'] or anchor['id']!=node['root_id'] or node['split']!='train':raise ValueError('unknown ancestry root; defer')
  identity=anchor['identity']
  if identity!=node['identity'] or identity['rl_source_sha256'] in blocked:raise ValueError('prohibited source identity; defer')
  evidence=node['root_training_evidence'];armed=registries[evidence['approval_registry']];pool=select(registries[evidence['plan_registry']],evidence['selector']);train=select(registries[evidence['split_registry']],evidence['train_selector'])
  if evidence['approval_owner']!='root' or evidence['approval_sha256']!=manifest['registries'][evidence['approval_registry']]['sha256'] or evidence['plan_sha256']!=manifest['registries'][evidence['plan_registry']]['sha256']:raise ValueError('historical approval hash differs')
  if armed.get('owner')!='root' or armed.get('armed') is not True or armed.get('plan_sha256')!=evidence['plan_sha256']:raise ValueError('historical native root not armed')
  if pool['sha256']!=digest or pool['term_hash']!=identity['term_set_sha256'] or pool['rl_source_hash']!=identity['rl_source_sha256'] or evidence['train_identity']!=identity['rl_source_sha256'] or evidence['train_identity'] not in train:raise ValueError('train split/initial pool binding differs')
  prior=next(item for item in branch['sources'] if item['raw_sha256']==digest)
  path=Path(anchor['path']);payload=path.read_bytes();prior_path=Path(prior['path'])
  if sha(payload)!=digest or sha(prior_path.read_bytes())!=digest or sha(Path(node['origin_path']).read_bytes())!=digest:raise ValueError('training source byte pin differs')
  candidate=json.loads(payload);terms,packed=exact_check(payload);scalar=verify_bytes(payload);primary=verify_candidate(candidate,random_trials=0)
  rl_identity=sha(json.dumps(sorted(terms),separators=(',',':')).encode())
  if packed['term_set_sha256']!=identity['term_set_sha256'] or rl_identity!=identity['rl_source_sha256']:raise ValueError('canonical source identity differs')
  if not primary['valid'] or not scalar['valid'] or primary['exact_entries_checked']!=15625 or scalar['exact_entries_checked']!=15625 or scalar['essential_rank']!=93:raise ValueError('source exactness/rank differs')
  support=set(terms)
  if any((v,w,u) not in support for u,v,w in support):raise ValueError('known source is not C3')
  cubes=sorted(u for u,v,w in terms if u==v==w);nonfixed=(len(terms)-len(cubes))//3
  pins[str(path.relative_to(ROOT))]=digest
  results.append({'raw_sha256':digest,'path':str(path.relative_to(ROOT)),'root_id':anchor['root_id'],'ancestor_ids':[anchor['root_id']],'identity':identity,'eligibility':'ELIGIBLE_ROOT_APPROVED_TRAIN_NATIVE_ROOT','heldout_evaluation_ancestors':False,'historical_c3_branch_source':str(prior_path.relative_to(ROOT)),'rank':93,'fixed_cubes':len(cubes),'cube_masks':cubes,'nonfixed_orbits':nonfixed,'total_source_orbits':len(cubes)+nonfixed,'primary_full_entries':primary['exact_entries_checked'],'independent_full_entries':scalar['exact_entries_checked'],'source_matrix_or_dictionary_built':False})
 return {'format':'cyclic-tensor-code7-source-audit-v1','status':'ELIGIBLE_TRAIN_C3_SEEDS_IDENTIFIED_NO_DICTIONARY','sources':results,'selected_seed_raw_sha256':SOURCE_HASHES[0],'pins':pins,'approved_corpus_atom_count_from_manifest_only':manifest['atom_union_count_read_only'],'approved_corpus_payloads_read':3,'heldout_evaluation_payloads_read':0,'production_dictionary_builds':0,'production_decoder_or_search_calls':0,'limits':'This audit replays historical training-root authorization, train membership and prohibited identities for three existing approved roots. Future broader corpus use must replay every approved descendant edge and recheck root/config pins; unknown ancestry defers.'}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['anchor-dir','approval','old-branch','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();result=audit(a.anchor_dir.resolve(),a.approval.resolve(),a.old_branch.resolve())
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('xb') as stream:stream.write((json.dumps(result,sort_keys=True,indent=2)+'\n').encode())
 print(json.dumps({k:result[k] for k in ['status','selected_seed_raw_sha256','production_dictionary_builds','production_decoder_or_search_calls']},sort_keys=True))
if __name__=='__main__':main()
