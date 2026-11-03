"""Query-free preparation of four disabled, hash-pinned hold-rank pilot jobs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from scripts import campaign_native_dwell_hold_rank as pilot


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--prior-ready',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    campaign=a.campaign.resolve();prior=a.prior_ready.resolve();ready=a.output_dir.resolve()
    if not ready.is_relative_to(campaign) or ready.exists():raise ValueError('new campaign prep directory required')
    old,_=pilot.base.read(prior/'plan.json')
    if old.get('heldout_declaration_sha256')!=pilot.base.sha((prior/'heldout-declaration.json').read_bytes()):raise ValueError('prior declaration pin differs')
    ready.mkdir(parents=True);code=pilot.runtime_hashes()
    for name in code:pilot.base.freeze(ready/'code'/name,(ROOT/name).read_bytes())
    for name in ['tests/test_native_dwell_hold_rank.py','tests/test_campaign_native_dwell_hold_rank.py','scripts/prepare_native_dwell_hold_rank.py']:
        pilot.base.freeze(ready/'code'/name,(ROOT/name).read_bytes())
    binary=ready/'native/hold-rank-worker';binary.parent.mkdir()
    subprocess.run(['g++','-std=c++17','-O2',str(ready/'code/native/flip_worker_dwell_hold_rank.cpp'),'-o',str(binary)],check=True,timeout=30)
    binary.chmod(0o555);binary_sha=pilot.base.sha(binary.read_bytes());runtime_sha=pilot.base.sha(pilot.base.raw_json(code))
    held=ready/'heldout-declaration.json';pilot.base.freeze(held,(prior/'heldout-declaration.json').read_bytes());held_sha=pilot.base.sha(held.read_bytes())
    sources={}
    for label in ['s01','s02']:
        item=next(x for x in old['sources'] if x['label']==label);origin=Path(item['path']);raw=origin.read_bytes()
        if pilot.base.sha(raw)!=item['raw_sha256']:raise ValueError('prior source raw pin differs')
        source=ready/'sources'/origin.name;pilot.base.freeze(source,raw)
        terms,metadata,_=pilot.base.validate_input(source,item['raw_sha256'],held,held_sha)
        independent=pilot.base.verify_bytes(raw)
        if not independent['valid'] or independent['exact_entries_checked']!=15625 or independent['essential_rank']!=93:raise ValueError('source independent verification failed')
        if metadata['source_term_hash']!=item['source_term_hash'] or metadata['term_set_sha256']!=item['term_set_sha256']:raise ValueError('prior source canonical pin differs')
        sources[label]={'label':label,'path':str(source),'prior_origin':str(origin),'prior_plan_sha256':pilot.base.sha((prior/'plan.json').read_bytes()),
                        'prior_source':item,'verification':metadata,'independent_verification':independent}
    jobs=[];arms=[]
    for label,flag in [('s01',0),('s02',1),('s01',1),('s02',0)]:
        seed=20261103123001 if label=='s01' else 20261103123002;source=sources[label]
        job_id=f'hold-rank-pilot-{label}-flag{flag}-K4-D128';output=campaign/job_id
        argv=['python3','-B',str(ready/'code/scripts/campaign_native_dwell_hold_rank.py'),
              '--campaign',str(campaign),'--input',source['path'],'--binary',str(binary),'--heldout-declaration',str(held),'--output-dir',str(output),
              '--expected-input-sha256',source['verification']['raw_sha256'],'--expected-binary-sha256',binary_sha,
              '--expected-heldout-sha256',held_sha,'--expected-runtime-sha256',runtime_sha,'--seconds','30','--cpu','3','--memory-mb','768',
              '--seed',str(seed),'--dwell-hold-rank',str(flag)]
        preview=subprocess.run([*argv,'--preview'],check=True,capture_output=True,timeout=30)
        value=json.loads(preview.stdout)
        if value['status']!='PREVIEW_ONLY' or value['zero_mutations'] is not True or output.exists():raise ValueError('preview was not query/mutation free')
        pilot.base.freeze(ready/'previews'/(job_id+'.json'),preview.stdout)
        job={'id':job_id,'enabled':False,'command':argv,'cpu':3,'memory_mb':768,'seconds':45};jobs.append(job)
        arms.append({'job_id':job_id,'source':label,'dwell_hold_rank':flag,'paired_seed':seed,'native_seconds':30,'output_dir':str(output)})
        pilot.base.freeze(ready/'jobs'/(job_id+'.json'),pilot.base.raw_json(job))
    plan={'format':'unlaunched-matched-dwell-hold-rank-pilot-v1','production_launched':False,'n5_target_queries_started':0,
          'root_approved':False,'status':'AWAITING_VERIFY_QA_AND_ROOT_REVIEW','arms':arms,'jobs':jobs,'sources':list(sources.values()),
          'binary_sha256':binary_sha,'runtime_sha256':runtime_sha,'runtime_code_sha256':code,'heldout_declaration_sha256':held_sha,
          'pairing':'Fresh paired seeds per source; s01 flag0 then1, s02 flag1 then0; exact prior approved training source bytes and heldout pins.',
          'policy':'K4/D128/H12/archive16, only dwelling flips have rank floor. Downward improving flips also deferred. Atomic rejected flips consume step/dwell tick. Restarts and UTC/wall caps bound search.',
          'readouts':['best/current/max rank and complete rank/excess residency','hold active/rejected-down/prevented-rank-loss/renewal/expiry/cap/restart counters','measured child CPU, full-tensor verified export diversity'],
          'claim':'Mechanics pilot only. No rank improvement or production advantage claim.'}
    pilot.base.freeze(ready/'plan.json',pilot.base.raw_json(plan))
    pilot.base.freeze(ready/'README.md',b'# Unlaunched dwell hold-rank pilot\n\nFour disabled jobs, CPU3/768MiB, 30s native and 45s outer each. Fresh paired seeds; source order counterbalances flag0/1. Root review and independent QA must precede production launch. All source bytes and lineage pins are retained. See plan.json.\n\nHold rejects downward flips during dwell, including improving flips. Plus and restart rank changes retain existing semantics. New native source only; frozen V44 and prior workers untouched.\n')
    hashes={str(path.relative_to(ready)):pilot.base.sha(path.read_bytes()) for path in ready.rglob('*') if path.is_file()}
    pilot.base.freeze(ready/'checksums.json',pilot.base.raw_json(hashes))
    pilot.base.freeze(ready/'READY.json',pilot.base.raw_json({'status':'UNLAUNCHED_AWAITING_VERIFY_QA_AND_ROOT_REVIEW','jobs':4,'all_disabled':True,'production93_queries_started':0,
        'plan_sha256':pilot.base.sha((ready/'plan.json').read_bytes()),'native_binary_sha256':binary_sha,'runtime_sha256':runtime_sha}))
    print(json.dumps({'ready':str(ready),'jobs':4,'production93_queries_started':0},sort_keys=True))

if __name__=='__main__':main()
