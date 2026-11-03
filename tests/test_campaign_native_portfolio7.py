"""Tiny native controls and exact publication/stop/cap checks; no n5 search."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mmsearch.search import encode_candidate, decode_candidate, naive_terms
from mmsearch.tensor import strassen_candidate
from scripts import campaign_native_portfolio7 as portfolio

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('PORTFOLIO7_TEST_BINARY', ROOT/'artifacts/rl_campaign42_20261103T033116Z/plus-burst42-pilot-ready-v1/native/plus-burst-worker'))


def profile(**changes):
    return dict(id='tiny-control', source_id=0, seed=3, cyclic=False, plus_burst=1,
                reduction_dwell=0, plus_every=20000, **changes) if not changes else {
                **profile(), **changes}


class PortfolioControls(unittest.TestCase):
    def test_profile_command_flags_and_strict_budgets(self):
        for cyclic in [False, True]:
            for burst in [1, 4]:
                p = profile(cyclic=cyclic, plus_burst=burst, reduction_dwell=128, plus_every=2000, seed=20261103140901)
                argv = portfolio.command('worker', 'input', 'output', p)
                self.assertEqual('--cyclic' in argv, cyclic)
                for key, value in {'--seconds':'120', '--archive-size':'16', '--max-rank':'105', '--reduction-dwell':'128',
                                   '--plus-burst':str(burst), '--plus-every':'2000'}.items():
                    self.assertEqual(argv[argv.index(key)+1], value)
                self.assertNotIn('--dwell-hold-rank', argv)
                self.assertNotIn('--allow-arbitrary', argv)
        for p, seconds in [(profile(seed=portfolio.safe.SEED), 120), (profile(), 121), (profile(plus_burst=True), 120), (profile(reduction_dwell=1), 120)]:
            with self.assertRaises(ValueError):
                portfolio.command('w', 'i', 'o', p, seconds=seconds)

    def test_early_positive_and_final_two_verifiers(self):
        with tempfile.TemporaryDirectory() as d:
            result = portfolio.execute(BINARY, naive_terms(2), d, lambda *_:True, profile(),
                                       seconds=2, n=2, target=7, steps=200000)
            self.assertEqual(result['execution']['exit_code'], 0)
            self.assertTrue(result['eligible_target_emitted'])
            self.assertTrue(result['final_checks_complete'])
            self.assertEqual(result['final_full_checks']['best']['primary']['exact_entries_checked'], 64)
            self.assertEqual(result['final_full_checks']['current']['independent']['exact_entries_checked'], 64)
            self.assertTrue(list((Path(d)/'records').glob('*.json')))
            self.assertFalse((Path(d)/'WINNER.json').exists())
            self.assertGreater(result['exploration_metrics']['raw_unique_per_child_cpu_second'], 0)

    def test_late_positive_retains_only_hidden_raw(self):
        good = encode_candidate(decode_candidate(strassen_candidate(2), 2), 2)
        with tempfile.TemporaryDirectory() as d:
            accepted = portfolio.safe.retain_target(d, good, lambda phase:phase!='post_target_strict_independent', target=7)
            self.assertFalse(accepted)
            self.assertTrue(list((Path(d)/'.raw-native-returns').glob('*.candidate.raw')))
            self.assertFalse((Path(d)/'records').exists())

    def test_false_primary_positive_does_not_bypass_strict_independent(self):
        bad = encode_candidate([(1, 1, 1)], 5)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(portfolio.safe, 'verify_candidate',
                return_value={'valid':True, 'exact_entries_checked':15625}):
            with self.assertRaises(ValueError):
                portfolio.safe.retain_target(d, bad, lambda *_:True)
            self.assertFalse((Path(d)/'records').exists())

    def test_prelaunch_stop_and_cyclic_source_precondition_start_no_child(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(portfolio.safe.base, 'run_child', side_effect=AssertionError('no child')):
            result = portfolio.execute(BINARY, naive_terms(2), d, lambda *_:False, profile(), seconds=2, n=2, target=7)
            self.assertEqual(result['native_queries_started'], 0)
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(ValueError, 'cyclic source'):
            portfolio.execute(BINARY, [(1, 2, 4)], d, lambda *_:True, profile(cyclic=True), seconds=2, n=2, target=7)

    def test_output_reserve_guard_and_factor_multiplicity_invariance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            budget = portfolio.SpaceBudget(root, root/'bundle', ['job'], root/'job')
            with mock.patch.object(budget, 'size', return_value=20*portfolio.MIB), self.assertRaises(portfolio.OutputHold):
                budget.check(force=True)
        terms = [(1, 2, 4), (1, 4, 8), (2, 4, 4)]
        # Bijective factor-coordinate renaming preserves the repetition pattern.
        transformed = [(a<<1, b<<2, c<<3) for a, b, c in terms]
        self.assertEqual(portfolio.factor_multiplicities(terms), portfolio.factor_multiplicities(transformed))
        self.assertEqual(portfolio.factor_multiplicities(terms)['u']['multiplicity_histogram'], {1:1, 2:1})

    def test_cyclic_dwell128_profile_native_mode_and_histograms_match(self):
        with tempfile.TemporaryDirectory() as d:
            result = portfolio.execute(BINARY, naive_terms(2), d, lambda *_:True,
                profile(cyclic=True, plus_burst=4, reduction_dwell=128, plus_every=2000),
                seconds=2, n=2, target=1, steps=512)
            self.assertTrue(result['stats']['cyclic'])
            self.assertEqual(result['stats']['reduction_dwell'], 128)
            self.assertEqual(result['stats']['plus_burst'], 4)
            self.assertTrue(result['final_checks_complete'])
            self.assertEqual(sum(result['stats']['rank_residency_steps'].values()), result['stats']['steps'])
            corrupted = copy.deepcopy(result['stats'])
            corrupted['rank_excess_residency_steps'] = {}
            with self.assertRaises(ValueError):
                portfolio.validate_stats(corrupted, result['profile'], 2, 1)


if __name__ == '__main__':
    unittest.main()
