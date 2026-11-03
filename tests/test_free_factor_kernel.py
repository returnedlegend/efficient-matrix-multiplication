import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel import (apply_circuit,decode_checked,delta_active,native_input,
                                        enumerate_circuits,pair_column,prepare_system,validate_circuit)
from mmsearch.free_factor_sat import ORIENTATIONS
from mmsearch.search import decode_candidate,encode_candidate
from mmsearch.tensor import strassen_candidate
from scripts.campaign_kernel_walk import export_checkpoints,read_vectors

ROOT=Path(__file__).resolve().parents[1]
BINARY=ROOT/'native/free_factor_kernel_worker'


def planted_split(orientation='uv'):
    original=decode_candidate(strassen_candidate(2),2);first,second,free=ORIENTATIONS[orientation]
    term=original[0];others=original[1:]
    occupied={(item[first],item[second]) for item in others}
    for mask in range(1,16):
        other=mask^term[first]
        if not other or (mask,term[second]) in occupied or (other,term[second]) in occupied:
            continue
        a=list(term);b=list(term);a[first]=mask;b[first]=other
        split=[tuple(a),tuple(b)]
        return original+split,encode_candidate(others+split,2)
    raise AssertionError('no planted split found')


class FreeFactorKernelTests(unittest.TestCase):
    def test_streamed_three_four_and_combo_witnesses_are_exact_kernel_relations(self):
        columns=[1,2,4,7]
        circuits,summary=enumerate_circuits(columns,[9,10,0,0],max_circuits=64,combos=False)
        self.assertEqual(len(circuits),1)
        self.assertEqual(circuits[0]['class_id'],1)
        self.assertEqual(circuits[0]['support'],[0,1,2,3])
        self.assertEqual(circuits[0]['witness']['baseline_active_pair'],[0,1])
        columns=[1,2,3,4,5]
        circuits,summary=enumerate_circuits(columns,[0]*5,max_circuits=64)
        self.assertTrue(any(c['class_id']==0 for c in circuits))
        self.assertTrue(any(c['class_id']==2 for c in circuits))
        for circuit in circuits:
            validate_circuit(columns,circuit['support'])
            if circuit['class_id']==2:
                a,b=circuit['witness']['xor_of']
                self.assertEqual(set(circuit['support']),set(circuits[a]['support'])^set(circuits[b]['support']))

    def test_delta_math_includes_zero_groups_and_reduction(self):
        self.assertEqual(delta_active([0,5,5],[0,1,2],5),-1)
        self.assertEqual(apply_circuit([0,5,5],[0,1,2],5),[5,0,0])
        self.assertEqual(delta_active([0,5,5],[0,1,2],7),1)
        self.assertEqual(delta_active([0,0,0],[0,1,2],1),3)
        with self.assertRaises(ValueError):delta_active([1,2,3],[0,1,2],0)

    def test_orientation_decode_and_exact_five_by_five_baseline(self):
        for orientation in ORIENTATIONS:
            dictionary,baseline=planted_split(orientation)
            system,circuits,summary=prepare_system(dictionary,baseline,dimension=2,orientation=orientation,max_circuits=64)
            candidate,report=decode_checked(system,system['baseline_vectors'])
            self.assertTrue(report['valid']);self.assertEqual(report['rank'],8)
            self.assertTrue(circuits)
        baseline=json.loads((ROOT/'artifacts/km93_f2.json').read_text())
        system,circuits,summary=prepare_system(decode_candidate(baseline,5),baseline,orientation='wu',max_circuits=64)
        candidate,report=decode_checked(system,system['baseline_vectors'])
        self.assertTrue(report['valid']);self.assertEqual(report['exact_entries_checked'],15625)
        self.assertEqual(report['rank'],93)

    def run_worker(self,root,system,circuits,*extra):
        source=root/'input.txt';source.write_bytes(native_input(system,circuits));prefix=root/'kernel_walk'
        result=subprocess.run([str(BINARY),'--input',str(source),'--output',str(prefix),'--target','7',
                               '--seconds','.1','--steps','10000','--seed','3','--archive-every','1',*extra],
                              capture_output=True,text=True,timeout=2)
        return result,prefix

    @unittest.skipUnless(BINARY.exists(),'native kernel worker not built')
    def test_real_three_circuit_recovers_strassen7_and_fast_exit_is_drained(self):
        dictionary,baseline=planted_split()
        system,circuits,summary=prepare_system(dictionary,baseline,dimension=2,orientation='uv',max_circuits=64)
        columns=[pair_column(pair,4) for pair in system['pairs']]
        for circuit in circuits:validate_circuit(columns,circuit['support'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);result,prefix=self.run_worker(root,system,circuits)
            self.assertEqual(result.returncode,0,result.stderr)
            vectors=read_vectors(Path(str(prefix)+'.best.w.txt'),len(system['pairs']),4)
            candidate,report=decode_checked(system,vectors)
            self.assertEqual(report['rank'],7)
            exported=export_checkpoints(prefix,root,system,{'native_seed':3},target=7,final=True)
            self.assertTrue(exported['winner'])
            self.assertTrue(json.loads((root/'WINNER.verification.json').read_text())['valid'])
            stats=json.loads((root/'walk.stats.json').read_text())
            self.assertTrue(stats['full_matrix_verified']);self.assertEqual(stats['best_rank'],7)

    @unittest.skipUnless(BINARY.exists(),'native kernel worker not built')
    def test_nonkernel_circuit_and_corrupt_baseline_fail_closed(self):
        dictionary,baseline=planted_split();system,circuits,summary=prepare_system(dictionary,baseline,dimension=2,max_circuits=64)
        columns=[pair_column(pair,4) for pair in system['pairs']]
        valid=circuits[0]['support'];bad=None
        for index in range(len(columns)):
            trial=[index,*valid[1:]]
            if len(set(trial))==len(trial):
                try:validate_circuit(columns,trial)
                except ValueError:bad=trial;break
        self.assertIsNotNone(bad)
        with self.assertRaises(ValueError):validate_circuit(columns,bad)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'bad.txt'
            lines=native_input(system,[circuits[0]]).decode().splitlines()
            lines[-1]=' '.join(map(str,[0,len(bad),*bad]));source.write_text('\n'.join(lines)+'\n')
            result=subprocess.run([str(BINARY),'--input',str(source),'--output',str(root/'bad')],capture_output=True,text=True,timeout=2)
            self.assertNotEqual(result.returncode,0);self.assertIn('nonkernel',result.stderr)
            corrupted=copy.deepcopy(system);corrupted['baseline_vectors'][0]^=1
            source.write_bytes(native_input(corrupted,circuits))
            result=subprocess.run([str(BINARY),'--input',str(source),'--output',str(root/'corrupt')],capture_output=True,text=True,timeout=2)
            self.assertNotEqual(result.returncode,0);self.assertIn('PW=Y',result.stderr)
            with self.assertRaises(ValueError):decode_checked(system,corrupted['baseline_vectors'])

    @unittest.skipUnless(BINARY.exists(),'native kernel worker not built')
    def test_wall_timeout_checkpoints_all_models_preserve_original_equations(self):
        dictionary,baseline=planted_split();system,circuits,summary=prepare_system(dictionary,baseline,dimension=2,max_circuits=64)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            result,prefix=self.run_worker(root,system,circuits,'--target','0','--seconds','.03','--steps','10000000',
                                          '--plus-every','1','--restart-every','37','--checkpoint-seconds','.01')
            self.assertEqual(result.returncode,0,result.stderr)
            stats=json.loads(prefix.with_suffix('.stats.json').read_text())
            self.assertGreater(stats['steps'],0);self.assertTrue(stats['tensor_invariant_checked'])
            for path in [Path(str(prefix)+'.best.w.txt'),Path(str(prefix)+'.current.w.txt'),
                         *prefix.with_suffix('.archive').glob('*.w.txt')]:
                candidate,report=decode_checked(system,read_vectors(path,len(system['pairs']),4))
                self.assertTrue(report['valid'])


if __name__=='__main__':
    unittest.main()
