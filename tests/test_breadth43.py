import ast
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

from mmsearch.breadth43 import (binary_rank,difference_rank,factor_histogram,histogram_distance,
    map_source,matrix_rank,select_farthest)
from mmsearch.free_factor_sat import build_system
from mmsearch.recombine import canonical_terms,digest
from mmsearch.tensor import naive_candidate
from scripts.campaign_breadth43 import SOURCE_FILES,run_child,stage_outcome
from scripts.campaign_observed_plane42 import resume_terminal


class Breadth43Tests(unittest.TestCase):
    def test_exact_rank_and_joint_factor_rank_histogram(self):
        self.assertEqual(binary_rank([1,2,3,8]),3)
        self.assertEqual(difference_rank([1,2,4],[1,2,4]),0)
        self.assertEqual(difference_rank([1,2,4],[0,0,0]),3)
        self.assertEqual(difference_rank([1,2,4],[8,16,32]),3)
        self.assertEqual(matrix_rank(9,2),2);self.assertEqual(matrix_rank(15,2),1)
        histogram=factor_histogram([(9,15,1),(1,1,1)],2)
        self.assertEqual(histogram,{'1/1/1':1,'2/1/1':1})
        self.assertEqual(histogram_distance(histogram,{'1/1/1':2}),2)

    def test_greedy_uses_rank_first_and_histogram_second(self):
        reference=dict(vectors=[0,0,0],factor_rank_histogram={'a':3},term_hash='r',model_sha256='r')
        a=dict(vectors=[1,2,4],factor_rank_histogram={'a':3},term_hash='a',model_sha256='a')
        b=dict(vectors=[1,2,3],factor_rank_histogram={'b':3},term_hash='b',model_sha256='b')
        c=dict(vectors=[8,16,32],factor_rank_histogram={'b':3},term_hash='c',model_sha256='c')
        chosen,trace=select_farthest([a,b],[reference],1)
        self.assertEqual(chosen[0]['term_hash'],'a');self.assertEqual(trace[0]['minimum_difference_rank'],3)
        chosen,trace=select_farthest([a,c],[reference],2)
        self.assertEqual([v['term_hash'] for v in chosen],['c','a'])
        self.assertEqual(trace[0]['minimum_histogram_l1'],6)

    def test_heldout_and_duplicate_exclusions_and_family_skip_are_not_negatives(self):
        candidate=naive_candidate(2);terms=canonical_terms(candidate)
        system=build_system(terms,2,'wu',candidate);term_hash=digest(terms)
        self.assertEqual(map_source(system,candidate,{term_hash})['status'],'EXCLUDED_V43_HELDOUT')
        self.assertEqual(map_source(system,candidate,(),{term_hash})['status'],'EXCLUDED_ALREADY_TESTED_MODEL')
        model_hash=digest(system['baseline_vectors'])
        self.assertEqual(map_source(system,candidate,(),(),{model_hash})['status'],'EXCLUDED_ALREADY_TESTED_MODEL')
        reduced=build_system(terms[:-1],2,'wu')
        reduced['baseline_vectors']=[0]*len(reduced['pairs'])
        skipped=map_source(reduced,candidate)
        self.assertEqual(skipped['status'],'SKIPPED_NOT_IN_FAMILY')
        self.assertTrue(skipped['missing_fixed_pairs'])

    def test_timeout_cleans_child_group_and_reaps_descendants(self):
        source='import os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\np=os.fork()\nif p==0:\n time.sleep(20)\n os._exit(0)\ntime.sleep(20)\n'
        with tempfile.TemporaryDirectory() as directory:
            result=run_child([sys.executable,'-c',source],.2,Path(directory)/'child.log')
        self.assertEqual(result['reason'],'wall limit or parent stop');self.assertTrue(result['child_reaped'])
        self.assertEqual(result['exit_code'],-signal.SIGKILL)
        if result['subreaper_enabled']:
            self.assertGreaterEqual(result['adopted_descendants_reaped'],1)
            with self.assertRaises(ProcessLookupError):os.killpg(result['child_pid'],0)

    def test_terminal_resume_guards_and_source_closure(self):
        child=dict(reason='completed',exit_code=0)
        self.assertEqual(stage_outcome(child,dict(status='SAT'),None),'ERROR')
        self.assertEqual(stage_outcome(child,dict(status='NO_WEIGHT_LE4_FOR_ENUMERATED_DELTAS'),None),
            'NO_WEIGHT_LE4_FOR_ENUMERATED_DELTAS')
        self.assertEqual(stage_outcome(dict(reason='stop',exit_code=-9),None,None),'UNKNOWN')
        self.assertEqual(stage_outcome(dict(reason='stop',exit_code=-9),None,dict(valid=True)),'SAT')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertEqual(resume_terminal(root,dict(last_status='ERROR')),'ERROR')
            (root/'WINNER.json').write_text('{}')
            with patch('scripts.campaign_observed_plane42.verify_candidate',return_value=dict(valid=True,rank=92,exact_entries_checked=15625)):
                self.assertEqual(resume_terminal(root,dict(last_status='SAT')),'SAT')
        root=Path(__file__).resolve().parents[1]
        for relative in SOURCE_FILES+['scripts/prepare_breadth43.py']:
            parts=list(Path(relative).with_suffix('').parts)
            for node in ast.walk(ast.parse((root/relative).read_text())):
                if not isinstance(node,ast.ImportFrom):continue
                module=(parts[:-node.level] if node.level else [])+(node.module.split('.') if node.module else [])
                if module and module[0] in ['mmsearch','scripts']:
                    self.assertIn('/'.join(module)+'.py',SOURCE_FILES)


if __name__=='__main__':unittest.main()
