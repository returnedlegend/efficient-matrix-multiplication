import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.run_campaign_dictionary_phase import run_phase


class DictionaryPhaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.explicit=self.root/'explicit.json';self.explicit.write_text('{}')
        self.directory=self.root/'directory';self.directory.mkdir()
        old=self.directory/'old.json';old.write_text('{}');os.utime(old,(900,900))
        young=self.directory/'young.json';young.write_text('{}');os.utime(young,(990,990))
        nested=self.directory/'nested';nested.mkdir();(nested/'ignored.json').write_text('{}')

    def tearDown(self):
        self.tmp.cleanup()

    def test_freeze_then_solve_budget_selection_and_no_shell_arguments(self):
        elapsed=[0.0];calls=[]
        def runner(command,log_path,timeout):
            calls.append((command,timeout))
            output=Path(log_path).parent
            if len(calls)==1:
                self.assertTrue(command[1].endswith('freeze_campaign_dictionary.py'))
                selected=[command[i+1] for i,arg in enumerate(command) if arg=='--candidate']
                self.assertEqual(set(selected),{str(self.explicit.resolve()),str((self.directory/'old.json').resolve())})
                elapsed[0]=4
            else:
                self.assertTrue(command[1].endswith('campaign_dictionary_preprocessed.py'))
                self.assertEqual(float(command[command.index('--seconds')+1]),16)
                self.assertEqual(command[command.index('--control-seconds')+1],'5')
                (output/'solve').mkdir();(output/'solve/result.json').write_text('{"status":"UNKNOWN"}')
                elapsed[0]=7
            return dict(exit_code=0,timed_out=False)
        result=run_phase(output_dir=self.root/'phase',seconds=20,candidates=[self.explicit],
                         candidate_dirs=[self.directory],runner=runner,clock=lambda:elapsed[0],wall_clock=lambda:1000)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(len(calls),2)
        manifest=json.loads((self.root/'phase/manifest.json').read_text())
        self.assertEqual(len(manifest['skipped_young']),1)
        self.assertEqual(manifest['stages'][1]['exit_code'],0)

    def test_exhausted_total_budget_never_starts_solver(self):
        elapsed=[0.0];calls=[]
        def runner(command,log_path,timeout):
            calls.append(command);elapsed[0]=11
            return dict(exit_code=0,timed_out=False)
        result=run_phase(output_dir=self.root/'exhausted',seconds=10,candidates=[self.explicit],
                         runner=runner,clock=lambda:elapsed[0])
        self.assertEqual(result['status'],'BUDGET_EXHAUSTED')
        self.assertEqual(len(calls),1)
        self.assertFalse((self.root/'exhausted/solve').exists())

    def test_failed_freezer_stops_before_solver(self):
        calls=[]
        def runner(command,log_path,timeout):
            calls.append(command);return dict(exit_code=2,timed_out=False)
        result=run_phase(output_dir=self.root/'failed',candidates=[self.explicit],runner=runner)
        self.assertEqual(result['status'],'ERROR')
        self.assertEqual(len(calls),1)
        self.assertEqual(json.loads((self.root/'failed/manifest.json').read_text())['stages'][0]['exit_code'],2)


if __name__=='__main__':
    unittest.main()
