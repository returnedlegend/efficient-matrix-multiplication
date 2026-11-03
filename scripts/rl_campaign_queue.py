#!/usr/bin/env python3
"""Restartable, read-only-policy queue launcher for the bounded RL campaign.

queue.json: {"jobs": [{"id": "name", "cpu": 0, "memory_mb": 768,
"seconds": 600, "command": ["python3", "..."], "enabled": true}]}.
An absent queue means no jobs. This supervisor never terminates workers and
does not verify candidates. A reported target stops further scheduling only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MEMORY_MB = 6144
TERMINAL = {"completed", "failed_to_launch"}


def utc(now):
    return dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path):
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def atomic_json(path, value):
    tmp = path.with_name(path.name+f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def process_identity(pid):
    """Identify a live process with Linux start ticks, rejecting zombies/PID reuse."""
    if type(pid) is not int or pid < 1:
        return None
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        fields = text[text.rfind(")")+2:].split()
        if fields[0] in ("Z", "X"):
            return None
        ticks = int(fields[19])
        boot = next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines()
                    if line.startswith('btime '))
        return {"start_ticks": ticks, "started_unix": boot+ticks/os.sysconf('SC_CLK_TCK')}
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def validate_jobs(value):
    if set(value) != {"jobs"} or not isinstance(value["jobs"], list):
        raise ValueError("queue must contain only a jobs array")
    seen, jobs = set(), []
    for job in value["jobs"]:
        if not isinstance(job, dict) or set(job) != {"id", "cpu", "memory_mb", "seconds", "command", "enabled"}:
            raise ValueError("each job requires id,cpu,memory_mb,seconds,command,enabled")
        name = job["id"]
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name) is None:
            raise ValueError("invalid job id")
        if name in seen:
            raise ValueError("duplicate job id")
        seen.add(name)
        if type(job["cpu"]) is not int or not 0 <= job["cpu"] <= 3:
            raise ValueError("CPU must be an integer in 0..3")
        if type(job["memory_mb"]) is not int or not 64 <= job["memory_mb"] <= MEMORY_MB:
            raise ValueError("memory_mb must be an integer in 64..6144")
        if type(job["seconds"]) is not int or job["seconds"] < 1:
            raise ValueError("seconds must be a positive integer")
        if type(job["enabled"]) is not bool:
            raise ValueError("enabled must be boolean")
        if (not isinstance(job["command"], list) or not job["command"]
                or any(not isinstance(x, str) or "\0" in x for x in job["command"])
                or not job["command"][0]):
            raise ValueError("command must be an argv of strings with a nonempty executable and no NULs")
        jobs.append(job)
    return jobs


class Supervisor:
    def __init__(self, directory, *, now=time.time, identity=process_identity, launch=None):
        self.directory = Path(directory).resolve()
        self.now, self.identity = now, identity
        self.launch = launch or self._launch
        self.children = {}
        self.code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        path = self.directory/'queue_state.json'
        if path.exists():
            self.state, _ = load_json(path)
            if self.state.get("format") != "mmsearch-queue-v1" or self.state.get("directory") != str(self.directory):
                raise ValueError("queue state format/directory mismatch")
        else:
            self.state = {"format": "mmsearch-queue-v1", "directory": str(self.directory),
                          "jobs": {}, "stop_reason": None, "created_utc": utc(self.now())}

    def save(self):
        self.state.update(updated_utc=utc(self.now()), supervisor_pid=os.getpid(),
                          supervisor_code_sha256=self.code_hash)
        atomic_json(self.directory/'queue_state.json', self.state)

    def record(self, event, **values):
        row = {"utc": utc(self.now()), "event": event, "code_sha256": self.code_hash,
               "queue_sha256": self.state.get("queue_sha256"), **values}
        with (self.directory/'queue_events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, allow_nan=False)+'\n')
            stream.flush()
            os.fsync(stream.fileno())

    def stop(self, reason):
        if self.state.get("stop_reason") is None:
            self.state["stop_reason"] = reason
            self.state["stopped_utc"] = utc(self.now())
            self.save()
            self.record("scheduling_stopped", reason=reason)

    def _launch(self, command, prefix):
        with prefix.with_suffix('.launcher.log').open('ab') as output:
            process = subprocess.Popen(command, cwd=ROOT, stdout=output,
                                       stderr=subprocess.STDOUT, shell=False,
                                       start_new_session=True)
        self.children[process.pid] = process
        return process.pid

    def reported_target(self, target):
        winner = next(iter(sorted(self.directory.glob('*/WINNER.json'))), None)
        if (self.directory/'WINNER.json').exists():
            winner = self.directory/'WINNER.json'
        if winner is not None:
            return f"WINNER file reported: {winner.relative_to(self.directory)}; unverified by supervisor"
        for path in [*self.directory.glob('*/best.json'), *self.directory.glob('*/best_verified.json'),
                     *self.directory.glob('*/checkpoint.json'), *self.directory.glob('*/phase-*/walk.stats.json')]:
            try:
                value, _ = load_json(path)
                meta, config, state = value.get('metadata', {}), value.get('config', {}), value.get('state', {})
                if path.name == 'checkpoint.json':
                    reached = config.get('n') == 5 and state.get('terminal') and len(value.get('best', [])) <= target
                elif path.name == 'walk.stats.json':
                    reached = value.get('dimension') == 5 and value.get('target_reached') and value.get('best_rank', 999) <= target
                else:
                    rank = meta.get('rank', len(value.get('terms', [])))
                    reached = (value.get('dimension') == 5 and value.get('field') == 2 and rank <= target
                               and (meta.get('record_target_reached') or meta.get('target_reached')
                                    or meta.get('status') == 'verified_target'))
                if reached:
                    return f"target reported: {path.relative_to(self.directory)}; unverified by supervisor"
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return None

    def running(self):
        """Return active root registrations; unreadable metadata blocks scheduling."""
        active = {}
        for path in self.directory.glob('*.running.json'):
            value, _ = load_json(path)
            pid = value.get('pid')
            identity = self.identity(pid)
            if identity is None:
                continue
            started = parse_time(value['started_utc'])
            if abs(identity['started_unix']-started) > 10:
                continue
            cpu, memory = value.get('cpu'), value.get('memory_mb')
            if type(cpu) is not int or cpu not in range(4) or type(memory) is not int or memory < 1:
                raise ValueError("invalid live job CPU/memory metadata")
            active[str(path).removesuffix('.running.json')] = value
        return active

    def reconcile(self):
        for name, record in self.state['jobs'].items():
            if record['status'] in TERMINAL:
                continue
            prefix = self.directory/f'{name}-job'
            result_path = prefix.with_suffix('.result.json')
            if result_path.exists():
                try:
                    result, digest = load_json(result_path)
                except (OSError, ValueError):
                    continue
                record.update(status='completed', completed_utc=utc(self.now()),
                              result_sha256=digest, exit_code=result.get('exit_code'),
                              timed_out=result.get('timed_out'))
                self.save()
                self.record('job_completed', id=name, result_sha256=digest, exit_code=result.get('exit_code'))
                continue
            identity = self.identity(record.get('launcher_pid'))
            launcher_live = bool(identity and identity['start_ticks'] == record.get('launcher_start_ticks'))
            child_live = False
            try:
                running, _ = load_json(prefix.with_suffix('.running.json'))
                child = self.identity(running.get('pid'))
                child_live = bool(child and abs(child['started_unix']-parse_time(running['started_utc'])) <= 10)
            except (OSError, ValueError, KeyError):
                pass
            if launcher_live or child_live:
                record['status'] = 'running'
            elif record['status'] != 'held_ambiguous' and self.now()-parse_time(record['attempted_utc']) > 30:
                # An intent can survive a crash before/after Popen. Never guess
                # and relaunch: retaining the id prevents duplicate execution.
                record.update(status='held_ambiguous', held_utc=utc(self.now()),
                              reason='no live registered process or result after launch intent; never auto-relaunched')
                self.save()
                self.record('job_held_ambiguous', id=name)

    def tick(self):
        for pid, process in list(self.children.items()):
            if process.poll() is not None:
                del self.children[pid]
        self.reconcile()
        if self.state.get('stop_reason') is not None:
            return False
        try:
            config, _ = load_json(self.directory/'campaign.json')
            deadline = parse_time(config['deadline_utc'])
            if config.get('field') != 2 or config.get('max_cpu_cores') != 4 or config.get('max_ram_gib') != 8:
                raise ValueError('expected declared F2 campaign with four CPUs and 8 GiB')
            target = config['target_rank']
            if type(target) is not int or target < 1:
                raise ValueError('invalid target rank')
            if self.now() >= deadline:
                self.stop('global campaign deadline reached')
                return False
            if (self.directory/'guard_stopped.json').exists():
                self.stop('campaign guard reported a stop; no further scheduling')
                return False
            winner = self.reported_target(target)
            if winner:
                self.stop(winner)
                return False
            queue = self.directory/'queue.json'
            if queue.exists():
                value, digest = load_json(queue)
            else:
                value, digest = {'jobs': []}, None
            jobs = validate_jobs(value)
            self.state.update(queue_sha256=digest, last_error=None)
            active = self.running()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.state['last_error'] = str(exc)
            self.save()
            return True
        # Include just-spawned launchers until the limiter registers its child.
        for name, record in self.state['jobs'].items():
            prefix = str(self.directory/f'{name}-job')
            if record['status'] in ('launching', 'running', 'held_ambiguous') and prefix not in active:
                active[prefix] = record['spec']
        occupied = {item['cpu'] for item in active.values()}
        memory = sum(item['memory_mb'] for item in active.values())
        self.state.update(active_registered_jobs=len(active), requested_active_memory_mb=memory)
        for job in jobs:
            name = job['id']
            if not job['enabled'] or name in self.state['jobs']:
                continue
            prefix = self.directory/f'{name}-job'
            if prefix.with_suffix('.result.json').exists():
                self.state['jobs'][name] = {'status': 'launching', 'attempted_utc': utc(self.now()),
                                            'spec': job, 'adopted_existing': True}
                self.reconcile()
                continue
            if str(prefix) in active:
                self.state['jobs'][name] = {'status': 'running', 'attempted_utc': utc(self.now()),
                                            'spec': job, 'adopted_existing': True}
                self.save()
                continue
            if prefix.with_suffix('.running.json').exists() or prefix.with_suffix('.launcher.log').exists():
                self.state['jobs'][name] = {'status': 'held_ambiguous', 'attempted_utc': utc(self.now()),
                    'spec': job, 'reason': 'existing launch artifacts without a live registration or completed result; never auto-relaunched'}
                active[str(prefix)] = job
                occupied.add(job['cpu'])
                memory += job['memory_mb']
                self.save()
                self.record('job_held_ambiguous', id=name)
                continue
            try:
                # Refresh before each launch in case another root-managed job
                # registered since this pass began. Reservations remain until
                # the next pass, which can delay work but cannot overallocate.
                for key, value in self.running().items():
                    active[key] = value
                occupied.update(value['cpu'] for value in active.values())
                memory = sum(value['memory_mb'] for value in active.values())
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.state['last_error'] = str(exc)
                self.save()
                return True
            if job['cpu'] in occupied or memory+job['memory_mb'] > MEMORY_MB:
                continue
            if deadline-self.now() < 1:
                self.stop('global campaign deadline reached')
                return False
            if (self.directory/'guard_stopped.json').exists():
                self.stop('campaign guard reported a stop; no further scheduling')
                return False
            winner = self.reported_target(target)
            if winner:
                self.stop(winner)
                return False
            command = [sys.executable, str(ROOT/'scripts/limited_worker.py'), '--cpu', str(job['cpu']),
                       '--memory-mb', str(job['memory_mb']), '--seconds', str(job['seconds']),
                       '--prefix', str(prefix), '--', *job['command']]
            record = {'status': 'launching', 'attempted_utc': utc(self.now()), 'spec': job,
                      'queue_sha256': digest, 'code_sha256': self.code_hash, 'launch_command': command}
            self.state['jobs'][name] = record
            self.save()  # Durable intent BEFORE Popen; this id is never retried.
            self.record('launch_intent', id=name, launch_command=command)
            try:
                pid = self.launch(command, prefix)
            except OSError as exc:
                record.update(status='failed_to_launch', error=str(exc), failed_utc=utc(self.now()))
                self.save()
                self.record('launch_failed', id=name, error=str(exc))
                continue
            identity = self.identity(pid)
            record.update(status='running', launcher_pid=pid,
                          launcher_start_ticks=identity['start_ticks'] if identity else None,
                          launched_utc=utc(self.now()))
            occupied.add(job['cpu'])
            active[str(prefix)] = job
            memory += job['memory_mb']
            self.save()
            self.record('job_launched', id=name, launcher_pid=pid, launch_command=command)
        self.state['requested_active_memory_mb'] = memory
        self.state['active_registered_jobs'] = len(active)
        self.save()
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--poll-seconds', type=float, default=5)
    parser.add_argument('--once', action='store_true', help='one scheduling pass (can launch enabled jobs)')
    args = parser.parse_args()
    if not 1 <= args.poll_seconds <= 60:
        parser.error('poll interval must be between 1 and 60 seconds')
    os.sched_setaffinity(0, {2})
    os.nice(10)
    with (args.directory/'queue_supervisor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('another queue supervisor holds this campaign lock')
        supervisor = Supervisor(args.directory)
        stopping = False
        exit_reason = None
        def stop(signum, _frame):
            nonlocal stopping, exit_reason
            stopping = True
            exit_reason = f'signal {signum}; workers untouched'
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            while not stopping:
                keep_running = supervisor.tick()
                if args.once or not keep_running:
                    break
                time.sleep(args.poll_seconds)
        finally:
            if exit_reason:
                supervisor.state['supervisor_exit_reason'] = exit_reason
            supervisor.save()
        print(json.dumps({'utc': utc(time.time()), 'stop_reason': supervisor.state.get('stop_reason'),
                          'registered_job_ids': len(supervisor.state['jobs']),
                          'last_error': supervisor.state.get('last_error')}))


if __name__ == '__main__':
    main()
