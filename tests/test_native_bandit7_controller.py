"""No-query controls for terminal handling and the fixed eight-epoch queue cap."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from scripts import native_bandit7_controller as controller
from scripts import campaign_native_bandit7 as b
from tests.test_campaign_native_bandit7 import state

class ControllerControls(unittest.TestCase):
    def test_eight_epoch_checkpoint_never_appends_ninth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=state();s['completed_epochs']=8;s['counts'][3]=8;s['contexts']['noncyclic_source']['counts'][3]=8;s['used_seeds']=list(range(8))
            path=root/'checkpoint.json';path.write_bytes(b.encoded(s))
            with mock.patch.object(b,'load_bundle',return_value={'campaign':str(root),'baseline_sha256':'b'}),mock.patch.object(controller,'append_jobs',side_effect=AssertionError('ninth forbidden')):
                result=controller.run(root,'m',path,b.sha(path.read_bytes()),root/'control')
            self.assertEqual(result['status'],'COMPLETE_EIGHT_EPOCHS')

    def test_unknown_terminal_and_wrong_queued_binding_stop_without_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bundle=root/'bundle';s=state();s['completed_epochs']=7;s['counts'][3]=7;s['contexts']['noncyclic_source']['counts'][3]=7;s['used_seeds']=list(range(7))
            checkpoint=root/'parent.json';checkpoint.write_bytes(b.encoded(s));pin=b.sha(checkpoint.read_bytes())
            sources={'0':{'cyclic_complete':True},'1':{'cyclic_complete':False}};choice=b.choose(s,sources);name=choice['profile']['id'];directory=root/name;directory.mkdir()
            job=dict(id=name,cpu=2,memory_mb=768,seconds=210,enabled=True,command=[controller.sys.executable,'-B',str(bundle/'code/scripts/campaign_native_bandit7.py'),'--bundle',str(bundle),'--manifest-sha256','m','--checkpoint',str(checkpoint),'--checkpoint-sha256',pin,'--output-dir',str(directory),'--execute'])
            (root/'queue.json').write_bytes(b.encoded({'jobs':[job]}));(root/'queue_state.json').write_bytes(b.encoded({'jobs':{name:{'status':'completed','spec':job}}}))
            (directory/'outcome.json').write_bytes(b.encoded({'status':'STOPPED_ERROR_OR_UNKNOWN'}))
            manifest=dict(campaign=str(root),baseline_sha256='b',sources=sources)
            guard=SimpleNamespace(hard=dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1))
            with mock.patch.object(b,'load_bundle',return_value=manifest),mock.patch.object(controller,'global_check',return_value=guard),mock.patch.object(controller,'append_jobs',side_effect=AssertionError('unknown must not append')):
                with self.assertRaisesRegex(ValueError,'UNKNOWN'):controller.run(bundle,'m',checkpoint,pin,root/'control')
                job['command'].append('--unexpected');(root/'queue.json').write_bytes(b.encoded({'jobs':[job]}))
                with self.assertRaisesRegex(ValueError,'existing job'):controller.run(bundle,'m',checkpoint,pin,root/'control')

if __name__=='__main__':unittest.main()
