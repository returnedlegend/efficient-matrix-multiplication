from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mmsearch.free_factor_kernel import native_input,prepare_system
from mmsearch.search import decode_candidate
from scripts.campaign_kernel_walk_v2 import export_checkpoints
from tests.test_slice_compression import expanded_naive

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'native/free_factor_kernel_worker'


@unittest.skipUnless(BINARY.exists(),'native kernel worker not built')
class KernelWalkV2Tests(unittest.TestCase):
    def raw_control(self,root,target=8):
        baseline,_=expanded_naive(2,0)
        system,circuits,summary=prepare_system(decode_candidate(baseline,2),baseline,dimension=2,orientation='wu',max_circuits=64)
        self.assertEqual(sum(bool(w) for w in system['baseline_vectors']),9)
        source=root/'input.txt';source.write_bytes(native_input(system,circuits));prefix=root/'kernel_walk'
        result=subprocess.run([str(BINARY),'--input',str(source),'--output',str(prefix),'--target',str(target),
                               '--seconds','0','--steps','0','--seed','3'],capture_output=True,text=True,timeout=2)
        self.assertEqual(result.returncode,0,result.stderr)
        return system,prefix

    def test_raw9_post8_first_winner_is_immutable_and_final_drain_skips_compression(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);system,prefix=self.raw_control(root);callbacks=[]
            result=export_checkpoints(prefix,root,system,{'native_seed':3},target=8,final=True,
                                      slice_compress=True,compression_seconds=.25,on_record=lambda:callbacks.append('stop'))
            self.assertTrue(result['winner']);self.assertEqual(callbacks,['stop'])
            self.assertEqual(result['stats']['best_rank'],9)
            self.assertEqual(result['stats']['primary_candidate_rank'],8)
            self.assertEqual(result['stats']['best_verified_rank'],8)
            self.assertFalse(result['stats']['target_reached'])
            self.assertTrue(result['stats']['campaign_target_reached'])
            primary=root/'WINNER.json';before=primary.read_bytes()
            self.assertEqual(len(json.loads(before)['terms']),8)
            self.assertFalse(primary.stat().st_mode&0o222)
            with patch('scripts.campaign_kernel_walk_v2.compress_candidate',side_effect=AssertionError('must skip after record')):
                again=export_checkpoints(prefix,root,system,{'native_seed':3},target=8,final=True,
                                         slice_compress=True,on_record=lambda:callbacks.append('again'))
            self.assertTrue(again['winner']);self.assertEqual(primary.read_bytes(),before)
            self.assertEqual(callbacks,['stop'])
            self.assertEqual((root/'WINNER.sha256').read_text().split()[0],hashlib.sha256(before).hexdigest())

    def test_compression_happens_before_raw_storage_cap_and_processed_hash_is_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);system,prefix=self.raw_control(root,target=7);counts=Counter({9:32})
            first=export_checkpoints(prefix,root,system,{'native_seed':3},target=7,final=True,
                                     slice_compress=True,counts=counts)
            self.assertFalse(first['winner'])
            self.assertFalse((root/'verified').exists())
            self.assertEqual(len(list((root/'derived').glob('*.verification.json'))),1)
            self.assertEqual(json.loads((root/'best_verified.json').read_text())['rank'],8)
            with patch('scripts.campaign_kernel_walk_v2.compress_candidate',side_effect=AssertionError('cached state must skip')):
                export_checkpoints(prefix,root,system,{'native_seed':3},target=7,final=True,
                                   slice_compress=True,counts=counts)
            state=json.loads((root/'compression_state.json').read_text())
            self.assertEqual(state['attempts'],1)


if __name__=='__main__':
    unittest.main()
