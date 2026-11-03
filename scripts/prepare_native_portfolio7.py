"""Freeze six approved 120-second profiles; preparation never launches native search."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from scripts import campaign_native_portfolio7 as p
from scripts.phase_coordinator42_v2 import validate_job

ANCHOR_SHA = '26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8'
GUARD_SHA = '09ac03c4ac1123eeb2ddba8a72653cc299aca052df9ad6c82ad618ed5cbd5cd9'
BASE_SHA = '37d8da3074517dda178b90369fab1817db998a1df6f3d89edcc1b87898bba54d'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(raw)

def profiles():
    settings = [(0,True,1,0,2000),(2,True,4,128,20000),(3,True,4,0,200000),
                (1,False,1,128,2000),(5,False,4,128,200000),(14,False,4,0,20000)]
    return [p.validate_profile(dict(id=f'native-portfolio7-p{i:02d}', source_id=source,
                seed=20261103140900+i, cyclic=cyclic, plus_burst=burst,
                reduction_dwell=dwell, plus_every=cadence))
            for i,(source,cyclic,burst,dwell,cadence) in enumerate(settings,1)]

def prepare(campaign, bundle):
    campaign, bundle = campaign.resolve(), bundle.resolve()
    if bundle.exists() or bundle.parent != campaign:
        raise ValueError('exclusive new direct campaign bundle required')
    anchor_path = campaign/'tensor-code-source-anchors-v1/manifest.json'
    anchor_raw = anchor_path.read_bytes()
    if sha(anchor_raw) != ANCHOR_SHA: raise ValueError('approved anchors differ')
    anchor = json.loads(anchor_raw)
    registries = {}
    for name in ['native_armed','native_initial_plan','v43_split','heldout_declaration']:
        record = anchor['registries'][name]
        raw = Path(record['path']).read_bytes()
        if sha(raw) != record['sha256']: raise ValueError('registry differs')
        registries[name] = json.loads(raw)
    if not registries['native_armed']['armed'] or registries['native_armed']['owner'] != 'root':
        raise ValueError('root armed training pool required')
    prohibited = set(anchor['prohibited_identities']['heldout']) | set(anchor['prohibited_identities']['evaluation'])
    audits, sources = {}, {}
    for profile in profiles():
        index = profile['source_id']; entry = anchor['known_input_train_states'][index]
        node = anchor['nodes'][entry['id']]; raw = Path(node['path']).read_bytes()
        candidate = json.loads(raw); terms = p.safe.base.canonical_terms(candidate)
        identity = p.lifecycle.digest(sorted(terms))
        if (sha(raw) != node['sha256'] or node['parent_ids'] or node['parent_files']
                or node['node_type'] != 'native_initial_train' or node['root_id'] != node['id']
                or node['root_approved_train'] is not True or node['split'] != 'train'
                or node['heldout_excluded'] is not True or node['evaluation_excluded'] is not True
                or identity != node['identity']['rl_source_sha256']
                or p.lifecycle.term_identity(candidate) != node['identity']['term_set_sha256']
                or set(node['identity'].values()) & prohibited):
            raise ValueError('source is not an approved closed training root')
        evidence = node['root_training_evidence']
        pool = registries['native_initial_plan']['initial_pool'][index]
        if (evidence['approval_owner'] != 'root' or evidence['selector'] != ['initial_pool',index]
                or evidence['approval_sha256'] != anchor['registries']['native_armed']['sha256']
                or evidence['plan_sha256'] != anchor['registries']['native_initial_plan']['sha256']
                or registries['native_armed']['plan_sha256'] != evidence['plan_sha256']
                or pool['sha256'] != node['sha256'] or pool['term_hash'] != node['identity']['term_set_sha256']
                or pool['rl_source_hash'] != identity or identity not in registries['v43_split']['v43_source_split']['train']):
            raise ValueError('root training declaration is not bound to input')
        first = p.safe.verify_candidate(candidate, random_trials=0); second = p.safe.independent(candidate, raw)
        cyclic = p.c3_closed(terms)
        if (not first['valid'] or not second['valid'] or second['essential_rank'] != 93
                or first['exact_entries_checked'] != 15625 or second['exact_entries_checked'] != 15625
                or profile['cyclic'] and not cyclic):
            raise ValueError('exact source or cyclic precondition failed')
        rel = f'sources/train-{index:02d}-{node["sha256"]}.json'
        sources[str(index)] = dict(file=rel,sha256=node['sha256'],node_id=node['id'])
        audits[str(index)] = dict(eligibility='ELIGIBLE_ROOT_APPROVED_TRAIN_NATIVE_ROOT',raw_sha256=sha(raw),
            identity=node['identity'],root_id=node['root_id'],parent_ids=[],parent_files=[],
            heldout_evaluation_ancestors=False,root_training_evidence=evidence,cyclic_complete=cyclic,
            primary=first,independent=second)
    # All validation above precedes the first write. No production child here.
    bundle.mkdir()
    shutil.copytree(campaign/'baseline-native300-ready-v1/code',bundle/'code')
    if sha((bundle/'code/scripts/campaign_native_baseline7.py').read_bytes()) != BASE_SHA:
        raise ValueError('safe baseline changed')
    for name in ['scripts/campaign_native_portfolio7.py','scripts/prepare_native_portfolio7.py',
                 'tests/test_campaign_native_portfolio7.py','mmsearch/marathon7_cached_guard.py']:
        raw = (ROOT/name).read_bytes()
        if name.endswith('marathon7_cached_guard.py') and sha(raw) != GUARD_SHA: raise ValueError('approved cached guard differs')
        write(bundle/'code'/name,raw)
    write(bundle/'provenance/approved-anchor-manifest.json',anchor_raw)
    for name in registries:
        write(bundle/'provenance'/f'{name}.json',Path(anchor['registries'][name]['path']).read_bytes())
    for index, source in sources.items():
        write(bundle/source['file'],Path(anchor['known_input_train_states'][int(index)]['path']).read_bytes())
    binary = ROOT/'artifacts/rl_campaign42_20261103T033116Z/plus-burst42-pilot-ready-v1/native/plus-burst-worker'
    raw = binary.read_bytes()
    if sha(raw) != p.BINARY_SHA: raise ValueError('native binary differs')
    write(bundle/'native/plus-burst-worker',raw); (bundle/'native/plus-burst-worker').chmod(0o755)
    write(bundle/'source-audit.json',encoded(dict(anchor_manifest_sha256=ANCHOR_SHA,sources=audits,
        native_queries=0,heldout_policy='Closed initial training roots only; no unknown ancestry edges.')))
    files = {str(path.relative_to(bundle)):sha(path.read_bytes()) for path in sorted(bundle.rglob('*')) if path.is_file()}
    manifest = dict(schema='native-portfolio7.v1',campaign=str(campaign),campaign_sha256=sha((campaign/'campaign.json').read_bytes()),
        profiles=profiles(),sources=sources,files=files,deadline=p.DEADLINE,cpu=0,memory_mb=768,
        native_seconds=120,outer_seconds=150,archive_cap=16,total_output_cap_bytes=150*p.MIB,
        guard_sha256=GUARD_SHA,baseline_sha256=BASE_SHA,anchor_manifest_sha256=ANCHOR_SHA,
        math_semantics='Original exact plus-burst binary; reduction-dwell, not hold-rank.',
        schedule='First five then reserved bounded corpus-preparation gap then sixth; no automatic continuation.')
    raw = encoded(manifest); write(bundle/'manifest.json',raw); manifest_sha = sha(raw)
    jobs = []
    for profile in profiles():
        job = dict(id=profile['id'],cpu=0,memory_mb=768,seconds=150,enabled=False,
            command=[sys.executable,'-B',str(bundle/'code/scripts/campaign_native_portfolio7.py'),
                '--bundle',str(bundle),'--expected-manifest-sha256',manifest_sha,
                '--profile-id',profile['id'],'--output-dir',str(campaign/profile['id'])])
        validate_job(job); jobs.append(job)
    for filename, selected in [('jobs-six-disabled.json',jobs),('jobs-first-five.json',jobs[:5]),('job-six-reserved.json',jobs[5:])]:
        write(bundle/filename,encoded(dict(jobs=selected)))
    pins = {str(path.relative_to(bundle)):sha(path.read_bytes()) for path in sorted(bundle.rglob('*')) if path.is_file()}
    write(bundle/'checksums.json',encoded(pins))
    return dict(bundle=str(bundle),manifest_sha256=manifest_sha,files=len(files),pins=pins,
        profiles=profiles(),native_queries=0,status='PREPARED_DISABLED')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args(); result=prepare(args.campaign,args.bundle)
    print(json.dumps({k:v for k,v in result.items() if k!='pins'},sort_keys=True))

if __name__=='__main__':main()
