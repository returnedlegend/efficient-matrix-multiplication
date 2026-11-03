"""Validate and append exact queue argv jobs; preview is read-only by default.

Every writer must use the campaign's queue_append.lock. No subprocesses or
command normalization: a shell string is invalid, even inside a six-key job.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import phase_coordinator42_v2 as coordinator


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def atomic(path, value):
    """Persist bytes, replace atomically, and persist the directory entry."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def proposals(path, expected):
    value, actual = coordinator.read(path)
    if actual != expected:
        raise ValueError('proposal SHA256 differs')
    jobs = value['jobs'] if set(value) == {'jobs'} else [value]
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('proposal requires a nonempty jobs array or one exact job')
    seen = set()
    for job in jobs:
        coordinator.validate_job(job)
        if job['id'] in seen:
            raise ValueError('duplicate proposal id')
        seen.add(job['id'])
    return jobs


def merge(queue, jobs, enable=False):
    result = copy.deepcopy(queue)
    by_id = {job['id']: job for job in result['jobs']}
    effective, actions = [], []
    for proposed in jobs:
        job = copy.deepcopy(proposed)
        if enable:
            job['enabled'] = True
        coordinator.validate_job(job)
        previous = by_id.get(job['id'])
        if previous is None:
            if job['enabled'] and not enable:
                raise ValueError('new enabled job requires explicit --enable')
            result['jobs'].append(job); by_id[job['id']] = job
            action = 'append'
        elif previous == job:
            action = 'unchanged'
        elif enable and previous['enabled'] is False and job['enabled'] is True and {**previous, 'enabled': True} == job:
            previous['enabled'] = True
            action = 'enable'
        else:
            raise ValueError('duplicate id mutation forbidden: ' + job['id'])
        effective.append(job); actions.append({'id': job['id'], 'action': action})
    # Validate the entire effective queue, not just the newly appended jobs.
    for job in result['jobs']:
        coordinator.validate_job(job)
    if len({job['id'] for job in result['jobs']}) != len(result['jobs']):
        raise ValueError('duplicate effective queue id')
    return result, effective, actions


def append_jobs(queue_path, proposal_path, expected_proposal_sha256, receipt_path, *, apply=False, enable=False):
    queue_path, proposal_path, receipt_path = map(lambda p: Path(p).resolve(), (queue_path, proposal_path, receipt_path))
    lock_path = queue_path.parent / 'queue_append.lock'
    if len({queue_path, proposal_path, receipt_path, lock_path}) != 4:
        raise ValueError('queue, proposal, receipt and lock paths must differ')
    jobs = proposals(proposal_path, expected_proposal_sha256)
    queue, before = coordinator.queue_value(queue_path)
    result, effective, actions = merge(queue, jobs, enable)
    binding = {'proposal_sha256': expected_proposal_sha256, 'proposal_path': str(proposal_path),
               'queue_path': str(queue_path), 'enable_requested': enable,
               'helper_sha256': digest(Path(__file__).read_bytes()),
               'validator_sha256': digest(Path(coordinator.__file__).read_bytes())}
    if not apply:
        return {'status': 'PREVIEW_ONLY', 'zero_mutations': True, **binding,
                'queue_before_sha256': before, 'effective_jobs': effective, 'actions': actions}
    if not receipt_path.parent.is_dir():
        raise ValueError('receipt parent directory must already exist')
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Read and validate again while holding the shared append lock.
        jobs = proposals(proposal_path, expected_proposal_sha256)
        queue, before = coordinator.queue_value(queue_path)
        result, effective, actions = merge(queue, jobs, enable)
        recovered_intent = None
        if receipt_path.exists():
            previous, _ = coordinator.read(receipt_path)
            if any(previous.get(key) != value for key, value in binding.items()) or previous.get('effective_jobs') != effective:
                raise ValueError('receipt request binding differs')
            if previous.get('status') == 'COMMITTED':
                current = {job['id']: job for job in queue['jobs']}
                if any(current.get(job['id']) != job for job in effective):
                    raise ValueError('committed receipt jobs no longer match queue')
                return {**previous, 'idempotent_receipt_replay': True}
            if previous.get('status') != 'INTENT':
                raise ValueError('unknown receipt state')
            recovered_intent = previous.get('recovered_intent') or {
                key: previous[key] for key in ('utc', 'queue_before_sha256', 'queue_after_sha256', 'actions')}
        changed = result != queue
        receipt = {'format': 'root-queue-append42-v1', 'owner': 'root', 'status': 'INTENT',
                   'utc': dt.datetime.now(dt.timezone.utc).isoformat(), **binding,
                   'queue_before_sha256': before,
                   'queue_after_sha256': digest(encoded(result)) if changed else before,
                   'effective_jobs': effective, 'actions': actions, 'queue_changed': changed}
        if recovered_intent is not None:
            receipt['recovered_intent'] = recovered_intent
        atomic(receipt_path, receipt)  # Durable intent precedes any queue replacement.
        if changed:
            atomic(queue_path, result)
        receipt['status'] = 'COMMITTED'
        atomic(receipt_path, receipt)
        return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('queue', 'proposal', 'receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-proposal-sha256', required=True)
    parser.add_argument('--apply', action='store_true', help='append under lock; default is read-only preview')
    parser.add_argument('--enable', action='store_true', help='explicitly enable all proposed jobs; allows only false-to-true existing changes')
    args = parser.parse_args(argv)
    result = append_jobs(args.queue, args.proposal, args.expected_proposal_sha256, args.receipt,
                         apply=args.apply, enable=args.enable)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
