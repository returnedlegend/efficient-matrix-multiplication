import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.search import decode_candidate
from mmsearch.tensor import strassen_candidate
from scripts.campaign_native import drain_final_best


class FinalNativeCheckpointTests(unittest.TestCase):
    def test_target_written_at_exit_is_verified_and_frozen(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);prefix=folder/'walk'
            triples=decode_candidate(strassen_candidate(2),2)
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in triples))
            self.assertTrue(drain_final_best(prefix,folder,{},n=2,target=7))
            self.assertTrue(json.loads((folder/'WINNER.verification.json').read_text())['valid'])

    def test_invalid_low_rank_final_file_cannot_be_claimed(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);prefix=folder/'walk'
            prefix.with_suffix('.best.txt').write_text('1 1 1\n')
            with self.assertRaises(RuntimeError):drain_final_best(prefix,folder,{},n=2,target=7)
            self.assertFalse((folder/'WINNER.json').exists())
