import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.search import decode_candidate
from mmsearch.tensor import strassen_candidate
from scripts.campaign_polarized import drain_verified


class PolarizedDrainTests(unittest.TestCase):
    def test_fast_success_final_drain_verifies_and_freezes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);prefix = root/'walk'
            terms = decode_candidate(strassen_candidate(2),2)
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms))
            result = drain_verified(prefix,root,{},n=2,target=7,max_rank=10)
            self.assertTrue(result['winner'])
            report = json.loads((root/'WINNER.verification.json').read_text())
            self.assertTrue(report['valid'])
            self.assertEqual(report['exact_entries_checked'],64)
            self.assertFalse((root/'WINNER.json').stat().st_mode & 0o222)

    def test_corrupt_final_cannot_be_claimed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);prefix = root/'walk'
            prefix.with_suffix('.best.txt').write_text('1 1 1\n')
            with self.assertRaises(RuntimeError):
                drain_verified(prefix,root,{},n=2,target=7,max_rank=10)
            self.assertFalse((root/'WINNER.json').exists())


if __name__ == '__main__':
    unittest.main()
