"""Six bounded exact native exploration profiles; no training or local WINNER.

Reuses the audited baseline's hidden-raw, fresh double-verification handoff.
Only an eligible records/*.json candidate is visible to the global record guard.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from scripts import campaign_native_baseline7 as safe
from scripts import tensor_code7 as lifecycle
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.compact_eight43 import opposite_pair_ranks

DEADLINE = '2026-11-03T19:24:17Z'
BINARY_SHA = '6e7d6c63fa262bfc50acfe92fbe9c11adb74426e3868a5a6f7ad8d1bf569ac19'
MIB = 1024**2


class OutputHold(Exception):
    pass


def validate_profile(profile):
    required = {'id', 'source_id', 'seed', 'cyclic', 'plus_burst', 'reduction_dwell', 'plus_every'}
    if set(profile) != required or type(profile['cyclic']) is not bool:
        raise ValueError('exact profile schema and literal cyclic Boolean required')
    if any(type(profile[k]) is not int for k in ['source_id', 'seed', 'plus_burst', 'reduction_dwell', 'plus_every']):
        raise ValueError('literal integer profile values required')
    if (profile['source_id'] < 0 or not 0 <= profile['seed'] < 2**64 or profile['plus_burst'] not in (1, 4)
            or profile['reduction_dwell'] not in (0, 128) or profile['plus_every'] not in (2000, 20000, 200000)
            or not isinstance(profile['id'], str) or not profile['id'] or Path(profile['id']).name != profile['id']):
        raise ValueError('profile outside bounded exploration settings')
    return profile


def command(binary, input_path, prefix, profile, *, seconds=120, n=5, target=92, steps=10**12):
    validate_profile(profile)
    if (type(n) is not int or n not in (2, 5) or not isinstance(seconds, (int, float))
            or isinstance(seconds, bool) or not math.isfinite(seconds) or not 0 < seconds <= 120
            or type(steps) is not int or steps < 1):
        raise ValueError('bounded exact native budget required')
    if n == 5 and (seconds != 120 or target != 92 or profile['seed'] == safe.SEED):
        raise ValueError('production uses120seconds/target92 and a fresh seed')
    argv = [str(binary), '--input', str(input_path), '--output', str(prefix), '--n', str(n),
        '--target', str(target), '--max-rank', str(105 if n == 5 else 20), '--seed', str(profile['seed']),
        '--steps', str(steps), '--seconds', str(seconds), '--checkpoint-seconds', '3',
        '--archive-size', '16', '--archive-every', '1000', '--plus-every', str(profile['plus_every']),
        '--restart-every', '50000000', '--plus-burst', str(profile['plus_burst']),
        '--reduction-dwell', str(profile['reduction_dwell'])]
    if profile['cyclic']:
        argv.append('--cyclic')
    return argv


def c3_closed(terms):
    values = set(terms)
    return all((b, c, a) in values for a, b, c in values)


def factor_multiplicities(terms):
    """Factor equality multiplicities are invariant under invertible axis bases."""
    answer = {}
    for axis, name in enumerate(('u', 'v', 'w')):
        counts = Counter(term[axis] for term in terms)
        answer[name] = dict(distinct_factors=len(counts), maximum_multiplicity=max(counts.values(), default=0),
            multiplicity_histogram=dict(sorted(Counter(counts.values()).items())))
    return answer


class SpaceBudget:
    def __init__(self, campaign, bundle, ids, current, *, monotonic=time.monotonic):
        self.campaign, self.bundle, self.ids, self.current = Path(campaign), Path(bundle), ids, Path(current)
        self.clock = monotonic
        self.last = -float('inf')
        self.current_bytes = self.total_bytes = 0
    @staticmethod
    def size(root):
        return sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()) if root.exists() else 0
    def check(self, force=False):
        if force or self.clock() - self.last >= .5:
            self.current_bytes = self.size(self.current)
            self.total_bytes = self.size(self.bundle) + sum(self.size(self.campaign / name) for name in self.ids)
            self.last = self.clock()
        # Reserve space for forced final raw drains and immutable proof metadata.
        if self.current_bytes >= 20*MIB or self.total_bytes >= 148*MIB:
            raise OutputHold('native portfolio output reserve reached; preserve final raw exports')


def validate_stats(stats, profile, n, target):
    expected = dict(dimension=n, seed=profile['seed'], target_rank=target, max_rank=105 if n == 5 else 20,
        cyclic=profile['cyclic'], reduction_dwell=profile['reduction_dwell'], plus_burst=profile['plus_burst'],
        plus_every=profile['plus_every'], restart_every=50000000, archive_every=1000)
    for key, value in expected.items():
        if type(stats.get(key)) is not type(value) or stats[key] != value:
            raise ValueError('native profile statistic differs: ' + key)
    if (type(stats.get('archive_size')) is not int or not 1 <= stats['archive_size'] <= 16
            or stats.get('exact') is not True or stats.get('tensor_invariant_checked') is not True
            or type(stats.get('steps')) is not int or stats['steps'] < 0):
        raise ValueError('native cap or exactness telemetry differs')
    for name in ['rank_residency_steps', 'rank_after_move_steps', 'rank_excess_residency_steps']:
        values = stats[name]
        if (not isinstance(values, dict) or any(not str(k).isdigit() or type(v) is not int or v < 0 for k, v in values.items())
                or sum(values.values()) != stats['steps']):
            raise ValueError('incomplete native residency histogram: ' + name)


def execute(binary, terms, output, fresh, profile, *, seconds=120, n=5, target=92, steps=10**12):
    output = Path(output)
    if profile['cyclic'] and not c3_closed(terms):
        raise ValueError('cyclic profile requires complete cyclic source orbits')
    prefix, input_path = output/'native/walk', output/'native/input.txt'
    safe.base.freeze(input_path, ''.join(f'{a} {b} {c}\n' for a, b, c in terms).encode())
    argv = command(binary, input_path, prefix, profile, seconds=seconds, n=n, target=target, steps=steps)
    seen, rank_hist = {}, Counter()
    last_scan, emitted = 0., False
    def drain(force=False):
        nonlocal last_scan, emitted
        if not force and time.monotonic() - last_scan < .5:
            return False
        last_scan = time.monotonic()
        paths = [Path(str(prefix)+'.best.txt'), Path(str(prefix)+'.current.txt'),
                 *sorted(Path(str(prefix)+'.archive').glob('*.txt'))]
        for path in paths:
            if not path.exists():
                continue
            state, text = safe.base.snapshot(path, n)
            digest = safe.base.term_set_sha256(state)
            if digest in seen:
                continue
            safe.base.freeze(output/'.raw-native-returns'/(digest+'.txt'), text)
            seen[digest] = dict(rank=len(state), raw_sha256=safe.base.sha(text),
                               source_snapshot=str(path.relative_to(output)), factor_multiplicities=factor_multiplicities(state))
            rank_hist[len(state)] += 1
            if len(state) <= target:
                candidate = safe.base.encode_candidate(state, n, method='bounded-native-portfolio7',
                                                       profile=profile, native_command=argv)
                emitted = safe.retain_target(output, candidate, fresh, target=target) or emitted
        return emitted
    if not fresh('pre_native_launch'):
        return dict(status='STOPPED_BEFORE_NATIVE', native_queries_started=0, profile=profile, command=argv)
    with (output/'worker.log').open('x') as log:
        execution = safe.base.run_child(argv, log, lambda: not fresh('loop'), drain, wall_seconds=seconds)
    drain(True)  # Includes a successful return that precedes the first polling tick.
    fresh('post_owned_child_return')
    stats_path = Path(str(prefix)+'.stats.json')
    stats = safe.base.read(stats_path)[0] if stats_path.exists() else None
    if stats is not None:
        validate_stats(stats, profile, n, target)
    checks, final_pair_ranks = {}, {}
    for name in ['best', 'current']:
        path = Path(str(prefix)+'.'+name+'.txt')
        if not path.exists():
            continue
        state, text = safe.base.snapshot(path, n)
        candidate = safe.base.encode_candidate(state, n)
        payload = safe.base.raw_json(candidate)
        if fresh('pre_final_'+name):
            first = safe.verify_candidate(candidate, random_trials=0)
            if not fresh('post_final_'+name+'_primary'):
                continue
            second = safe.independent(candidate, payload)
            if not fresh('post_final_'+name+'_independent'):
                continue
            if not first['valid'] or not second['valid'] or first['exact_entries_checked'] != n**6 or second['exact_entries_checked'] != n**6:
                raise ValueError('final native state failed full double verification')
            checks[name] = dict(primary=first, independent=second, raw_sha256=safe.base.sha(text))
            final_pair_ranks[name] = opposite_pair_ranks(state)
    cpu = execution['child_cpu_seconds']
    histogram = stats.get('rank_excess_residency_steps', {}) if stats else {}
    above = sum(value for key, value in histogram.items() if int(key) > 0)
    metrics = dict(raw_canonical_unique=len(seen), raw_productcount_histogram=dict(sorted(rank_hist.items())),
        raw_canonical_hashes=sorted(seen), above_best_residency_steps=above,
        rank_excess_residency_steps=histogram, final_opposite_pair_ranks=final_pair_ranks,
        final_min_opposite_pair_rank={key: min(value) for key, value in final_pair_ranks.items()},
        child_cpu_seconds=cpu, raw_unique_per_child_cpu_second=len(seen)/cpu if cpu else None,
        steps_per_child_cpu_second=stats['steps']/cpu if stats and cpu else None,
        above_best_steps_per_child_cpu_second=above/cpu if cpu else None,
        repetition_semantics='Per-axis equal-factor multiplicities, invariant under invertible factor bases.',
        dwell_semantics='Native reduction-dwell; NOT the separate dwell-hold-rank prototype.')
    summary = dict(status='TARGET_EMITTED_TO_GLOBAL_GUARD' if emitted else 'UNKNOWN_WITHIN_PROFILE',
        native_queries_started=1, profile=profile, execution=execution, command=argv, stats=stats,
        stats_sha256=safe.base.sha(stats_path.read_bytes()) if stats_path.exists() else None,
        eligible_target_emitted=emitted, final_full_checks=checks, final_checks_complete=set(checks)=={'best', 'current'},
        exploration_metrics=metrics, raw_exports=seen,
        claim='Bounded exact exploration only. Revisited93states are not a new mathematical result; no novelty, superiority or lower-bound claim.')
    safe.base.atomic(output/'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args(argv)
    bundle, output = args.bundle.resolve(), args.output_dir.resolve()
    raw_manifest = (bundle/'manifest.json').read_bytes()
    if safe.base.sha(raw_manifest) != args.expected_manifest_sha256:
        raise ValueError('root-reviewed portfolio manifest pin differs')
    manifest = json.loads(raw_manifest)
    for name, expected in manifest['files'].items():
        path = (bundle/name).resolve(strict=True)
        if not path.is_relative_to(bundle) or safe.base.sha(path.read_bytes()) != expected:
            raise ValueError('frozen portfolio runtime/input differs: ' + name)
    profile = next(p for p in manifest['profiles'] if p['id'] == args.profile_id)
    validate_profile(profile)
    campaign = Path(manifest['campaign'])
    if output != campaign/profile['id'] or output.exists() or args.output_dir.is_symlink():
        raise ValueError('exact new profile output required; no resume or overwrite')
    config_raw = (campaign/'campaign.json').read_bytes()
    if safe.base.sha(config_raw) != manifest['campaign_sha256']:
        raise ValueError('root-pinned campaign policy differs')
    guard = lifecycle.Guard(DEADLINE, 135, campaign, campaign/'operations-v3/state.json', manifest['campaign_sha256'])
    guard.canonical = CampaignGuard(135, guard.hard.isoformat(), (), campaign/'operations-v3/state.json', campaign_dir=campaign)
    guard('pre_portfolio_input')
    if time.time()+150 > guard.hard.timestamp():
        raise ValueError('150second outer envelope cannot fit campaign deadline')
    source = manifest['sources'][str(profile['source_id'])]
    payload = (bundle/source['file']).read_bytes()
    audit = json.loads((bundle/'source-audit.json').read_bytes())['sources'][str(profile['source_id'])]
    if (safe.base.sha(payload) != source['sha256'] or source['sha256'] != audit['raw_sha256']
            or audit['eligibility'] != 'ELIGIBLE_ROOT_APPROVED_TRAIN_NATIVE_ROOT' or audit['heldout_evaluation_ancestors'] is not False):
        raise ValueError('approved training source/audit binding differs')
    candidate = json.loads(payload)
    primary, independent = safe.verify_candidate(candidate, random_trials=0), safe.independent(candidate, payload)
    guard('post_input_full_double_verification')
    terms = safe.base.canonical_terms(candidate)
    if (not primary['valid'] or not independent['valid'] or independent['essential_rank'] != 93
            or primary['exact_entries_checked'] != 15625 or independent['exact_entries_checked'] != 15625
            or profile['cyclic'] and not c3_closed(terms)):
        raise ValueError('source exactness or cyclic-mode precondition differs')
    binary = bundle/'native/plus-burst-worker'
    if safe.base.sha(binary.read_bytes()) != BINARY_SHA:
        raise ValueError('audited plus-burst binary differs')
    metadata = dict(profile=profile, native_seconds=120, outer_seconds=150, cpu=0, memory_mib=768,
        archive_cap=16, profile_output_cap_bytes=22*MIB, total_output_cap_bytes=150*MIB,
        manifest_sha256=args.expected_manifest_sha256, source_sha256=source['sha256'], binary_sha256=BINARY_SHA,
        primary=primary, independent=independent, deadline=guard.hard.isoformat())
    if args.preview:
        print(json.dumps(dict(status='PREVIEW_ONLY', zero_mutations=True, **metadata), sort_keys=True))
        return 0
    os.sched_setaffinity(0, {0})
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    if nice < 10:
        os.nice(10-nice)
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    limits = [768*MIB] + [value for value in (soft, hard) if value != resource.RLIM_INFINITY]
    resource.setrlimit(resource.RLIMIT_AS, (min(limits), hard))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    output.mkdir(parents=True, exist_ok=False)
    safe.base.freeze(output/'manifest.json', safe.base.raw_json(metadata))
    safe.base.freeze(output/'.input.candidate.raw', payload)
    budget = SpaceBudget(campaign, bundle, [p['id'] for p in manifest['profiles']], output)
    reason = None
    def fresh(barrier):
        nonlocal reason
        try:
            guard(barrier)
            budget.check()
            return True
        except (lifecycle.Stop, OutputHold) as error:
            reason = str(error)
            return False
    summary = execute(binary, terms, output, fresh, profile)
    summary.update(stop_reason=reason, guard_final=guard.observation(),
                   output_bytes=budget.size(output), portfolio_output_bytes=budget.total_bytes)
    safe.base.atomic(output/'summary.json', summary)
    print(json.dumps({key: summary.get(key) for key in ['status', 'native_queries_started', 'eligible_target_emitted',
        'final_checks_complete', 'execution', 'stop_reason', 'exploration_metrics']}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
