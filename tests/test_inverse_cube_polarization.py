import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from mmsearch.cube_polarization import polarize_cubes
from mmsearch.inverse_cube_polarization import compress_candidate,identity,patterns,verify_move
from mmsearch.recombine import canonical_terms,encode
from mmsearch.slice_compression import InvalidCertificate
from mmsearch.tensor import naive_candidate
from mmsearch.verify import verify_candidate
from scripts import scan_inverse_cube_polarizations as scanner
from scripts.scan_inverse_cube_polarizations import read_source


class InverseCubePolarizationTests(unittest.TestCase):
    def test_n2_forward13_inverse8_all64_entries(self):
        original=naive_candidate(2);terms=canonical_terms(original)
        forward=polarize_cubes(terms,1,8)
        self.assertEqual(len(forward),13)
        source=encode(forward,2)
        self.assertTrue(verify_candidate(source)['valid'])
        result=compress_candidate(source,seconds=1)
        self.assertEqual(result['final_rank'],8)
        self.assertEqual(canonical_terms(result['candidate']),terms)
        self.assertEqual(result['source_verification']['exact_entries_checked'],64)
        self.assertEqual(result['final_verification']['exact_entries_checked'],64)
        self.assertEqual(result['moves'][0]['rank_drop'],5)
        self.assertFalse(result['winner_eligible'])

    def test_complete_orbits_required_and_corrupt_witness_rejected(self):
        forward=tuple(sorted(polarize_cubes(canonical_terms(naive_candidate(2)),1,8)))
        move=next(patterns(forward,4))
        for term in move['required_terms']:
            partial=set(forward);partial.remove(tuple(term))
            self.assertEqual(list(patterns(partial,4)),[])
        for key in ('c','rank_drop','new_count'):
            corrupt=copy.deepcopy(move);corrupt[key]^=1
            with self.assertRaises(ValueError):verify_move(forward,corrupt,4)
        corrupt=copy.deepcopy(move);corrupt['identity_terms'][0][0]^=1
        with self.assertRaises(ValueError):verify_move(forward,corrupt,4)

    def test_identity_every_small_mask_pair_and_strict_binary(self):
        for a in range(1,16):
            for b in range(1,16):
                if a!=b:self.assertEqual(len(identity(a,b,4)),9)
        for a,b in ((0,1),(1,1),(True,2),(16,1),(-1,2)):
            with self.assertRaises(ValueError):identity(a,b,4)

    def test_hypothetical97_to92_count_is_not_a_multiplication_claim(self):
        # Only the algebraic rank-count implication is tested. This arbitrary
        # 97-term tensor is NOT claimed to be the multiplication tensor.
        nine=set(identity(1,2,25));source=nine-{(1,1,1),(2,2,2)}
        source|={(u,16,32) for u in range(1,91)}
        self.assertEqual(len(source),97)
        move=next(patterns(source,25));new=verify_move(source,move,25)
        self.assertEqual(len(new),92)
        self.assertEqual(move['rank_drop'],5)
        with self.assertRaises(InvalidCertificate):compress_candidate(encode(source,5),seconds=1)

    def test_full_global_parser_strict_no_partial_source_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'walk.current.txt';path.write_text('1 2 3\n')
            raw,candidate,key,_normalization=read_source(path,'full-global-mask')
            self.assertTrue(raw);self.assertTrue(key)
            with self.assertRaises(InvalidCertificate):compress_candidate(candidate,seconds=1)
            path.write_text('1.0 2 3\n')
            with self.assertRaises(ValueError):read_source(path,'full-global-mask')

    def test_scanner_first_record_stop_generic_n2_control_only(self):
        # The eligibility flag/parser are mocked only to exercise scanner
        # control flow with a known exact n2 example, not a research record.
        source=encode(polarize_cubes(canonical_terms(naive_candidate(2)),1,8),2)
        result=compress_candidate(source,seconds=1);result['winner_eligible']=True
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=root/'a.json';b=root/'b.json';a.write_text('{}');b.write_text('{}')
            parsed=(b'{}',source,'hypothetical-n2-key',{})
            with patch.object(scanner.resource,'setrlimit'),patch.object(scanner,'read_source',return_value=parsed):
                with patch.object(scanner,'compress_candidate',return_value=copy.deepcopy(result)) as compress:
                    self.assertEqual(scanner.main(['--input',str(a),'--input',str(b),'--output-dir',str(root/'out')]),0)
                    self.assertEqual(compress.call_count,1)
            raw=(root/'out/WINNER.json').read_bytes()
            from scripts.scan_slice_compressions import _freeze_first_winner
            with self.assertRaises(FileExistsError):_freeze_first_winner(root/'out',naive_candidate(2))
            self.assertEqual((root/'out/WINNER.json').read_bytes(),raw)


if __name__=='__main__':unittest.main()
