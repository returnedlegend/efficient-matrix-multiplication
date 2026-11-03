"""Query-free immutable source/policy/reward comparison pack for eight epochs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from scripts import campaign_native_bandit7 as b
from scripts.prepare_native_portfolio7 import ANCHOR_SHA,GUARD_SHA,BASE_SHA

def prepare(campaign,bundle,carry_checkpoint=None,carry_checkpoint_sha256=None,carry_manifest=None,carry_manifest_sha256=None):
    campaign,bundle=campaign.resolve(),bundle.resolve()
    if bundle.exists() or bundle.parent!=campaign:raise ValueError('new direct campaign bundle required')
    anchors=campaign/'tensor-code-source-anchors-v1';manifest=b.read_pin(anchors/'manifest.json',ANCHOR_SHA)
    # The owner's frozen trust-anchor loader replays the complete pinned graph.
    # It writes only temporary proof/source snapshots, not a dictionary or query.
    with tempfile.TemporaryDirectory(prefix='bandit7-source-proof-') as tmp:
        proof=Path(tmp)
        candidates,records,_=b.p.lifecycle.load_sources(SimpleNamespace(manifest=anchors/'manifest.json',
            manifest_sha256=ANCHOR_SHA,approved_root=anchors),proof,lambda _:None)
        sources={};known_hashes=set();known_atoms=set()
        selected=[(candidate,record) for candidate,record in zip(candidates,records) if record['source_group']=='native_initial_train']
        if len(selected)!=16:raise ValueError('exact frozen16 training roots required')
        for index,(candidate,record) in enumerate(selected):
            entry=manifest['known_input_train_states'][index];node=manifest['nodes'][entry['id']]
            if record['anchor_id']!=entry['id'] or node['parent_ids'] or node['parent_files'] or node['root_id']!=node['id']:
                raise ValueError('known source is not an initial training root')
            raw=(proof/record['snapshot']).read_bytes();terms=b.p.safe.base.canonical_terms(candidate)
            primary=b.p.safe.verify_candidate(candidate,random_trials=0);independent=b.p.safe.independent(candidate,raw)
            if not primary['valid'] or not independent['valid'] or independent['essential_rank']!=93 or primary['exact_entries_checked']!=15625 or independent['exact_entries_checked']!=15625:raise ValueError('source full checks failed')
            sources[str(index)]=dict(file=f'sources/train-{index:02d}.json',sha256=b.sha(raw),
                root_approved_train=True,heldout_evaluation_ancestors=False,cyclic_complete=b.p.c3_closed(terms),
                root_id=node['root_id'],identity=node['identity'],parent_ids=[],parent_files=[],
                source_anchor_manifest_sha256=ANCHOR_SHA,root_training_evidence=node['root_training_evidence'],
                primary=primary,independent=independent)
            known_hashes.add(b.p.safe.base.term_set_sha256(terms));known_atoms.update(terms)
        prior_pins={}
        for number in range(1,7):
            directory=campaign/f'native-portfolio7-p{number:02d}';raw=(directory/'summary.json').read_bytes();summary=json.loads(raw)
            if not b.completed_native(summary):raise ValueError('prior measured comparison is incomplete')
            prior_pins[str(directory/'summary.json')]=b.sha(raw)
            for digest,item in summary['raw_exports'].items():
                if item['rank']!=93:continue
                terms,text=b.p.safe.base.snapshot(directory/'.raw-native-returns'/(digest+'.txt'),5)
                if len(terms)!=93 or b.sha(text)!=item['raw_sha256'] or b.p.safe.base.term_set_sha256(terms)!=digest:raise ValueError('frozen comparison raw hash differs')
                known_hashes.add(digest);known_atoms.update(terms)
        bundle.mkdir();shutil.copytree(campaign/'native-portfolio7-ready-v1/code',bundle/'code')
        for name in ['scripts/campaign_native_bandit7.py','scripts/prepare_native_bandit7.py',
                     'scripts/phase_coordinator42_v2.py','scripts/append_campaign_jobs42.py',
                     'scripts/native_bandit7_controller.py','tests/test_campaign_native_bandit7.py','tests/test_native_bandit7_controller.py']:
            b.p.safe.base.freeze(bundle/'code'/name,(ROOT/name).read_bytes())
        if b.sha((bundle/'code/mmsearch/marathon7_cached_guard.py').read_bytes())!=GUARD_SHA or b.sha((bundle/'code/scripts/campaign_native_baseline7.py').read_bytes())!=BASE_SHA:raise ValueError('audited guard/handoff differs')
        shutil.copytree(proof/'inputs',bundle/'source-proof')
        for index,(_,record) in enumerate(selected):
            b.p.safe.base.freeze(bundle/sources[str(index)]['file'],(proof/record['snapshot']).read_bytes())
        native=campaign/'native-portfolio7-ready-v1/native/plus-burst-worker'
        raw=native.read_bytes()
        if b.sha(raw)!=b.p.BINARY_SHA:raise ValueError('binary differs')
        b.p.safe.base.freeze(bundle/'native/plus-burst-worker',raw,True)
        comparison=dict(schema='native-bandit7.comparison.v1',known_hashes=sorted(known_hashes),known_atoms=sorted(known_atoms),
            prior_summary_pins=prior_pins,source_anchor_sha256=ANCHOR_SHA,
            semantics='Conservative exclusion set of approved initial16 and sampled raw rank93 all-six states. Raw prior states excluded from rewards without claiming they were all doubleverified.')
        b.p.safe.base.freeze(bundle/'comparison.json',b.encoded(comparison));baseline_sha=b.sha((bundle/'comparison.json').read_bytes())
        carry=None
        if carry_checkpoint is not None:
            old_manifest=b.read_pin(carry_manifest,carry_manifest_sha256)
            carry=b.validate_state(b.read_pin(carry_checkpoint,carry_checkpoint_sha256),carry_manifest_sha256,baseline_sha)
            if old_manifest['baseline_sha256']!=baseline_sha or old_manifest['sources']!=sources or old_manifest['arms']!=b.ARMS or carry['completed_epochs']!=1:
                raise ValueError('exact epoch1 policy/source/comparison carry required')
            b.p.safe.base.freeze(bundle/'carry-checkpoint.raw',Path(carry_checkpoint).read_bytes())
            b.p.safe.base.freeze(bundle/'carry-manifest.raw',Path(carry_manifest).read_bytes())
        files={str(path.relative_to(bundle)):b.sha(path.read_bytes()) for path in sorted(bundle.rglob('*')) if path.is_file()}
        policy=dict(schema='native-bandit7.manifest.v1',campaign=str(campaign),campaign_sha256=b.sha((campaign/'campaign.json').read_bytes()),
            files=files,sources=sources,baseline_sha256=baseline_sha,arms=b.ARMS,max_epochs=8,sample_cap=32,
            cpu=2,memory_mb=768,native_seconds=180,outer_seconds=210,deadline=b.p.DEADLINE,
            total_output_cap_bytes=250*b.MIB,source_anchor_sha256=ANCHOR_SHA,guard_sha256=GUARD_SHA,
            policy_seed=20261103155217,exploration_reserved_epochs=[1,5],
            reward='0.5*(fresh doubleverified new rank93 states/32)+0.5*min(new whole atoms,512)/512; target<=92 dominates and stops.',
            stop_policy='No continuation after UNKNOWN, owned native error, malformed evidence, late guards, or incomplete final/sample verification.',
            launch_condition='Explicit CPU2 local-family retirement/reaping and fresh global campaign/resource checks.')
        if carry is not None:policy['carry']=dict(checkpoint_sha256=carry_checkpoint_sha256,manifest_sha256=carry_manifest_sha256,completed_epochs=1,unchanged_fields='All policy counts/rewards/context/RNG/accepted/observed/atoms/seeds; only runtime manifest binding and migration provenance change.')
        b.p.safe.base.freeze(bundle/'manifest.json',b.encoded(policy));pin=b.sha((bundle/'manifest.json').read_bytes())
        state=dict(schema='native-bandit7.checkpoint.v1',manifest_sha256=pin,baseline_sha256=baseline_sha,
            status='READY_NEXT_EPOCH',completed_epochs=0,counts=[0]*6,reward_sums=[0]*6,accepted_hashes=[],observed_hashes=[],
            contexts={key:dict(counts=[0]*6,reward_sums=[0]*6) for key in ['cyclic_source','noncyclic_source']},
            known_atoms=sorted(known_atoms),used_seeds=[],rng_state=random.Random(policy['policy_seed']).getstate())
        if carry is not None:
            state=json.loads(json.dumps(carry));state['manifest_sha256']=pin
            state['previous_runtime_manifest_sha256']=carry_manifest_sha256;state['previous_runtime_checkpoint_sha256']=carry_checkpoint_sha256
        b.p.safe.base.freeze(bundle/'initial-checkpoint.json',b.encoded(state));checkpoint_sha=b.sha((bundle/'initial-checkpoint.json').read_bytes())
        b.validate_state(json.loads(b.encoded(state)),pin,baseline_sha)
        first_epoch=state['completed_epochs']+1
        job=b.prepare_job(bundle,pin,bundle/'initial-checkpoint.json',checkpoint_sha,bundle/f'job-e{first_epoch:02d}-disabled.json')
        return dict(status='PREPARED_DISABLED_NO_QUERY',manifest_sha256=pin,initial_checkpoint_sha256=checkpoint_sha,
            first_proposal_sha256=job['proposal_sha256'],comparison_states=len(known_hashes),comparison_atoms=len(known_atoms),
            source_count=len(sources),files=len(files),bundle=str(bundle),choice=job['choice'])

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--campaign',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--carry-checkpoint',type=Path);parser.add_argument('--carry-checkpoint-sha256')
    parser.add_argument('--carry-manifest',type=Path);parser.add_argument('--carry-manifest-sha256')
    args=parser.parse_args();carry=[args.carry_checkpoint,args.carry_checkpoint_sha256,args.carry_manifest,args.carry_manifest_sha256]
    if any(carry) and not all(carry):parser.error('all four exact carry pins required')
    print(json.dumps(prepare(args.campaign,args.bundle,*carry),sort_keys=True))

if __name__=='__main__':main()
