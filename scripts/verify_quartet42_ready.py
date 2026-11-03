"""Execute quartet controls entirely from a frozen self-contained launch closure."""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.freeze_campaign_dictionary import freeze, json_bytes, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(); bundle = args.bundle.resolve()
    closure = read_json((bundle/'launch-closure.json').read_bytes())
    for name, expected in closure.items():
        if hashlib.sha256((bundle/'code'/name).read_bytes()).hexdigest() != expected:
            raise ValueError('frozen launch closure hash mismatch: '+name)
    tests = importlib.import_module('tests.test_kernel_quartet_block_wide')
    tests.BINARY = bundle/'native-worker'; tests.MATH = bundle/'native-math-driver'
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    if not result.wasSuccessful():
        raise ValueError(log.getvalue())
    freeze(bundle/'controls/tests.log', log.getvalue().encode())
    pilot = bundle/'pilot'; prefix = bundle/'controls/native5-zero'
    native = [str(bundle/'native-worker'), '--input', str(pilot/'kernel_input.txt'),
              '--catalog', str(pilot/'quartets.txt'), '--output', str(prefix), '--seconds', '0', '--target', '92']
    done = subprocess.run(native, capture_output=True, text=True, timeout=5)
    if done.returncode:
        raise ValueError(done.stderr)
    stats = read_json(prefix.with_suffix('.stats.json').read_bytes())
    if stats['quartets_considered'] != 0 or stats['status'] != 'UNKNOWN' or stats['baseline_rank'] != 93:
        raise ValueError('native zero-row diagnostic failed')
    empty = bundle/'controls/empty-quartets.txt'; freeze(empty, b'MMKQUARTETS1 0\n')
    launcher = bundle/'code/scripts/campaign_kernel_quartet_block_wide.py'
    common = [sys.executable, '-B', str(launcher), '--dictionary', str(pilot/'inputs/dictionary.json'),
              '--baseline', str(pilot/'inputs/baseline.json'), '--circuits', str(pilot/'inputs/circuits.json'),
              '--quartet-catalog', str(empty), '--binary', str(bundle/'native-worker'), '--seconds', '5']
    first, second = bundle/'controls/runner-empty', bundle/'controls/runner-resume-empty'
    commands = [native]
    for dest, extra in ((first, []), (second, ['--resume-from', str(first)])):
        command = [*common, '--outdir', str(dest), *extra]; commands.append(command)
        done = subprocess.run(command, cwd='/tmp', capture_output=True, text=True, timeout=6)
        if done.returncode:
            raise ValueError(done.stderr)
        summary = read_json((dest/'summary.json').read_bytes())
        if summary['status'] != 'NO_TARGET' or summary['exact_entries_checked'] != 15625 or summary['coverage']['prefix_completed'] != 0:
            raise ValueError('frozen wrapper/resume control failed')
    report = dict(status='PASS', tests=result.testsRun, self_contained_launch_closure_verified=True,
                  frozen_control_script=str(Path(__file__).resolve()), native5_zero_rows=True,
                  native5_PW_checked=True, full_matrix_entries=15625,
                  empty_wrapper_and_hash_resume=True, actual_quartet_catalog_searched=False,
                  command_cwd='/tmp', commands=commands)
    freeze(bundle/'VALIDATION.json', json_bytes(report)); print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
