import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel import apply_circuit,decode_checked,pair_column
from mmsearch.free_factor_kernel_wide import native_input,validate_circuit
from mmsearch.free_factor_sat import build_system
from mmsearch.search import decode_candidate
from mmsearch.tensor import strassen_candidate
from scripts.campaign_kernel_walk_wide import export_checkpoints

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'native/free_factor_kernel_worker_wide'


def wide_control():
    baseline=strassen_candidate(2);terms=decode_candidate(baseline,2)
    occupied={(a,b) for a,b,c in terms};pairs=[]
    for a,b,c in terms[:3]:
        for first in range(1,16):
            second=first^a
            if second and (first,b) not in occupied and (second,b) not in occupied:
                pairset=[(a,b),(first,b),(second,b)]
                if not set(pairset)&set(pairs):
                    pairs.extend(pairset);occupied.update(pairset);break
        else:raise AssertionError('cannot plant disjoint triple')
    dictionary=terms+[(a,b,0) for a,b in pairs]
    system=build_system(dictionary,2,'uv',baseline)
    index={tuple(pair):g for g,pair in enumerate(system['pairs'])}
    support=[index[pair] for pair in pairs]
    assert len(set(support))==9
    return system,dict(class_id=2,support=support,witness={'kind':'XOR of three disjoint3circuits'})


class WideKernelTests(unittest.TestCase):
    def test_nine_group_null_move_preserves_full_tensor_and_old_guard_is_not_used(self):
        system,circuit=wide_control();columns=[pair_column(pair,4) for pair in system['pairs']]
        validate_circuit(columns,circuit['support'])
        moved=apply_circuit(system['baseline_vectors'],circuit['support'],8)
        candidate,report=decode_checked(system,moved)
        self.assertTrue(report['valid']);self.assertEqual(report['exact_entries_checked'],64)
        self.assertTrue(native_input(system,[circuit]).startswith(b'MMKERNELWIDE1'))

    @unittest.skipUnless(BINARY.exists(),'wide worker not built')
    def test_native_controlled_wide_update_and_independent_global_decode(self):
        system,circuit=wide_control()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.txt';source.write_bytes(native_input(system,[circuit]));prefix=root/'kernel_walk'
            result=subprocess.run([str(BINARY),'--input',str(source),'--output',str(prefix),'--target','0',
                                   '--steps','1','--seconds','1','--plus-every','1','--headroom','6','--seed','9'],
                                  capture_output=True,text=True,timeout=2)
            self.assertEqual(result.returncode,0,result.stderr)
            raw=json.loads(prefix.with_suffix('.stats.json').read_text())
            self.assertEqual(raw['long_support_attempts'],1)
            self.assertEqual(raw['long_support_accepted'],1)
            self.assertGreater(raw['current_rank'],raw['best_rank'])
            exported=export_checkpoints(prefix,root,system,{'native_seed':9},target=0,final=True)
            self.assertTrue(exported['stats']['full_matrix_verified'])

    @unittest.skipUnless(BINARY.exists(),'wide worker not built')
    def test_nonzero_Pn_and_129_groups_fail_closed_in_python_and_native(self):
        system,circuit=wide_control();columns=[pair_column(pair,4) for pair in system['pairs']]
        bad=list(circuit['support']);bad[0]=next(g for g in range(len(columns)) if g not in bad)
        with self.assertRaises(ValueError):validate_circuit(columns,bad)
        baseline=strassen_candidate(2)
        large=build_system([(a,b,0) for a in range(1,16) for b in range(1,16)],2,'uv',baseline)
        with self.assertRaises(ValueError):validate_circuit([pair_column(p,4) for p in large['pairs']],list(range(129)))
        for which in ('nonkernel','129'):
            with self.subTest(which=which),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'bad.txt'
                if which=='nonkernel':
                    lines=native_input(system,[circuit]).decode().splitlines();lines[-1]=' '.join(map(str,[2,9,*bad]))
                else:
                    raw=native_input(large,[]).decode().splitlines();raw[1]=raw[1].rsplit(' ',1)[0]+' 1'
                    lines=raw+[' '.join(map(str,[2,129,*range(129)]))]
                source.write_text('\n'.join(lines)+'\n')
                result=subprocess.run([str(BINARY),'--input',str(source),'--output',str(root/'bad')],capture_output=True,text=True,timeout=2)
                self.assertNotEqual(result.returncode,0)
                self.assertFalse((root/'bad.stats.json').exists())


if __name__=='__main__':
    unittest.main()
