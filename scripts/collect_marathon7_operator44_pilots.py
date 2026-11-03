"""Query-free C7 pilot audit; explicit roles, fresh outputs, no old42 writes.

Reuses reviewed metadata/statistics helpers. The collect body adapts the old
collector only for explicit C7 role mapping, complete native coverage, and
requiring completed/check-clean learned results before freezing a snapshot.
No policy fitting, tensor/native query, validation call or queue mutation.
"""
from __future__ import annotations
import argparse
import datetime as dt
import math
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.collect_operator44_pilots import (read,decode,sha,encoded,digest,atomic,
    freeze,budget_status,policy_checks,event_summary,collect_native)

ROLES={'marathon7-learned44-pilot450':None,'marathon7-frozen44-pilot450':'frozen',
       'marathon7-random44-pilot450':'random'}

def control_for_job(job):
    if job['id'] not in ROLES:raise ValueError('unreviewed C7 pilot id')
    role=ROLES[job['id']];argv=job['command']
    observed='random' if '--control' in argv and argv[argv.index('--control')+1]=='random' else 'frozen' if '--frozen' in argv else None
    if observed!=role:raise ValueError('job id/control flags differ')
    if '--resume' not in argv or '--main-cpu-budget' not in argv or argv[argv.index('--main-cpu-budget')+1]!='450':raise ValueError('pilot fork/budget differs')
    return role

def validate_inputs(campaign,runtime,proposal,output):
    campaign,runtime,proposal,output=[Path(p).resolve() for p in (campaign,runtime,proposal,output)]
    if not output.is_relative_to(campaign) or output==campaign or output.exists():raise ValueError('new output under C7 required')
    if campaign.name!='marathon7_20261103T122417Z':raise ValueError('explicit C7 only')
    for directory in (runtime,proposal):
        for name,wanted in read(directory/'checksums.json').items():
            path=(directory/name).resolve()
            if not path.is_relative_to(directory) or sha(path.read_bytes())!=wanted:raise ValueError('frozen input checksum differs: '+str(path))
    jobs=read(proposal/'proposed_pilot_jobs.json')['jobs']
    if len(jobs)!=3 or {job['id'] for job in jobs}!=set(ROLES):raise ValueError('exact three C7 pilot arms required')
    for job in jobs:control_for_job(job)
    return campaign,runtime,proposal,output

def collect(campaign, runtime, proposal, output):
    campaign, runtime, proposal, output = map(lambda p: Path(p).resolve(), (campaign, runtime, proposal, output))
    output.mkdir(parents=True, exist_ok=True)
    initial = read(runtime/'initial/checkpoint.json'); initial_schedule = read(runtime/'initial/checkpoint.schedule.json')
    binding = initial['operator44']['binding']; jobs = read(proposal/'proposed_pilot_jobs.json')['jobs']
    cache_path = output/'native-stats-cache.json'; cache = read(cache_path) if cache_path.exists() else {}
    rows = []; queue_state = read(campaign/'queue_state.json')
    for job in jobs:
        name = job['id']; directory = campaign/name; result_file = campaign/(name+'-job.result.json')
        result = read(result_file) if result_file.exists() else None
        control = control_for_job(job)
        events = event_summary(directory/'events.jsonl', initial, initial_schedule, control)
        references = events.pop('run_references'); missing = collect_native(references, binding, campaign, cache)
        native_rows = [cache[x['run_dir']] for x in references if x['run_dir'] in cache]
        checks = dict(events['checks']); checks['event_invariants'] = not events['errors']; checks['native_stats_complete'] = not missing
        row = {'job': name, 'queue_status': queue_state.get('jobs', {}).get(name, {}).get('status', 'queued'),
               'status': 'PENDING_OR_RUNNING', 'result': result, 'events': events, 'checks': checks,
               'native_stats': {'covered': len(native_rows), 'referenced': len(references), 'missing_run_paths': missing,
                   'all_available_checks_pass': all(all(x['checks'].values()) for x in native_rows),
                   'max_visited_by_action': {action:max(x['max_visited_rank'] for x in native_rows if x['action']==action)
                                           for action in sorted({x['action'] for x in native_rows})},
                   'histograms_are_descriptive_only': True}}
        cp_path, schedule_path = directory/'checkpoint.json', directory/'checkpoint.schedule.json'
        if cp_path.exists() and schedule_path.exists():
            cp_bytes, schedule_bytes = cp_path.read_bytes(), schedule_path.read_bytes()
            cp, schedule = decode(cp_bytes), decode(schedule_bytes)
            coherent = schedule.get('checkpoint_sha256') == sha(cp_bytes)
            if coherent:
                record = cp['state']['terminal'] or len(cp['best']) <= 92
                actual = schedule['record_cpu']-initial_schedule['record_cpu']
                row.update(status=budget_status(result, actual, record=record), actual_main_CPU=actual,
                    actual_recovery_CPU=schedule['recovery_cpu']-initial_schedule['recovery_cpu'], main_CPU_overshoot=max(0., actual-450),
                    updates_before=initial['policy']['updates'], updates_after=cp['policy']['updates'],
                    checkpoint_sha256=sha(cp_bytes), schedule_sha256=sha(schedule_bytes),
                    full_policy_sha256=digest(cp['policy']))
                checks.update(policy_checks(initial['policy'], cp['policy'], control))
                checks.update(checkpoint_schedule_coherent=True,
                    operator_identity=cp.get('operator44') == initial['operator44'] == schedule.get('operator44'),
                    phase_clock_and_lineage=cp.get('finetune43') == initial['finetune43'] == schedule.get('finetune43'),
                    pool_and_operator_identity=cp.get('pool_curriculum') == initial['pool_curriculum'] == schedule.get('pool_context'),
                    main_CPU_accounting=math.isclose(actual, schedule['invocation_main_cpu'], abs_tol=1e-7),
                    CPU_counters_monotone=actual>=0 and schedule['recovery_cpu']>=initial_schedule['recovery_cpu'],
                    restart_seeds_and_interval=all(cp['restart_curriculum'][k] == initial['restart_curriculum'][k] for k in ('seed_order','interval_cpu','dimension','known_rank')),
                    restart_count_monotone=cp['restart_curriculum']['restarts']>=initial['restart_curriculum']['restarts'],
                    novelty_cap_preserved=cp['context']['ledger']['cap']==initial['context']['ledger']['cap'] and initial['context']['ledger']['paid']<=cp['context']['ledger']['paid']<=cp['context']['ledger']['cap'],
                    main_steps_monotone=cp['state']['steps']>=initial['state']['steps'],
                    architecture_20_32_14=len(cp['policy']['params']['W'])==20 and cp['policy']['hidden']==32 and cp['actions']==initial['actions'],
                    native_action_cap_checks=row['native_stats']['all_available_checks_pass'])
                if row['status']=='CPU_TARGET_COMPLETED' and all(checks.values()) and not control:
                    destination = output/'learned-frozen'
                    copies = {}
                    for source in [cp_path, schedule_path, directory/'best.json', directory/'best.verification.json',
                                   directory/'best.verify.py', result_file]:
                        if source.is_file():
                            payload = source.read_bytes(); label = 'job.result.json' if source==result_file else source.name
                            freeze(destination/label, payload); copies[label] = {'source':str(source),'sha256':sha(payload)}
                    freeze(destination/'snapshot.json', encoded({'job':name,'status':row['status'],'copies':copies,
                        'validation_launch_authorized':False,'query_free':True}))
                    row['learned_snapshot'] = str(destination)
            elif result:
                checks['checkpoint_schedule_coherent'] = False; row['status'] = 'INCOHERENT_FINAL_CHECKPOINT'
            else: row['checkpoint_publication_in_progress'] = True
        row['all_available_checks_pass'] = all(checks.values())
        rows.append(row)
    quarantine = runtime/'initial/pending-v43.json'
    report = {'format':'query-free-marathon7-operator44-pilot-collection-v1','utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'collector_sha256':sha(Path(__file__).read_bytes()),'runtime_manifest_sha256':sha((runtime/'manifest.json').read_bytes()),
              'proposal_sha256':sha((proposal/'proposed_pilot_jobs.json').read_bytes()),
              'quarantine_unchanged':sha(quarantine.read_bytes())==initial['operator44']['quarantine_sha256'],
              'all_three_CPU_targets_completed':all(x['status']=='CPU_TARGET_COMPLETED' for x in rows),
              'all_available_checks_pass':all(x['all_available_checks_pass'] for x in rows),
              'pilots':rows,'no_native_or_tensor_queries':True,'validation_launched':False,'promotion_authorized':False,
              'limits':'Checks metadata,state and existing proofs only; no independent tensor reconstruction. Wall-censored clean exits are UNKNOWN,not matched450CPU trials. Missing archived stats remain explicit. No learning advantage inferred.'}
    atomic(cache_path, cache); atomic(output/'REPORT.json', report)
    text = 'Isolated V44 pilot collection (read only; no native or tensor queries).\n\n'
    for row in rows:
        text += f"{row['job']}: {row['status']}; main CPU {row.get('actual_main_CPU','pending')}; recovery CPU {row.get('actual_recovery_CPU','pending')}; checks {'pass' if row['all_available_checks_pass'] else 'pending/fail'}.\n\n"
    text += 'Validation is unlaunched and promotion is unauthorized. Clean exits below450mainCPU remain wall-censored UNKNOWN. Full Adam/policy controls,clock/operator identities,stats coverage and immutable learned snapshot are reported in REPORT.json.\n'
    (output/'REPORT.md').write_text(text)
    return report

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('campaign','runtime','proposal','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(argv);paths=validate_inputs(a.campaign,a.runtime,a.proposal,a.output)
    report=collect(*paths)
    print(encoded({'all_three_CPU_targets_completed':report['all_three_CPU_targets_completed'],
        'all_available_checks_pass':report['all_available_checks_pass'],
        'pilots':[{k:row.get(k) for k in ('job','status','actual_main_CPU','actual_recovery_CPU','updates_before','updates_after','all_available_checks_pass')} for row in report['pilots']],
        'report':str(paths[-1]/'REPORT.json'),'validation_launched':False}).decode())
    return 0 if report['all_three_CPU_targets_completed'] and report['all_available_checks_pass'] and report['quarantine_unchanged'] else 2

if __name__=='__main__':raise SystemExit(main())
