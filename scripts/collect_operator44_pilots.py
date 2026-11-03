"""Read-only artifact checks for the isolated V44 pilots; never runs a solver.

Writes only its own report/cache/learned snapshot directory. No training,
certificate tensor verification, native process, archive restore, or queue edit.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import tarfile
import datetime as dt


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate JSON key: '+key)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def read(path): return decode(Path(path).read_bytes())
def sha(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value): return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()
def digest(value): return sha(encoded(value))


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp'); temporary.write_bytes(encoded(value)); temporary.replace(path)


def freeze(path, payload):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream: stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != payload: raise ValueError('immutable snapshot changed: '+str(path))
    path.chmod(0o444)


def budget_status(result, actual, target=450, record=False):
    if record: return 'RECORD_REPORTED_REQUIRES_EXISTING_INDEPENDENT_PROOFS'
    if result is None: return 'PENDING_OR_RUNNING'
    if result.get('exit_code') != 0 or result.get('timed_out') is not False or result.get('interrupted') is not False:
        return 'INTERRUPTED_OR_FAILED'
    if actual is None: return 'MISSING_FINAL_CPU_ACCOUNTING'
    if actual+1e-8 < target: return 'UNKNOWN_WALL_CENSORED_CPU_TARGET_NOT_MET'
    return 'CPU_TARGET_COMPLETED'


def policy_checks(initial, final, control):
    def finite(value):
        if isinstance(value, dict): return all(finite(x) for x in value.values())
        if isinstance(value, list): return all(finite(x) for x in value)
        return not isinstance(value, (float, int)) or math.isfinite(value)
    same = digest(initial) == digest(final)
    if control:
        return {'full_policy_Adam_scalars_counters_unchanged': same, 'policy_finite': finite(final)}
    return {'updates_increased': final['updates'] > initial['updates'],
            'weights_changed': final['params'] != initial['params'],
            'Adam_first_moment_changed': final['m'] != initial['m'],
            'Adam_second_moment_changed': final['s'] != initial['s'],
            'hyperparameters_unchanged': all(final[k] == initial[k] for k in ('hidden', 'entropy', 'learning_rate')),
            'policy_finite': finite(final)}


def event_summary(path, initial, initial_schedule, control):
    summary = {'lines': 0, 'native_transitions': 0, 'main_transitions': 0, 'recovery_transitions': 0,
               'actions': Counter(), 'run_references': [], 'checks': {}, 'errors': [], 'trailing_partial_line': False,
               'last_main_action_cpu': None}
    if not path.exists(): return summary
    previous_cpu = (initial_schedule['record_cpu'], initial_schedule['recovery_cpu'])
    clock = initial['finetune43']['clock']; cap = initial['context']['ledger']['cap']
    start = None
    with path.open() as stream:
        for number, line in enumerate(stream, 1):
            try: event = decode(line)
            except ValueError:
                if not line.endswith('\n'): summary['trailing_partial_line'] = True; break
                summary['errors'].append('invalid complete event JSON line '+str(number)); continue
            summary['lines'] += 1
            if event.get('event') == 'start':
                start = event
                summary['checks'].update(
                    startup_operator_identity=event.get('operator44') == initial['operator44'],
                    startup_phase_clock=event.get('finetune43') == initial['finetune43'],
                    startup_restart_identity=event.get('restart_context') == initial['restart_curriculum'],
                    startup_pool_operator_identity=event.get('pool_context') == initial['pool_curriculum'],
                    startup_CPU_origins=event.get('record_cpu') == initial_schedule['record_cpu'] and event.get('recovery_cpu') == initial_schedule['recovery_cpu'],
                    startup_450_budget=event.get('main_cpu_budget') == 450 and event.get('invocation_main_origin') == initial_schedule['record_cpu'],
                    startup_training_mode=event.get('train') is (not control),
                    startup_control_mode=event.get('control') == ('random' if control == 'random' else 'policy'))
            if event.get('event') == 'recovery_start':
                record, recovery = previous_cpu
                used_record, used_recovery = record-clock['record_origin'], recovery-clock['recovery_origin']
                due = used_record > 0 and used_recovery < clock['recovery_fraction']*(used_record+used_recovery)
                if not due: summary['errors'].append('recovery launched without inherited CPU debt at line '+str(number))
                if event.get('training_split') != 'train': summary['errors'].append('nontraining task used for auxiliary update')
            if event.get('event') == 'transition':
                summary['actions'][event['action']] += 1
                recovery = event.get('task_kind') == 'KNOWN_RECOVERY'
                summary['recovery_transitions' if recovery else 'main_transitions'] += 1
                if not recovery: summary['last_main_action_cpu'] = event.get('measured_total_cpu_seconds')
                if event.get('rank', 0) > event.get('best_rank', 0)+6:
                    summary['errors'].append('accepted-state best+6 cap violated at line '+str(number))
                if event.get('global_novelty_paid', cap) > cap:
                    summary['errors'].append('novelty cap exceeded at line '+str(number))
                native = event.get('native', {})
                if native.get('run_dir'):
                    summary['native_transitions'] += 1
                    summary['run_references'].append({'run_dir': native['run_dir'], 'action': event['action'],
                        'task_kind': event.get('task_kind'), 'attempted_moves': native.get('attempted_moves'),
                        'native_current_rank': native.get('current_rank'), 'controller_rank': event.get('rank'),
                        'controller_best_rank': event.get('best_rank'), 'accepted': event.get('accepted')})
            if 'record_cpu' in event and 'recovery_cpu' in event:
                current = event['record_cpu'], event['recovery_cpu']
                if current[0]+1e-9 < previous_cpu[0] or current[1]+1e-9 < previous_cpu[1]:
                    summary['errors'].append('CPU counter decreased at line '+str(number))
                previous_cpu = current
    summary['last_record_cpu'], summary['last_recovery_cpu'] = previous_cpu
    summary['checks']['start_event_present'] = start is not None
    summary['actions'] = dict(summary['actions'])
    return summary


def native_summary(record, manifest, stats, binding, input_rank=None):
    profile_name = record['action'].removeprefix('native_'); profile = binding['profiles'][profile_name]
    checks = {'profile': manifest.get('action_parameters') == profile,
              'worker_source': manifest.get('binary_sha256') == binding['binary_sha256'] and manifest.get('source_sha256') == binding['source_sha256'],
              'native_cap': stats.get('max_rank') == manifest.get('max_rank') and stats.get('max_visited_rank', 10**9) <= manifest.get('max_rank', -1),
              'steps': stats.get('steps') == record.get('attempted_moves'),
              'cyclic': stats.get('cyclic') == profile['cyclic'],
              'burst_dwell': stats.get('plus_burst') == profile['plus_burst'] and stats.get('reduction_dwell') == profile['reduction_dwell'],
              'cadences': stats.get('plus_every') == profile['plus_every'] and stats.get('restart_every') == profile['restart_every']}
    checks['bridge_code'] = manifest.get('code_sha256', {}).get('native_bridge44.py') == binding['bridge_sha256']
    checks['target'] = stats.get('target_rank') == manifest.get('target_rank') == (93 if record['task_kind']=='KNOWN_RECOVERY' else 92)
    if input_rank is not None: checks['current_plus_profile_headroom'] = manifest['max_rank'] == input_rank+profile['rank_headroom']
    if record['task_kind'] == 'KNOWN_RECOVERY': checks['recovery_fixed_step_cap'] = manifest.get('step_budget') == 50000 and stats.get('steps', 50001) <= 50000
    return {'checks': checks, 'action': record['action'], 'task_kind': record['task_kind'],
            'max_rank': stats.get('max_rank'), 'max_visited_rank': stats.get('max_visited_rank'),
            'max_rank_excess': stats.get('max_rank_excess'), 'steps': stats.get('steps'),
            'rank_residency_steps': stats.get('rank_residency_steps'),
            'rank_excess_residency_steps': stats.get('rank_excess_residency_steps'),
            'accepted_by_kind': stats.get('accepted_by_kind'),
            'dwell_reductions_deferred': stats.get('dwell_reductions_deferred'),
            'burst_rank_capped': stats.get('burst_rank_capped'),
            'burst_attempt_capped': stats.get('burst_attempt_capped'),
            'input_rank': input_rank, 'manifest_sha256': digest(manifest), 'stats_sha256': digest(stats)}


def collect_native(references, binding, campaign, cache):
    pending = {r['run_dir']: r for r in references if r['run_dir'] not in cache}
    for directory, record in list(pending.items()):
        run = Path(directory)
        if not run.is_relative_to(campaign): raise ValueError('event native path outside campaign')
        m, s, input_file = run/'manifest.json', run/'walk.stats.json', run/'input.json'
        if m.is_file() and s.is_file() and input_file.is_file():
            candidate = read(input_file)
            value = native_summary(record, read(m), read(s), binding, len(candidate['terms']))
            value['provenance'] = {'raw_run': directory, 'input_raw_sha256': sha(input_file.read_bytes())}
            cache[directory] = value; pending.pop(directory)
    # Only explicit archive namespaces for the referenced pilot roots; no
    # campaign recursion and no extraction/restoration of any file.
    policy = read(campaign/'campaign.json'); prior = Path(policy['prior_campaign']).resolve()
    central = prior/'lossless-native-archives42'
    roots = sorted({str(Path(d).parent) for d in pending})
    for root_string in roots:
        root = Path(root_string); native = root.parent.parent
        namespace = central/(native.parent.name+'-'+root.parent.name+'-'+sha(str(root).encode())[:16])
        for path in sorted(namespace.glob('*.manifest.json')):
            archive_manifest = read(path)
            if Path(archive_manifest.get('runs_directory', '')).resolve() != root: raise ValueError('archive source-root mismatch')
            runs = {x['run']: x for x in archive_manifest['runs']}
            wanted = {Path(d).name: d for d in pending if Path(d).parent == root and Path(d).name in runs}
            if not wanted: continue
            table = {x['path']: x for x in archive_manifest['files']}
            with tarfile.open(path.parent/archive_manifest['archive'], 'r:gz') as stream:
                for member in stream:
                    name = member.name.split('/')[0]
                    if name not in wanted or member.name != name+'/walk.stats.json': continue
                    payload = stream.extractfile(member).read()
                    if sha(payload) != table[member.name]['sha256']: raise ValueError('archived stats checksum differs')
                    directory = wanted[name]; metadata = runs[name]
                    input_ranks = [x['rank'] for x in metadata['candidate_audits'] if x['source'] == 'input.json']
                    value = native_summary(pending[directory], metadata['preserved_manifest'], decode(payload), binding,
                                           input_ranks[0] if input_ranks else None)
                    value['provenance'] = {'archive_manifest': str(path), 'manifest_sha256': sha(path.read_bytes()),
                        'archive': str(path.parent/archive_manifest['archive']), 'archive_sha256': archive_manifest['archive_sha256'],
                        'stats_member': member.name, 'stats_raw_sha256': sha(payload)}
                    cache[directory] = value; pending.pop(directory)
    return sorted(pending)


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
        control = 'random' if name.startswith('random') else 'frozen' if name.startswith('frozen') else None
        events = event_summary(directory/'events.jsonl', initial, initial_schedule, control)
        references = events.pop('run_references'); missing = collect_native(references, binding, campaign, cache)
        native_rows = [cache[x['run_dir']] for x in references if x['run_dir'] in cache]
        checks = dict(events['checks']); checks['event_invariants'] = not events['errors']
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
                if result and result.get('exit_code')==0 and not control:
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
    report = {'format':'query-free-operator44-pilot-collection-v1','utc':dt.datetime.now(dt.timezone.utc).isoformat(),
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
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('campaign','runtime','proposal','output'): parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args(argv)
    report = collect(args.campaign,args.runtime,args.proposal,args.output)
    print(json.dumps({'all_three_CPU_targets_completed':report['all_three_CPU_targets_completed'],
                      'pilots':[{'job':x['job'],'status':x['status']} for x in report['pilots']],
                      'report':str(args.output/'REPORT.json')}))


if __name__=='__main__': main()
