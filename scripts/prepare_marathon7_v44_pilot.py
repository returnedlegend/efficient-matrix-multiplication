"""Prepare disabled C7 V44 jobs using the exact frozen runtime and phase023 fork."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True


def sha(raw):return hashlib.sha256(raw).hexdigest()
def raw(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def read(path):return json.loads(Path(path).read_bytes())
def freeze(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(value)
    path.chmod(0o444)
def checks(directory):
    declared=read(directory/'checksums.json')
    for name,digest in declared.items():
        if sha((directory/name).read_bytes())!=digest:raise ValueError('original checksum differs: '+str(directory/name))
    return declared

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['campaign','original-ready','original-proposal','output-dir']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();campaign=a.campaign.resolve();ready=a.original_ready.resolve();old=a.original_proposal.resolve();out=a.output_dir.resolve()
    if not out.is_relative_to(campaign) or out.exists():raise ValueError('new C7 proposal directory required')
    old_ready_hashes=checks(ready);old_proposal_hashes=checks(old)
    manifest=read(ready/'manifest.json');variant=read(old/'manifest.json');fork=ready/'initial/checkpoint.json';schedule=fork.with_suffix('.schedule.json');quarantine=ready/'initial/pending-v43.json'
    for name,path in [('initial_checkpoint_sha256',fork),('initial_schedule_sha256',schedule),('quarantine_sha256',quarantine)]:
        if sha(path.read_bytes())!=manifest[name] or manifest[name]!=variant[name]:raise ValueError('fork pin differs: '+name)
    runtime=manifest['runtime_code_sha256']
    for name,digest in runtime.items():
        if sha((ready/'code'/name).read_bytes())!=digest:raise ValueError('runtime differs: '+name)
    runtime_sha=sha(json.dumps(runtime,sort_keys=True,separators=(',',':')).encode())
    if runtime_sha!=manifest['runtime_sha256'] or runtime_sha!=variant['original_runtime_sha256']:raise ValueError('original runtime aggregate pin differs')
    checkpoint=read(fork);sched=read(schedule);boundary=checkpoint['operator44'];preserved=boundary['preserved_state_hashes'];preserved_checks={}
    for section,obj in [('checkpoint',checkpoint),('schedule',sched)]:
        for key,digest in preserved[section].items():
            actual=sha(raw(obj[key]))
            if actual!=digest:raise ValueError('preserved fork field differs: '+section+'.'+key)
            preserved_checks[section+'.'+key]=digest
    config=read(campaign/'campaign.json');deadline=datetime.datetime.fromisoformat(config['deadline_utc'].replace('Z','+00:00'))
    if config['dimension']!=5 or config['field']!=2 or config['target_rank']!=92:raise ValueError('C7 target differs')
    if datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=3*1230)>deadline:raise ValueError('three serial outer envelopes do not fit absolute C7 deadline')
    partial=ready.parent/'learned44-pilot450-v1';partial_events=partial/'events.jsonl';events=[json.loads(line) for line in partial_events.read_text().splitlines()]
    if (partial/'checkpoint.json').exists() or (partial/'checkpoint.schedule.json').exists():raise ValueError('old partial unexpectedly has resumable files; root must reconsider lineage')
    last=next(x for x in reversed(events) if 'record_cpu' in x)
    discarded={'path':str(partial),'events_sha256':sha(partial_events.read_bytes()),'event_lines':len(events),'resumable_checkpoint':False,
               'observed_main_cpu_seconds':last['record_cpu']-sched['record_cpu'],'observed_recovery_cpu_seconds':last['recovery_cpu']-sched['recovery_cpu'],
               'last_elapsed_seconds':last['elapsed_seconds'],'disposition':'Discarded experiment, separately accounted sunk work. New matched arms start from the same original phase023 fork. No continuation, resumed progress, reset novelty cap, debt forgiveness, or recovered optimizer/RNG claim.'}
    original=read(old/'proposed_pilot_jobs.json')['jobs'];jobs=[];diffs=[];preview_results=[]
    out.mkdir(parents=True)
    tracked={str(ready/name):digest for name,digest in old_ready_hashes.items()};tracked.update({str(old/name):digest for name,digest in old_proposal_hashes.items()});tracked[str(partial_events)]=discarded['events_sha256']
    tracked[str(ready/'checksums.json')]=sha((ready/'checksums.json').read_bytes());tracked[str(old/'checksums.json')]=sha((old/'checksums.json').read_bytes())
    for job,arm in zip(original,['learned','frozen','random']):
        if job['id']!=f'{arm}44-pilot450-v1' or job['cpu']!=0 or job['memory_mb']!=1024 or job['seconds']!=1230 or job['enabled'] is not False:raise ValueError('original job envelope differs')
        new=copy.deepcopy(job);new['id']=f'marathon7-{arm}44-pilot450';argv=new['command'];changes=[];output=campaign/new['id']
        if output.exists():raise ValueError('fresh arm output already exists')
        for key,name in [('--checkpoint','checkpoint.json'),('--output','best.json'),('--events','events.jsonl'),('--native-dir','native')]:
            index=argv.index(key)+1;prior=argv[index]
            if Path(prior).parent!=ready.parent/job['id']:raise ValueError('unexpected prior output path: '+key)
            argv[index]=str(output/name);changes.append({'argument':key,'old':prior,'new':argv[index]})
        expected=copy.deepcopy(job);expected['id']=new['id']
        for change in changes:expected['command'][expected['command'].index(change['argument'])+1]=change['new']
        if new!=expected:raise ValueError('non-output argument changed')
        for key,want in [('--resume',str(fork)),('--seconds','1200'),('--main-cpu-budget','450'),('--cpu','0')]:
            if argv[argv.index(key)+1]!=want:raise ValueError('immutable parameter differs: '+key)
        for key in ['--resume','--native-binary','--record-seed']:
            for index,value in enumerate(argv[:-1]):
                if value==key:tracked[argv[index+1]]=sha(Path(argv[index+1]).read_bytes())
        pool=Path(argv[argv.index('--recovery-pool')+1])/'manifest.json';tracked[str(pool)]=sha(pool.read_bytes())
        process=subprocess.run([*argv,'--preview'],capture_output=True,timeout=30)
        if process.returncode:raise RuntimeError('frozen CLI preview failed: '+process.stderr.decode())
        preview=json.loads(process.stdout)
        if preview['status']!='PREVIEW_ONLY' or preview['zero_mutations'] is not True or preview['native_queries']!=0 or preview['checkpoint_sha256']!=manifest['initial_checkpoint_sha256'] or output.exists():raise ValueError('preview invariant differs')
        freeze(out/'previews'/(new['id']+'.json'),process.stdout);freeze(out/'jobs'/(new['id']+'.json'),raw(new))
        jobs.append(new);diffs.append({'old_id':job['id'],'new_id':new['id'],'changes':changes,'only_id_and_four_output_paths_changed':True});preview_results.append({'id':new['id'],'exit_code':process.returncode,'preview':preview})
    if any(sha(Path(name).read_bytes())!=digest for name,digest in tracked.items()):raise ValueError('original input changed during preparation')
    if checks(ready)!=old_ready_hashes or checks(old)!=old_proposal_hashes:raise ValueError('original checksum declaration changed')
    freeze(out/'proposed_pilot_jobs.json',raw({'jobs':jobs}));freeze(out/'discarded_partial_experiment.json',raw(discarded))
    freeze(out/'source-pins.json',raw({'ready':str(ready),'proposal':str(old),'original_ready_checksums':old_ready_hashes,'original_proposal_checksums':old_proposal_hashes,'tracked_original_paths':tracked,'preserved_fork_field_hashes':preserved_checks}))
    report={'format':'marathon7-v44-three-arm-proposal-v1','status':'PREPARED_UNLAUNCHED_ROOT_REVIEW_REQUIRED','root_approved':False,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'campaign':str(campaign),'deadline_utc':config['deadline_utc'],'original_manifest_sha256':sha((ready/'manifest.json').read_bytes()),'original_variant_manifest_sha256':sha((old/'manifest.json').read_bytes()),
            'original_runtime_sha256':runtime_sha,'initial_checkpoint_sha256':manifest['initial_checkpoint_sha256'],'initial_schedule_sha256':manifest['initial_schedule_sha256'],'quarantine_sha256':manifest['quarantine_sha256'],
            'diff':diffs,'jobs':3,'all_disabled':True,'actual_frozen_cli_previews_passed':3,'preview_results':preview_results,'production_n5_queries_started':0,'queue_changes':0,'old42_writes':0,
            'fork_semantics':'All three arms load the same byte-identical phase023 V44 fork and schedule. Adam, RNG, debt, seed order, capped novelty, quarantine and runtime are retained. Prior learned partial experiment is discarded and separately accounted.',
            'main_cpu_budget_per_arm':450,'driver_wall_seconds':1200,'outer_wall_seconds':1230,'cpu':0,'memory_mb':1024,'scheduling':'Root must enqueue serially on CPU0. C7 queue/guard absolute deadline remains authoritative and must clamp jobs; no envelope may start if it cannot fit. Guard stops on fresh independently verified frozen record or deadline/resources.',
            'censoring':'If main CPU is below450 without a verified record when wall or campaign stop ends the arm, report UNKNOWN_WALL_CENSORED_CPU_TARGET_NOT_MET. Report actual main/auxiliary CPU and bounded overshoot. No automatic retry. Prior partial CPU is not matched completion.',
            'validation':'No validation or promotion launch is authorized by this proposal. Native hold-rank pilot package is unchanged.'}
    freeze(out/'manifest.json',raw(report));freeze(out/'prepare.py',Path(__file__).read_bytes())
    freeze(out/'README.md',b'# Fresh C7 V44 pilot proposal\n\nThree disabled jobs: marathon7-learned44-pilot450, marathon7-frozen44-pilot450, and marathon7-random44-pilot450. Each uses 450 measured main CPU seconds, 1200 driver wall seconds, 1230 outer wall seconds, CPU0 and 1024MiB. Root must review and enqueue serially; C7 guard and the absolute 2026-11-03T19:24:17Z deadline clamp execution.\n\nOnly job IDs and four output-bearing paths change from the frozen wall1200 proposal. Runtime, phase023 fork, seed order, Adam, RNG, debt, capped novelty, quarantine and all other arguments are unchanged. Three actual frozen CLI previews pass with no writes or native queries. Source pins and exact diffs are in source-pins.json and manifest.json.\n\nThe old learned partial experiment spent about27.27 main CPU seconds and1.52 recovery CPU seconds, but produced no resumable checkpoint. It is discarded experimental work, separately accounted. All new matched arms start from the same original fork. This is not a continuation or a claim of reset budgets, novelty or debt. See discarded_partial_experiment.json for exact measured values and event hash.\n\nNo queue edit, production launch, validation or promotion was performed. The native hold-rank ready package is unchanged.\n')
    freeze(out/'checksums.json',raw({str(path.relative_to(out)):sha(path.read_bytes()) for path in out.rglob('*') if path.is_file()}))
    print(json.dumps({'proposal':str(out),'status':report['status'],'actual_previews':3,'production_n5_queries_started':0,'original_runtime_sha256':runtime_sha,'discarded_main_cpu':discarded['observed_main_cpu_seconds']},sort_keys=True))

if __name__=='__main__':main()
