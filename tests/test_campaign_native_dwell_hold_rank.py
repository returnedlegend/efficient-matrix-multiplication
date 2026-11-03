"""Zero production queries: matched forwarding, preview, positive/negative proof controls."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from mmsearch.search import decode_candidate,encode_candidate
from mmsearch.tensor import strassen_candidate
from scripts.verify_record42_independent import _check_all_basis_outputs
from scripts import campaign_native_dwell_hold_rank as pilot

ROOT=Path(__file__).resolve().parents[1]

class HoldHarnessTests(unittest.TestCase):
    def test_matched_forwarding_and_bounds(self):
        zero=pilot.command('w','i','o',seconds=30,seed=7,hold_rank=0)
        one=pilot.command('w','i','o',seconds=30,seed=7,hold_rank=1)
        self.assertEqual(zero[:-1],one[:-1]);self.assertEqual(zero[-2:],['--dwell-hold-rank','0'])
        for key,value in {'--target':'92','--n':'5','--max-rank':'105','--reduction-dwell':'128','--plus-burst':'4','--plus-every':'20000'}.items():self.assertEqual(one[one.index(key)+1],value)
        for kw in [{'seconds':31,'hold_rank':0},{'seconds':30,'hold_rank':2}]:
            with self.assertRaises(ValueError):pilot.command('w','i','o',seed=1,**kw)

    def test_preview_starts_no_child_and_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=ROOT/'artifacts/rl_campaign42_20261103T033116Z/breadth43-ready-v1/sources/90feb0398e7ee787626aff84bdee638311e6ada128edf8023c1e7d1ef20c2514.json'
            held=root/'held.json';held.write_text(json.dumps({'heldout_source_term_hashes':[str(i)*64 for i in range(1,5)]}))
            binary=root/'fake';binary.write_bytes(b'not executed');(root/'campaign.json').write_text(json.dumps({'dimension':5,'field':2,'target_rank':92,'deadline_utc':'2099-01-01T00:00:00Z'}))
            args=['--campaign',str(root),'--input',str(source),'--binary',str(binary),'--heldout-declaration',str(held),'--output-dir',str(root/'NEW'),
                  '--expected-input-sha256',pilot.base.sha(source.read_bytes()),'--expected-binary-sha256',pilot.base.sha(binary.read_bytes()),
                  '--expected-heldout-sha256',pilot.base.sha(held.read_bytes()),'--expected-runtime-sha256',pilot.base.sha(pilot.base.raw_json(pilot.runtime_hashes())),
                  '--seed','7','--dwell-hold-rank','1','--preview']
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for cpu in [0,3]:
                with mock.patch.object(pilot.base.subprocess,'Popen') as child,contextlib.redirect_stdout(io.StringIO()) as out:pilot.main(args+['--cpu',str(cpu)])
                child.assert_not_called();self.assertTrue(json.loads(out.getvalue())['zero_mutations']);self.assertFalse((root/'NEW').exists())
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_positive_full_tensor_marker_last_and_negative_independent_controls(self):
        good=encode_candidate(decode_candidate(strassen_candidate(2),2),2)
        independent=_check_all_basis_outputs(2,[(tuple(t['u']),tuple(t['v']),tuple(t['w'])) for t in good['terms']])
        self.assertEqual(independent['output_bits_checked'],64);self.assertEqual(independent['mismatch_count'],0)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[];original=pilot.safe.base.freeze
            def record(path,raw,*args,**kwargs):calls.append(Path(path).name);return original(path,raw,*args,**kwargs)
            with mock.patch.object(pilot.safe.base,'freeze',side_effect=record):self.assertTrue(pilot.safe.freeze_winner(root,good,'control',b'n2',lambda:False,n=2,target=7))
            self.assertEqual(calls[-1],'WINNER.json');self.assertEqual(json.loads((root/'WINNER.verification.json').read_text())['exact_entries_checked'],64)
        for first_passes in [False,True]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);bad=encode_candidate([(1,1,1)],5)
                manager=mock.patch.object(pilot.safe.base,'verify_candidate',return_value={'valid':True,'exact_entries_checked':15625}) if first_passes else contextlib.nullcontext()
                with manager,self.assertRaises(ValueError):pilot.safe.freeze_winner(root,bad,'bad',b'bad',lambda:False)
                self.assertFalse((root/'WINNER.json').exists())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.assertFalse(pilot.safe.freeze_winner(root,good,'control',b'n2',lambda:True,n=2,target=7));self.assertFalse((root/'WINNER.json').exists())

if __name__=='__main__':unittest.main()
