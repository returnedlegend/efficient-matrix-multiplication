"""Authenticate frozen corpus, freeze eight derived sources and four disabled jobs."""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch import native_xor3_source7 as source
from mmsearch.tensor_code7_native_corpus import load_root_pinned_native
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts import campaign_native_portfolio7 as p
from scripts.phase_coordinator42_v2 import validate_job

def freeze(path,raw):p.safe.base.freeze(path,raw)
def prepare(campaign,bundle):
    campaign,bundle=campaign.resolve(),bundle.resolve()
    if bundle.exists()or bundle.parent!=campaign:raise ValueError('exclusive new direct bundle required')
    started=time.monotonic();cpu=time.process_time();guard=p.CampaignGuard(120,p.DEADLINE,(),campaign/'operations-v3/state.json',campaign_dir=campaign)
    guard.check('pre_xor3_authority_reconstruction');poller=CancelPoller(guard)
    def check(stage='loop'):
        if stage.startswith(('pre_','post_')):guard.check(stage)
        elif poller.cancelled():guard.check(stage)
    prepared_path=campaign/'tensor-code-native-corpus-prep-001/prepared.json'
    sources_path=campaign/'tensor-code-native-corpus-sources-v1/sources.json'
    anchors_path=campaign/'tensor-code-source-anchors-v1/manifest.json'
    if source.sha(prepared_path.read_bytes())!=source.PREPARED_SHA or source.sha(sources_path.read_bytes())!=source.SOURCES_SHA or source.sha(anchors_path.read_bytes())!=source.ANCHORS_SHA:raise ValueError('root-approved authority bytes changed')
    # Use the existing reviewed, exact native corpus provenance reconstruction.
    launch=json.loads((prepared_path.parent/'launch.json').read_bytes())
    for name,pin in launch['code_sha256'].items():
        if source.sha((ROOT/name).read_bytes())!=pin:raise ValueError('original authenticating source changed:'+name)
    bundle.mkdir();blobs=bundle/'authentication/blobs';blobs.mkdir(parents=True);provenance={}
    def freeze_record(record,label):
        path=Path(record['path']).resolve();raw=path.read_bytes();pin=source.sha(raw)
        if pin!=record['sha256']:raise ValueError('parent provenance bytes differ:'+label)
        freeze(blobs/pin,raw);provenance[str(path)]=dict(sha256=pin,snapshot='authentication/blobs/'+pin,label=label)
        return raw
    scratch=bundle/'authentication/replay';scratch.mkdir()
    prepared=load_root_pinned_native(prepared_path,source.PREPARED_SHA,sources_path,source.SOURCES_SHA,campaign,scratch,freeze_record,check)
    guard.check('post_complete_authority_reconstruction')
    freeze(bundle/'authority/prepared.json',prepared_path.read_bytes());freeze(bundle/'authority/native-sources.json',sources_path.read_bytes());freeze(bundle/'authority/anchors.json',anchors_path.read_bytes())
    receipt=dict(status='AUTHENTICATED_FULL_NATIVE_CORPUS_REPLAY',source_prepared_sha256=source.PREPARED_SHA,
        source_manifest_sha256=source.SOURCES_SHA,authority_anchors_sha256=source.ANCHORS_SHA,
        original_authenticating_code_sha256=launch['code_sha256'],authenticated_parent_count=36,
        source_records=prepared['source_records'],provenance=provenance,guard=guard.observation())
    freeze(bundle/'authority/authentication-receipt.json',source.encoded(receipt))
    original=campaign/'native-xor3-seed-scan-v1';scan=json.loads((original/'summary.json').read_bytes());rows=[]
    if scan['source_prepared_sha256']!=source.PREPARED_SHA or scan['native_queries']!=0 or len(scan['selected'])!=8:raise ValueError('qualified exact scan differs')
    for index,entry in enumerate(scan['selected']):
        raw=(original/entry['file']).read_bytes();proof=json.loads((original/f'seeds/seed-{index:02d}.proof.json').read_bytes())
        if source.sha(raw)!=entry['sha256']:raise ValueError('selected derived bytes changed')
        filename=f'seeds/seed-{index:02d}.json';freeze(bundle/filename,raw)
        rows.append(dict(index=index,file=filename,sha256=entry['sha256'],identity=source.identity(p.safe.base.canonical_terms(json.loads(raw))),
            initial_rank=entry['input_rank'],reduced_rank=entry['reduced_rank'],parent_indices=entry['parents'],
            parent_records=[prepared['source_records'][i]for i in entry['parents']],reduction_moves=proof['moves']))
    authority={name:dict(file=file,sha256=source.sha((bundle/file).read_bytes()))for name,file in[
        ('prepared','authority/prepared.json'),('native_sources','authority/native-sources.json'),('anchors','authority/anchors.json'),('authentication_receipt','authority/authentication-receipt.json')]}
    contract=dict(schema=source.SCHEMA,dimension=5,field=2,authority=authority,sources=rows,
        scope='Only exact three-distinct-parent XOR from root-authenticated36 train descendants, then deterministic exact shared-two-factor fixpoint; no unknown edges or mathematical novelty claim.')
    source.schema_check(contract);freeze(bundle/'sources.json',source.encoded(contract));contract_sha=source.sha((bundle/'sources.json').read_bytes())
    def fresh(stage):guard.check(stage);return True
    receipts=[]
    for index in range(8):
        terms,verified=source.load_source(bundle,contract_sha,index,fresh);receipts.append(verified)
        freeze(bundle/f'verification/source-{index:02d}.json',source.encoded(verified))
    # Runtime closure is the union of two immutable, already audited closures.
    shutil.copytree(campaign/'native-bandit7-ready-v5/code',bundle/'code')
    for old in sorted((prepared_path.parent/'code').rglob('*')):
        if not old.is_file():continue
        target=bundle/'code'/old.relative_to(prepared_path.parent/'code')
        if target.exists():
            if target.read_bytes()!=old.read_bytes():raise ValueError('audited dependency closure conflict:'+str(target))
        else:freeze(target,old.read_bytes())
    for name in ['mmsearch/compact_xor3_seed7.py','mmsearch/native_xor3_source7.py','mmsearch/marathon7_cancel_poller.py',
                 'scripts/campaign_native_xor3_7.py','scripts/prepare_native_xor3_7.py','tests/test_compact_xor3_seed7.py','tests/test_native_xor3_source7.py']:
        target=bundle/'code'/name
        if target.exists()and target.read_bytes()!=(ROOT/name).read_bytes():raise ValueError('new dependency collision')
        freeze(target,(ROOT/name).read_bytes())
    binary=campaign/'native-bandit7-ready-v5/native/plus-burst-worker';raw=binary.read_bytes()
    if source.sha(raw)!=p.BINARY_SHA:raise ValueError('audited binary differs')
    p.safe.base.freeze(bundle/'native/plus-burst-worker',raw,True)
    selected=[1,3,4,7];settings=[(1,2000),(4,20000),(4,200000),(1,200000)]
    used={p.safe.SEED};used.update(json.loads((campaign/'native-bandit7-e08/checkpoint.json').read_bytes())['used_seeds'])
    used.update(row['seed']for row in json.loads((campaign/'native-portfolio7-ready-v1/manifest.json').read_bytes())['profiles'])
    profiles=[]
    for number,(index,(burst,cadence))in enumerate(zip(selected,settings,strict=True),1):
        seed=(int(source.sha(f'native-xor3-v1:{number}:{rows[index]["sha256"]}'.encode())[:16],16)&((1<<62)-1))|(1<<62)
        if seed in used:raise ValueError('old/native seed replay forbidden')
        used.add(seed);name=f'native-xor3-p{number:02d}'
        profile=p.validate_profile(dict(id=name,source_id=index,seed=seed,cyclic=False,plus_burst=burst,reduction_dwell=128,plus_every=cadence))
        profiles.append(dict(id=name,source_index=index,input_rank=rows[index]['reduced_rank'],profile=profile))
    files={str(path.relative_to(bundle)):source.sha(path.read_bytes())for path in sorted(bundle.rglob('*'))if path.is_file()}
    manifest=dict(schema='native-xor3-plateau7.v1',campaign=str(campaign),campaign_sha256=source.sha((campaign/'campaign.json').read_bytes()),
        source_contract_sha256=contract_sha,source_files={str(row['index']):row['file']for row in rows},profiles=profiles,files=files,
        cpu=2,memory_mb=1024,native_seconds=180,outer_seconds=210,max_rank=135,archive_cap=16,total_output_cap_bytes=150*1024**2,
        scope='Four newly derived starts; initial16 gate and previous runtimes unchanged; no novelty or global rank bound.')
    freeze(bundle/'manifest.json',source.encoded(manifest));pin=source.sha((bundle/'manifest.json').read_bytes());jobs=[]
    for row in profiles:
        job=dict(id=row['id'],cpu=2,memory_mb=1024,seconds=210,enabled=False,
            command=[sys.executable,'-B',str(bundle/'code/scripts/campaign_native_xor3_7.py'),'--bundle',str(bundle),
                '--manifest-sha256',pin,'--job-id',row['id'],'--output-dir',str(campaign/row['id'])])
        validate_job(job);jobs.append(job)
    freeze(bundle/'jobs-four-disabled.json',source.encoded(dict(jobs=jobs)));guard.check('post_derived_source_freeze')
    return dict(status='PREPARED_QUALIFIED_NO_NATIVE_QUERY',bundle=str(bundle),manifest_sha256=pin,
        source_contract_sha256=contract_sha,proposal_sha256=source.sha((bundle/'jobs-four-disabled.json').read_bytes()),
        source_count=8,qualified_ranks=[row['reduced_rank']for row in rows],profiles=profiles,code_files=len(files),
        elapsed_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,guard=guard.observation())

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args();os.sched_setaffinity(0,{1});resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if os.getpriority(os.PRIO_PROCESS,0)<10:os.nice(10-os.getpriority(os.PRIO_PROCESS,0))
    print(json.dumps(prepare(args.campaign,args.bundle),sort_keys=True))

if __name__=='__main__':main()
