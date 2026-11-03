import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mmsearch.search import naive_terms
from mmsearch.cube_polarization import polarize_cubes
from scripts import campaign_fixed_one_cube as campaign


class OneCubeProfileTests(unittest.TestCase):
    def launch(self, extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'seed.json'; source.write_text('{"dimension":5}')
            binary = root/'worker'; binary.write_bytes(b'fake binary')
            output = root/'output'
            argv = ['campaign', '--binary', str(binary), '--input', str(source),
                    '--pool', str(root/'pool'), '--output-dir', str(output), '--seconds', '1', '--deadline-utc','2099-01-01T00:00:00Z', *extra]
            commands = []
            class Worker:
                returncode = 0
                def __init__(self, command, **kwargs):
                    commands.append(command)
                    prefix = Path(command[command.index('--output')+1])
                    prefix.with_suffix('.stats.json').write_text('{}')
                def poll(self): return 0
                def wait(self, **kwargs): return 0
            result = dict(winner=False, best_record=None, verified=0, buckets={})
            with patch('sys.argv', argv), patch.object(campaign, 'canonical_terms', return_value=[(1,2,3)]*100), \
                 patch.object(campaign, 'is_cyclic', return_value=True), \
                 patch.object(campaign, 'orbit_counts', return_value={'fixed_cubes':1}), \
                 patch.object(campaign, 'orbit_inventory', return_value={}), \
                 patch.object(campaign, 'verify_candidate', return_value={'valid':True}), \
                 patch.object(campaign, 'encode_candidate', return_value={}), \
                 patch.object(campaign.subprocess, 'Popen', Worker), \
                 patch.object(campaign.time, 'monotonic', side_effect=[0,0,0,2]), \
                 patch.object(campaign, 'drain_verified', return_value=result) as drain:
                campaign.main()
            self.assertEqual(drain.call_count, 1) # completed workers always get final drain
            manifest = json.loads((output/'phase-000/manifest.json').read_text())
            self.assertEqual(manifest['source_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest['binary_sha256'], hashlib.sha256(binary.read_bytes()).hexdigest())
            return commands[0], manifest

    def test_defaults_and_custom_profile_are_passed_to_fixed_cyclic_worker(self):
        for extra, expected in [([], (50000,100000000,6,16)),
                                (['--plus-every','70000','--restart-every','90000000',
                                  '--headroom','9','--archive-size','8'], (70000,90000000,9,8))]:
            command, manifest = self.launch(extra)
            plus, restart, headroom, archive = expected
            for flag, value in [('--plus-every',plus),('--restart-every',restart),
                                ('--max-rank',100+headroom),('--archive-size',archive),
                                ('--target',92),('--fixed-cubes',1)]:
                self.assertEqual(command[command.index(flag)+1], str(value))
            self.assertIn('--cyclic', command)
            self.assertEqual(manifest['profile'], 'fixed-one-cube-v1')
            self.assertEqual((manifest['plus_every'],manifest['restart_every'],manifest['headroom']),
                             (plus,restart,headroom))

    def test_invalid_bounds_fail_before_io(self):
        for flag, value in [('--plus-every','0'),('--plus-every','1000000000001'),
                            ('--restart-every','-1'),('--restart-every','1000000000001'),
                            ('--headroom','0'),('--headroom','10'),('--archive-size','33'),
                            ('--deadline-utc','2026-11-03T03:07:35'),('--seconds','nan'),('--phase-seconds','inf'),('--target','95')]:
            argv = ['campaign','--binary','missing','--input','missing','--pool','missing',
                    '--output-dir','missing','--seconds','1',flag,value]
            with patch('sys.argv',argv), patch('sys.stderr'), self.assertRaises(SystemExit) as error:
                campaign.main()
            self.assertEqual(error.exception.code,2)

    def test_positive_control_final_drain(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); prefix=root/'walk'
            prefix.with_suffix('.best.txt').write_text(''.join(f'{a} {b} {c}\n' for a,b,c in polarize_cubes(naive_terms(2),1,8)))
            result=campaign.drain_verified(prefix,root,{},n=2,target=13,max_rank=13)
            self.assertTrue(result['winner'])
            self.assertTrue(json.loads((root/'WINNER.verification.json').read_text())['valid'])
            self.assertEqual(json.loads((root/'WINNER.json').read_text())['metadata']['orbit_profile']['fixed_cubes'],1)

if __name__ == '__main__':
    unittest.main()
