import json
from pathlib import Path
import tempfile
import unittest

from mmsearch.search import decode_candidate,naive_terms
from mmsearch.tensor import strassen_candidate
from scripts.campaign_fixed_cubes import drain_verified


class FixedCubeDrainTests(unittest.TestCase):
    def test_positive_control_final_drain_freezes_exact_two_cube_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'walk'
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in naive_terms(2)))
            result=drain_verified(prefix,root,{},n=2,target=8,max_rank=11)
            self.assertTrue(result['winner'])
            candidate=json.loads((root/'WINNER.json').read_text())
            self.assertEqual(candidate['metadata']['orbit_profile']['fixed_cubes'],2)
            self.assertTrue(json.loads((root/'WINNER.verification.json').read_text())['valid'])
            # A repeated drain preserves a previously frozen winner.
            self.assertTrue(drain_verified(prefix,root,{},n=2,target=8,max_rank=11)['winner'])

    def test_exact_but_wrong_fixed_cube_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'walk'
            terms=decode_candidate(strassen_candidate(2),2)
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in terms))
            with self.assertRaisesRegex(ValueError,'fixed-two-cube'):
                drain_verified(prefix,root,{},n=2,target=8,max_rank=11)
            self.assertFalse((root/'WINNER.json').exists())


if __name__=='__main__':
    unittest.main()
