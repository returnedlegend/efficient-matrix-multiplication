#!/usr/bin/env python3
"""Collect bounded, read-only campaign evidence into repeatable JSON/CSV snapshots.

Reads root job registrations and selected files in immediate child directories.
Never descends into native/recovery runs, verifies tensors, or starts workers.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import time

ARTIFACT_NAMES = ('manifest.json', 'provenance.json', 'result.json', 'summary.json',
                  'best_verified.json', 'latest_stats.json', 'READY.json', 'preparation.json')
ROOT_NAMES = ('campaign.json', 'queue.json', 'queue_state.json', 'resource_status.json',
              'live_status.json', 'quick_status.json', 'auxiliary_pair_watcher.json')
CSV_FIELDS = ('id', 'queue_status', 'registration_status', 'process_observation',
              'exit_code', 'timed_out', 'interrupted', 'cpu', 'memory_mb',
              'wall_limit_seconds', 'started_utc', 'wall_elapsed_seconds', 'cpu_seconds',
              'max_rss_kib', 'artifact_status', 'control_status', 'reported_best_rank',
              'input_code_hash_references', 'evidence_paths', 'read_issues')


class Reader:
    def __init__(self, per_file=2*1024*1024, total=64*1024*1024):
        self.per_file, self.remaining = per_file, total
        self.inventory, self.cache = [], {}

    def read(self, path):
        path = Path(path)
        if path in self.cache:
            return self.cache[path]
        info = {'path': str(path), 'read_status': 'missing'}
        value = None
        try:
            if path.is_symlink():
                info['read_status'] = 'symlink_skipped'
            elif path.is_file():
                size = path.stat().st_size; info['bytes'] = size
                if size > self.per_file:
                    info['read_status'] = 'per_file_limit'
                elif size > self.remaining:
                    info['read_status'] = 'total_read_limit'
                else:
                    with path.open('rb') as stream:
                        raw = stream.read(min(self.per_file, self.remaining)+1)
                    if len(raw) > min(self.per_file, self.remaining):
                        raise ValueError('file grew beyond read bound')
                    self.remaining -= len(raw)
                    info['sha256'] = hashlib.sha256(raw).hexdigest()
                    value = json.loads(raw)
                    info['read_status'] = 'ok'
        except (OSError, ValueError, RecursionError) as exc:
            info['read_status'] = 'unreadable_or_partial_json'
            info['error_type'] = type(exc).__name__
        self.inventory.append(info); self.cache[path] = (value, info)
        return value, info


def scalar_summary(value):
    if not isinstance(value, dict):
        return {}
    out = {k: v for k, v in value.items() if v is None or type(v) in (str, int, float, bool)}
    for key in ('counts', 'status_counts', 'stats', 'arms'):
        child = value.get(key)
        if isinstance(child, dict):
            out[key] = {k: v for k, v in child.items()
                        if v is None or type(v) in (str, int, float, bool)}
            if key == 'arms':
                out[key] = {k: scalar_summary(v) for k, v in child.items() if isinstance(v, dict)}
    return out


def hash_references(value, limit=256):
    found, work, inspected = {}, [('', value)], 0
    while work and len(found) < limit and inspected < 4096:
        prefix, obj = work.pop(); inspected += 1
        if isinstance(obj, dict):
            for key, item in list(obj.items())[:256]:
                label = f'{prefix}.{key}' if prefix else key
                if isinstance(item, str) and ('sha256' in key.lower() or 'hash' in key.lower()):
                    found[label] = item
                elif isinstance(item, (dict, list)):
                    work.append((label, item))
        elif isinstance(obj, list):
            work.extend((f'{prefix}[{i}]', item) for i, item in enumerate(obj[:64])
                        if isinstance(item, (dict, list)))
        # code_sha256 dictionaries use filenames as keys, so preserve these too.
        if isinstance(obj, dict) and ('sha256' in prefix.lower() or 'hash' in prefix.lower()):
            found.update({f'{prefix}.{k}': v for k, v in list(obj.items())[:256]
                          if isinstance(v, str) and len(v) == 64})
    return dict(sorted(found.items())[:limit])


def process_observation(pid):
    if type(pid) is not int:
        return 'not_registered'
    try:
        state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
        return 'zombie' if state == 'Z' else 'pid_exists_identity_not_validated'
    except (OSError, IndexError):
        return 'pid_missing'


def output_directory(command, campaign, job_id):
    for flag in ('--output-dir', '--outdir', '--checkpoint'):
        if flag in command and command.index(flag)+1 < len(command):
            path = Path(command[command.index(flag)+1])
            if not path.is_absolute():
                path = campaign.parent.parent/path
            return path.parent if flag == '--checkpoint' else path
    return campaign/job_id


def collect(campaign, *, max_jobs=512, max_directories=256, per_file=2*1024*1024,
            total_bytes=64*1024*1024, exclude=None):
    campaign = Path(campaign).resolve(); reader = Reader(per_file, total_bytes)
    root = {name: reader.read(campaign/name)[0] for name in ROOT_NAMES}
    queue = root.get('queue.json') or {}; state = root.get('queue_state.json') or {}
    queue = queue if isinstance(queue, dict) else {}; state = state if isinstance(state, dict) else {}
    specs = {j['id']: j for j in queue.get('jobs', []) if isinstance(j, dict) and isinstance(j.get('id'), str)}
    registrations = {}
    for suffix in ('.running.json', '.result.json'):
        for path in sorted(campaign.glob('*'+suffix))[:max_jobs]:
            job_id = path.name.removesuffix(suffix).removesuffix('-job')
            registrations.setdefault(job_id, {})[suffix] = path
    ids = sorted(set(specs) | set(registrations) | set(state.get('jobs', {})))
    jobs, summaries, reported_ranks = [], {}, []
    for job_id in ids[:max_jobs]:
        entry = state.get('jobs', {}).get(job_id, {}); spec = specs.get(job_id, entry.get('spec', {}))
        paths = registrations.get(job_id, {})
        result, running = reader.read(paths.get('.result.json', campaign/(job_id+'-job.result.json')))[0], reader.read(paths.get('.running.json', campaign/(job_id+'-job.running.json')))[0]
        result = result if isinstance(result, dict) else {}; running = running if isinstance(running, dict) else {}
        value = result or running; command = value.get('command', spec.get('command', []))
        command = command if isinstance(command, list) else []
        directory = output_directory(command, campaign, job_id)
        evidence, statuses, controls, ranks, refs, issues = [], [], [], [], {}, []
        # Only registered, immediate campaign children may supply artifact files.
        if directory.resolve().parent == campaign and not directory.is_symlink():
            for name in ARTIFACT_NAMES:
                artifact, info = reader.read(directory/name)
                if info['read_status'] == 'missing':
                    continue
                evidence.append(info['path'])
                if info['read_status'] != 'ok':
                    issues.append(f'{name}:{info["read_status"]}')
                if isinstance(artifact, dict):
                    summaries[info['path']] = scalar_summary(artifact)
                    refs.update({f'{name}:{k}': v for k, v in hash_references(artifact).items()})
                    if name in ('result.json', 'summary.json') and artifact.get('status'):
                        statuses.append(f'{name}:{artifact["status"]}')
                    if artifact.get('control_status'):
                        controls.append(str(artifact['control_status']))
                    if name == 'best_verified.json' and type(artifact.get('rank')) is int:
                        ranks.append(artifact['rank']); reported_ranks.append(artifact['rank'])
        row = dict(id=job_id, queue_status=entry.get('status', 'queued' if spec else 'untracked'),
                   registration_status='completed' if result else ('registered_running' if running else 'not_registered'),
                   process_observation=process_observation(running.get('pid')) if running else 'not_registered',
                   exit_code=result.get('exit_code'), timed_out=result.get('timed_out'), interrupted=result.get('interrupted'),
                   cpu=value.get('cpu', spec.get('cpu')), memory_mb=value.get('memory_mb', spec.get('memory_mb')),
                   wall_limit_seconds=value.get('wall_seconds', spec.get('seconds')), started_utc=value.get('started_utc'),
                   wall_elapsed_seconds=result.get('elapsed_seconds'), cpu_seconds=result.get('cpu_seconds'),
                   max_rss_kib=result.get('max_rss_kib'), artifact_status=';'.join(statuses),
                   control_status=';'.join(sorted(set(controls))), reported_best_rank=min(ranks) if ranks else None,
                   input_code_hash_references=refs, evidence_paths=evidence, read_issues=issues, command=command)
        jobs.append(row)
    directories = sorted(x for x in campaign.iterdir() if x.is_dir() and not x.is_symlink()
                         and (exclude is None or x.resolve() != Path(exclude).resolve()))
    for directory in directories[:max_directories]:
        for name in ARTIFACT_NAMES:
            value, info = reader.read(directory/name)
            if isinstance(value, dict):
                summaries[info['path']] = scalar_summary(value)
    reconstruction, _ = reader.read(campaign/'dictionary-new1/resource_reconstruction.json')
    completed = [x for x in jobs if x['registration_status'] == 'completed']
    numeric_cpu = [x['cpu_seconds'] for x in completed if type(x['cpu_seconds']) in (int, float)]
    return dict(format='bounded-campaign-report-v1', collected_utc=datetime.now(timezone.utc).isoformat(),
                campaign_directory=str(campaign), collector_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                claim='Reporting existing files only; no tensor verification, novelty assessment, or search performed.',
                bounds=dict(max_jobs=max_jobs, jobs_discovered=len(ids), jobs_truncated=len(ids)>max_jobs,
                            max_directories=max_directories, directories_discovered=len(directories),
                            directories_truncated=len(directories)>max_directories, per_file_bytes=per_file,
                            total_bytes=total_bytes, consumed_bytes=total_bytes-reader.remaining,
                            traversal='root job files and selected immediate-child JSON files only; no recovery/native tree traversal'),
                campaign=scalar_summary(root.get('campaign.json')), guard=scalar_summary(root.get('resource_status.json')),
                queue_state=scalar_summary(root.get('queue_state.json')), current_status=scalar_summary(root.get('live_status.json')),
                reported_best_rank=min(reported_ranks) if reported_ranks else None,
                resource_totals=dict(completed_jobs=len(completed), sum_reported_cpu_seconds=sum(numeric_cpu),
                    sum_completed_job_wall_seconds_not_campaign_duration=sum(x['wall_elapsed_seconds'] for x in completed if type(x['wall_elapsed_seconds']) in (int,float)),
                    completeness='PARTIAL: outer rusage omitted dictionary solver grandchild; running jobs have no final CPU totals; bounded/missing reads may omit evidence.',
                    dictionary_grandchild_reconstruction=reconstruction,
                    reconstruction_policy='Preserved separately; not silently added to outer-rusage totals or double-counted.'),
                jobs=jobs, artifact_summaries=summaries, evidence_files=reader.inventory)


def write_snapshot(report, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True)+'\n'
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS); writer.writeheader()
    for row in report['jobs']:
        writer.writerow({key: json.dumps(row[key], sort_keys=True) if isinstance(row.get(key), (list, dict)) else row.get(key)
                         for key in CSV_FIELDS})
    for name, value in (('report.json', payload), ('jobs.csv', stream.getvalue())):
        temporary = output/(name+'.tmp'); temporary.write_text(value); temporary.replace(output/name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--max-jobs', type=int, default=512)
    parser.add_argument('--max-directories', type=int, default=256)
    args = parser.parse_args(argv)
    if not args.campaign.is_dir() or not 1 <= args.max_jobs <= 4096 or not 1 <= args.max_directories <= 4096:
        parser.error('existing campaign and limits between 1 and 4096 required')
    if args.output_dir.resolve() == args.campaign.resolve() or args.campaign.resolve().is_relative_to(args.output_dir.resolve()):
        parser.error('output must be a separate snapshot directory, not the campaign or its ancestor')
    os.sched_setaffinity(0, {2}); os.nice(10)
    start = time.process_time()
    report = collect(args.campaign, max_jobs=args.max_jobs, max_directories=args.max_directories, exclude=args.output_dir)
    report['collector_cpu_seconds_before_export'] = time.process_time()-start
    write_snapshot(report, args.output_dir)
    print(json.dumps(dict(output_dir=str(args.output_dir), jobs=len(report['jobs']),
                         reported_best_rank=report['reported_best_rank'], cpu_seconds=time.process_time()-start)))


if __name__ == '__main__':
    main()
