"""Reproduce SAT campaign counts with explicit local-feasibility deduplication.

Only recognized frozen campaign encoders are included. Dictionary and other
conditioned search branches are excluded unless a recognized encoder explicitly
records their restrictions; such records receive separate conditional keys.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

SUPPORTED = {
    'exact-multilinear-image-v1', 'exact-multilinear-image-native-xor-v1',
    'koszul-filtered-exact-image-cadical-v1', 'koszul-filtered-exact-image-xor-v1',
    'koszul-p1-p2-filtered-exact-image-cadical-v1', 'koszul-p1-p2-filtered-exact-image-xor-v1',
    'oriented-koszul-p1-p2-exact-image-cadical-v1', 'oriented-koszul-p1-p2-exact-image-xor-v1',
}
RESTRICTION_KEYS = ('slot_supports', 'per_slot_support', 'fixed_factors', 'fixed_coefficients',
                    'conditioning', 'assumptions', 'factor_fixings', 'fixed_active_terms', 'dictionary',
                    'slot_domains', 'slot_constraints', 'nonzero_factors', 'nonzero_constraints',
                    'mandatory_nonzero', 'required_nonzero', 'fixed_active_coefficients')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def summarize(groups):
    values = list(groups.values())
    return dict(neighborhoods=len(values),
        exact_bound_rejected=sum('BOUND' in x['labels'] for x in values),
        solver_unsat=sum('UNSAT' in x['labels'] for x in values),
        bound_and_solver_unsat=sum({'BOUND', 'UNSAT'} <= x['labels'] for x in values),
        negative_union=sum(bool(x['labels'] & {'BOUND', 'UNSAT'}) for x in values),
        sat=sum('SAT' in x['labels'] for x in values),
        unknown_only=sum(x['labels'] == {'UNKNOWN'} for x in values),
        unresolved=sum(not bool(x['labels'] & {'SAT', 'BOUND', 'UNSAT'}) for x in values),
        error_present=sum('ERROR' in x['labels'] for x in values),
        contradictions=sum('SAT' in x['labels'] and bool(x['labels'] & {'BOUND', 'UNSAT'}) for x in values))


def audit(directory, replay=None):
    started = time.monotonic()
    root = Path(directory)
    groups = {}
    raw = Counter()
    workers = []
    excluded = [] if replay is None else replay['excluded_workers']
    diagnostics = []
    replay_workers = {} if replay is None else {item['worker']: item for item in replay['workers']}
    paths = sorted(root.glob('*/results.jsonl')) if replay is None else [root/name/'results.jsonl' for name in sorted(replay_workers)]
    for path in paths:
        manifest_path = path.parent/'manifest.json'
        frozen = replay_workers.get(path.parent.name)
        if frozen is not None:
            manifest = dict(identity=frozen['identity'], encoding=frozen['encoding'], attempts=frozen['manifest_attempts'])
            if manifest['encoding'] == 'baseline-local-cnf':
                manifest['encoding'] = None
            manifest_sha = frozen['manifest_sha256']
        elif not manifest_path.exists():
            excluded.append(dict(worker=path.parent.name, reason='no campaign manifest'))
            continue
        else:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
            manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        encoding = manifest.get('encoding')
        if encoding not in SUPPORTED and not (encoding is None and path.parent.name == 'sat'):
            excluded.append(dict(worker=path.parent.name, reason='unrecognized or conditioned encoder', encoding=encoding))
            continue
        identity = manifest.get('identity', {})
        if type(identity.get('dimension')) is not int or type(identity.get('target_rank')) is not int:
            excluded.append(dict(worker=path.parent.name, reason='missing tensor identity'))
            continue
        content = path.read_bytes()
        if frozen is not None:
            content = content[:frozen['results_bytes']]
            if len(content) != frozen['results_bytes'] or hashlib.sha256(content).hexdigest() != frozen['results_sha256']:
                raise ValueError(f'replay prefix does not match snapshot hash: {path}')
        lines = content.decode().splitlines()
        local = Counter()
        for number, line in enumerate(lines, 1):
            try:
                event = json.loads(line)
            except ValueError as exc:
                partial_tail = number == len(lines) and not content.endswith(b'\n')
                diagnostics.append(dict(worker=path.parent.name, line=number,
                    kind='partial_live_tail' if partial_tail else 'malformed_record', error=str(exc)))
                continue
            kind = event.get('event')
            if kind not in ('solve', 'koszul_reject'):
                continue
            try:
                patch = event['patch']
                active, dropped = patch['active_terms'], patch['drop_term']
                if (not isinstance(active, list) or not active or type(dropped) is not int or
                        any(type(x) is not int for x in active) or len(set(active)) != len(active) or dropped in active):
                    raise ValueError('invalid active/deleted source indices')
                selected = sorted(active+[dropped])
                if min(selected) < 0 or max(selected) > identity['target_rank']:
                    raise ValueError('source index outside target_rank+1 terms')
                if patch.get('active_count', len(active)) != len(active):
                    raise ValueError('active_count disagrees with active indices')
                source = patch['source_sha256']
                if not isinstance(source, str) or len(source) != 64 or any(c not in '0123456789abcdef' for c in source):
                    raise ValueError('invalid canonical source SHA256')
                problem = event.get('problem', {})
                if kind == 'solve' and problem.get('field') != 2:
                    raise ValueError('recognized campaign solve must declare field2')
                if kind == 'koszul_reject' and patch.get('koszul', {}).get('field') != 2:
                    raise ValueError('bound report must declare exact field2')
                label = 'BOUND' if kind == 'koszul_reject' else event['status']
                if label not in ('BOUND', 'SAT', 'UNSAT', 'UNKNOWN', 'ERROR'):
                    raise ValueError('unrecognized result status')
                restriction = {}
                for location, data in (('problem', problem), ('patch', patch)):
                    for key in RESTRICTION_KEYS:
                        if data.get(key):
                            restriction[location+'.'+key] = data[key]
                support = problem.get('support_mode', patch.get('support_mode'))
                if support not in ('union', 'full', 'image', 'multilinear-image'):
                    restriction['unsupported_support_mode'] = support
                descriptor = dict(field=2, dimension=identity['dimension'], source_sha256=source,
                    selected_source_terms=selected, replacement_slots=len(active))
                if restriction:
                    descriptor['conditional_restrictions'] = restriction
                    descriptor['worker'] = path.parent.name
                key = digest(descriptor)
                entry = groups.setdefault(key, dict(descriptor=descriptor, labels=set(), workers=set(),
                    solve_records=0, bound_records=0, patch_ids=set()))
                entry['labels'].add(label)
                entry['workers'].add(path.parent.name)
                entry['patch_ids'].add(patch['patch_id'])
                entry['bound_records' if label == 'BOUND' else 'solve_records'] += 1
                raw[label] += 1
                local[label] += 1
            except (KeyError, TypeError, ValueError) as exc:
                diagnostics.append(dict(worker=path.parent.name, line=number, kind='invalid_record', error=str(exc)))
        workers.append(dict(worker=path.parent.name, encoding=encoding or 'baseline-local-cnf',
            identity=identity, raw_record_counts=dict(local), manifest_attempts=manifest.get('attempts'),
            results_bytes=len(content), results_sha256=hashlib.sha256(content).hexdigest(),
            manifest_sha256=manifest_sha))
    uniform = {key: value for key, value in groups.items() if 'conditional_restrictions' not in value['descriptor']}
    conditional = {key: value for key, value in groups.items() if key not in uniform}
    summary = summarize(uniform)
    serializable = {key: dict(value, labels=sorted(value['labels']), workers=sorted(value['workers']),
                              patch_ids=sorted(value['patch_ids'])) for key, value in groups.items()}
    valid = not summary['contradictions'] and not any(item['kind'] != 'partial_live_tail' for item in diagnostics)
    return dict(recorded_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), campaign=str(root), audit_valid=valid,
        replay_of_utc=None if replay is None else replay['recorded_utc'],
        scope='local frozen replacement neighborhoods only; no global matrix-multiplication rank lower bound',
        deduplication='field,dimension,canonical-source-SHA256,selected-source-index-set,replacement-slot-count; uniform union/full/image identified by projection proof',
        equivalence_assumptions=['all mutable slots share one coordinate support on each axis',
            'support union includes all selected source terms including the deleted term',
            'no guessed fixed factors, nonzero requirements, dictionary constraints, or per-slot support masks',
            'coefficients are unrestricted GF2 scalars, canonically represented by0/1',
            'exact mode-image projection preserves <=K products; zero mutable slots allowed',
            'U-lex only permutes mutable slots with identical domains'],
        raw_record_counts=dict(raw), uniform_summary=summary, conditional_summary=summarize(conditional),
        workers=workers, excluded_workers=excluded, diagnostics=diagnostics,
        neighborhoods=serializable, elapsed_seconds=time.monotonic()-started,
        audit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


def write_report(report, prefix):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix('.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    s = report['uniform_summary']
    text = f"""# Local SAT audit

Snapshot: {report['recorded_utc']}. Recognized workers: {len(report['workers'])}.

There are {s['neighborhoods']:,} distinct uniform-domain frozen neighborhoods:
{s['exact_bound_rejected']:,} have exact Koszul rejections, {s['solver_unsat']:,}
have solver UNSAT results, {s['unknown_only']:,} remain UNKNOWN-only, and
{s['sat']:,} have SAT results. Bound/UNSAT overlap: {s['bound_and_solver_unsat']}.
Contradictions: {s['contradictions']}. Error-containing neighborhoods: {s['error_present']}.
These counts do not establish a global matrix-multiplication rank bound.

Uniform union, full-coordinate, and exact image-coordinate formulations are
identified: projecting each factor of any K-product residual decomposition
onto the three residual mode images preserves the tensor and number of slots;
the images lie inside the shared source-support union. All mutable slots use
that same union, zeros are allowed, and U-lex only reorders identical-domain
products. Different deleted slots within one selected subset merely relabel
mutable products; the frozen complement and residual remain identical.

Nonuniform supports, guessed factor fixings, dictionary restrictions, and other
recorded conditioning receive separate conditional keys. Unrecognized encoders
are excluded. Conditional groups: {report['conditional_summary']['neighborhoods']}.
Excluded worker logs: {len(report['excluded_workers'])}. Diagnostics: {len(report['diagnostics'])}.

Raw result counts are {json.dumps(report['raw_record_counts'], sort_keys=True)};
these include intentional backend, symmetry, budget, and heuristic repeats.
The companion JSON contains every derived key, contributing patch/worker IDs,
input-log hashes, prefix byte counts, manifest identities/hashes, exclusions,
and diagnostics. Reproduce a live snapshot after workers append more data with
`python scripts/campaign_sat_audit.py CAMPAIGN --replay-snapshot SNAPSHOT.json --output-prefix PREFIX`.
Replay verifies each recorded log prefix against its saved hash and uses the
saved identity rather than a newer manifest. Normal invocation omits the replay
flag and audits all currently recognized worker logs.
"""
    prefix.with_suffix('.md').write_text(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--output-prefix', type=Path, required=True)
    parser.add_argument('--replay-snapshot', type=Path)
    args = parser.parse_args(argv)
    replay = None if args.replay_snapshot is None else json.loads(args.replay_snapshot.read_text())
    report = audit(args.campaign, replay=replay)
    write_report(report, args.output_prefix)
    print(json.dumps({key: report[key] for key in ('recorded_utc', 'audit_valid', 'raw_record_counts',
        'uniform_summary', 'conditional_summary', 'elapsed_seconds')}, sort_keys=True))
    return 0 if report['audit_valid'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
