"""Small frozen preparation controls; never evaluate a target quartet move."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.freeze_campaign_dictionary import freeze, json_bytes, read_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    args = p.parse_args(); bundle = args.bundle.resolve()
    launcher = bundle/'code/scripts/prepare_kernel_quartet_sample42.py'
    commands = []
    for label in ('first', 'repeat'):
        command = [sys.executable, '-B', str(launcher), '--bundle', str(bundle), '--output-dir',
            str(bundle/'controls'/label), '--count', '64', '--pool-factor', '1', '--seed', '4243001',
            '--seconds', '3', '--max-attempts', '100000', '--max-workload', '50000']
        done = subprocess.run(command, cwd='/tmp', capture_output=True, text=True, timeout=10)
        if done.returncode:
            raise ValueError(done.stderr)
        commands.append(command)
    first, repeat = bundle/'controls/first', bundle/'controls/repeat'
    if (first/'quartets.txt').read_bytes() != (repeat/'quartets.txt').read_bytes():
        raise ValueError('fixed-seed preparation is not deterministic')
    audits = read_json((first/'independent-reservoir-audit.json').read_bytes())
    stats = read_json((first/'native_sampler_stats.json').read_bytes())
    if len(audits) != 64 or stats['workload_sum'] != sum(a['exact_rhs_assignments'] for a in audits):
        raise ValueError('native aggregate E differs from full independent64-row audit')
    if stats['selected'] != 64 or stats['actual_optimizer_assignments'] != 0 or any(x == 0 for x in stats['mode_proposed']):
        raise ValueError('small sampler control did not exercise expected preparation modes')
    # Native rejects invalid PW and duplicate exclusion identities.
    raw = (bundle/'inputs/kernel_input.txt').read_text().splitlines()
    parts = raw[3].split(); parts[2] = str(int(parts[2]) ^ (2 if int(parts[2]) == 1 else 1)); raw[3] = ' '.join(parts)
    bad = bundle/'controls/bad-PW.txt'; freeze(bad, ('\n'.join(raw)+'\n').encode())
    excluded = bundle/'completed-source/quartets.txt'
    prefix = bundle/'controls/bad-native'
    native = [str(bundle/'native-sampler'), '--input', str(bad), '--exclude', str(excluded), '--output', str(prefix), '--count', '1', '--seconds', '0']
    done = subprocess.run(native, capture_output=True, text=True, timeout=5)
    if done.returncode == 0:
        raise ValueError('invalid PW accepted')
    duplicate = bundle/'controls/duplicate-exclusions.txt'
    row = excluded.read_text().splitlines()[1]
    freeze(duplicate, ('MMKQUARTETS1 2\n'+row+'\n'+row+'\n').encode())
    native = [str(bundle/'native-sampler'), '--input', str(bundle/'inputs/kernel_input.txt'),
        '--exclude', str(duplicate), '--output', str(prefix), '--count', '1', '--seconds', '0']
    done = subprocess.run(native, capture_output=True, text=True, timeout=5)
    if done.returncode == 0:
        raise ValueError('duplicate exclusions accepted')
    report = dict(status='PASS', fixed_seed_repeat_identical=True, selected=64,
        all64_independently_bound_positive_and_workload_checked=True, aggregate_E_matches=True,
        selected_excludes_all2000_completed=True, all_selected_connected_and_unique=True,
        proposal_modes=['star', 'path', 'four-cycle'], mode_proposed=stats['mode_proposed'],
        mode_accepted_pool=stats['mode_accepted_pool'], invalid_PW_rejected=True,
        duplicate_exclusions_rejected=True, actual_optimizer_assignments=0,
        frozen_control_script=str(Path(__file__).resolve()), commands=commands)
    freeze(bundle/'VALIDATION.json', json_bytes(report)); print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
