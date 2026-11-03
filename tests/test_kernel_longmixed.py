"""Bounded controls for sampler attribution; no campaign search is launched."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel import decode_checked
from mmsearch.free_factor_kernel_wide import native_input
from tests.test_kernel_wide import wide_control

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT/'native/free_factor_kernel_worker_longmixed'
PREPARED = ROOT/'artifacts/rl_campaign_20261102T210735Z/kernel-longmixed-prepared-v1'


class LongmixedTests(unittest.TestCase):
    def run_native(self, source, prefix, *arguments):
        return subprocess.run([str(BINARY), '--input', str(source), '--output', str(prefix),
            '--profile', 'longmixed', *arguments], capture_output=True, text=True, timeout=3)

    def test_zero_step_full_n5_control_all_heads_and_independent_decode(self):
        system = json.loads((PREPARED/'system.json').read_bytes())
        for headroom in (16, 32):
            with self.subTest(headroom=headroom), tempfile.TemporaryDirectory() as directory:
                prefix = Path(directory)/'zero'
                result = self.run_native(PREPARED/'kernel_input.txt', prefix,
                    '--steps', '0', '--seconds', '0', '--headroom', str(headroom))
                self.assertEqual(result.returncode, 0, result.stderr)
                stats = json.loads(prefix.with_suffix('.stats.json').read_bytes())
                self.assertEqual(stats['steps'], 0)
                self.assertEqual(stats['best_rank'], 93)
                self.assertEqual(stats['max_rank'], 93+headroom)
                self.assertEqual(stats['pair_count'], 1536)
                self.assertEqual(stats['circuit_count'], 9331)
                self.assertEqual(stats['long_catalog_size'], 69)
                vectors = list(map(int, prefix.with_suffix('.current.w.txt').read_text().split()))
                self.assertEqual(vectors, system['baseline_vectors'])
                _, report = decode_checked(system, vectors)
                self.assertTrue(report['valid'])
                self.assertEqual(report['exact_entries_checked'], 15625)

    def test_nine_support_positive_update_and_half_sampler_attribution(self):
        system, circuit = wide_control()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'input.txt'
            source.write_bytes(native_input(system, [circuit]))
            prefix = Path(directory)/'positive'
            result = self.run_native(source, prefix, '--target', '0', '--steps', '1',
                '--seconds', '1', '--plus-every', '1', '--headroom', '6', '--seed', '0')
            self.assertEqual(result.returncode, 0, result.stderr)
            stats = json.loads(prefix.with_suffix('.stats.json').read_bytes())
            self.assertEqual(stats['explicit_long_draws'], 1)
            self.assertEqual(stats['explicit_long_accepted'], 1)
            self.assertEqual(stats['long_support_accepted'], 1)
            vectors = list(map(int, prefix.with_suffix('.current.w.txt').read_text().split()))
            self.assertNotEqual(vectors, system['baseline_vectors'])
            _, report = decode_checked(system, vectors)
            self.assertTrue(report['valid'])
            self.assertEqual(report['exact_entries_checked'], 64)
            # A tiny n2 sampler control tests the actual branch counters, not a campaign walk.
            prefix = Path(directory)/'mixture'
            result = self.run_native(source, prefix, '--target', '0', '--steps', '4096',
                '--seconds', '1', '--plus-every', '1000', '--headroom', '32', '--seed', '13')
            self.assertEqual(result.returncode, 0, result.stderr)
            stats = json.loads(prefix.with_suffix('.stats.json').read_bytes())
            self.assertEqual(stats['steps'], 4096)
            self.assertEqual(stats['explicit_long_draws']+stats['wide_mixture_draws'], 4096)
            self.assertTrue(.45 < stats['explicit_long_draws']/4096 < .55)
            self.assertEqual(stats['long_support_attempts'], 4096)
            self.assertEqual(stats['long_support_accepted'],
                             stats['explicit_long_accepted']+stats['wide_mixture_long_accepted'])

    def test_invalid_profile_and_non_kernel_guard_fail_before_output(self):
        system, circuit = wide_control()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'input.txt'
            source.write_bytes(native_input(system, [circuit]))
            prefix = Path(directory)/'invalid-profile'
            result = self.run_native(source, prefix, '--profile', 'long-biased-unsupported', '--steps', '0')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('invalid options', result.stderr)
            self.assertFalse(prefix.with_suffix('.stats.json').exists())
            lines = source.read_text().splitlines()
            support = list(circuit['support'])
            support[0] = next(g for g in range(len(system['pairs'])) if g not in support)
            lines[-1] = ' '.join(map(str, [2, 9, *support]))
            source.write_text('\n'.join(lines)+'\n')
            prefix = Path(directory)/'invalid-kernel'
            result = self.run_native(source, prefix, '--steps', '0')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('nonkernel circuit rejected', result.stderr)
            self.assertFalse(prefix.with_suffix('.stats.json').exists())


if __name__ == '__main__':
    unittest.main()
