import copy
import itertools
import signal
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mmsearch.common_delta42 import multiply
from mmsearch.free_factor_sat import build_system
from mmsearch.observed_plane42 import (active_certificate,decode_plane_hit,decode_weight3,lift_plane,
    plane_plan,prepare_plane,search_plane_bounded,validate_active_certificate,validate_plane)
from mmsearch.recombine import canonical_terms,digest,encode
from mmsearch.tensor import strassen_candidate
from scripts.campaign_observed_plane42 import SOURCE_FILES,resume_terminal


def split_system():
    candidate=strassen_candidate(2);terms=canonical_terms(candidate)
    for t,(u,v,w) in enumerate(terms):
        for a in range(1,16):
            b=u^a
            if b:
                split=list(terms[:t])+list(terms[t+1:])+[(a,v,w),(b,v,w)]
                if len({(z,x) for x,y,z in split})==8:
                    return build_system(sorted(set(split)|set(terms)),2,'wu',encode(split,2)),v
    raise AssertionError('no split control')


class ObservedPlaneTests(unittest.TestCase):
    def test_resume_stops_at_verified_winner_or_prior_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertIsNone(resume_terminal(root,dict(last_status='UNKNOWN')))
            self.assertEqual(resume_terminal(root,dict(last_status='ERROR')),'ERROR')
            (root/'WINNER.json').write_text('{}')
            with patch('scripts.campaign_observed_plane42.verify_candidate',return_value=dict(
                    valid=True,rank=92,exact_entries_checked=15625)):
                self.assertEqual(resume_terminal(root,dict(last_status='SAT')),'SAT')
            with patch('scripts.campaign_observed_plane42.verify_candidate',return_value=dict(
                    valid=False,rank=92,exact_entries_checked=15625)):
                with self.assertRaises(AssertionError):resume_terminal(root,dict(last_status='SAT'))

    def test_frozen_source_import_closure(self):
        root=Path(__file__).resolve().parents[1]
        for relative in SOURCE_FILES:
            parts=list(Path(relative).with_suffix('').parts)
            for node in ast.walk(ast.parse((root/relative).read_text())):
                if not isinstance(node,ast.ImportFrom):continue
                module=(parts[:-node.level] if node.level else [])+(node.module.split('.') if node.module else [])
                if module and module[0] in ['mmsearch','scripts']:
                    self.assertIn('/'.join(module)+'.py',SOURCE_FILES)

    def test_exhaustive_decoder_matches_independent_four_power_assignments(self):
        families=list(itertools.chain.from_iterable(itertools.combinations_with_replacement(range(8),n) for n in range(4)))
        families.extend([(1,2,4,8),(1,4,6),(4,4,5),(4,8,13)])
        for columns in families:
            best={}
            for values in itertools.product(range(4),repeat=len(columns)):
                a=b=0
                for h,v in zip(columns,values):
                    if v&1:a^=h
                    if v&2:b^=h
                key=(a,b);weight=sum(bool(v) for v in values)
                best[key]=min(best.get(key,len(columns)+1),weight)
            width=max(3,max(columns,default=0).bit_length())
            for targets in itertools.product(range(1<<width),repeat=2):
                for bound in [1,2,3]:
                    result=decode_weight3(columns,targets,bound,seconds=1)
                    self.assertEqual(result['status']=='HIT',best.get(targets,99)<=bound,(columns,targets,bound,result))

    def test_essential_mixed_case_and_bounded_negative_scope(self):
        result=decode_weight3([1,4,6],[1,2],3)
        self.assertEqual(result['case'],'target_plane_point_plus_parallel_pair')
        self.assertEqual(result['entries'],[[0,1],[1,2],[2,2]])
        for columns in [[0,4,6],[2,4,6],[4,4,5],[4,8,13]]:
            self.assertEqual(decode_weight3(columns,[1,2],3)['status'],'NO_WEIGHT_LE3')
        q=dict(column_syndromes_hex=list(map(hex,[1,2,4,8])),targets_hex=['0x3','0xc'],
            weight_bound=4,quotient_sha256='synthetic',scope='bounded synthetic test')
        result=search_plane_bounded(q,seconds=1,memory_mb=256)
        self.assertEqual(result['status'],'NO_WEIGHT_LE3')
        self.assertFalse(result['complete_for_requested_gain'])
        self.assertEqual(result['worker_stats']['address_space_limit_bytes'],256*1024**2)

    def test_full_split_strassen_repair_and_baseline_control(self):
        system,delta=split_system()
        other=next(v for v in system['baseline_vectors'] if v and v!=delta)
        q=prepare_plane(system,sorted([delta,other,delta^other]))
        baseline=[[i,value] for i,value in enumerate(q['old_coordinates']) if value]
        lift=lift_plane(system,q,baseline,require_gain=False)
        self.assertEqual(lift['coordinate_kernel_masks_hex'],['0x0','0x0'])
        result=search_plane_bounded(q,seconds=1,memory_mb=256)
        self.assertEqual(result['status'],'HIT')
        answer=decode_plane_hit(system,q,result['entries'])
        self.assertLessEqual(answer['verification']['rank'],7)
        self.assertEqual(answer['verification']['exact_entries_checked'],64)

    def test_all_tiny_y_assignments_and_neutral_lifts(self):
        columns=[1,2,3,3,4];old=[1,2,4,5,0]
        rows=[sum(1<<g for g,c in enumerate(columns) if c>>r&1) for r in range(3)]
        rhs=[]
        for row in rows:
            value=0
            for g,w in enumerate(old):
                if row>>g&1:value^=w
            rhs.append(value)
        system=dict(coefficients=rows,right_sides=rhs,baseline_vectors=old,metadata=dict(width=3),pairs=[(1,1)]*len(old))
        q=prepare_plane(system,[1,2,3])
        for values in itertools.product(range(4),repeat=len(q['relevant_groups'])):
            entries=[[i,v] for i,v in enumerate(values) if v]
            observed=[]
            for bit in range(2):
                value=0
                for i,v in entries:
                    if v>>bit&1:value^=int(q['column_syndromes_hex'][i],16)
                observed.append(value)
            holds=observed==[int(t,16) for t in q['targets_hex']]
            exists=False
            for neutral in itertools.product(range(4),repeat=len(q['neutral_groups'])):
                updates=[0]*len(old)
                for i,g in enumerate(q['relevant_groups']):updates[g]=values[i]^old[g]
                for g,v in zip(q['neutral_groups'],neutral):updates[g]=v
                if all(not multiply(columns,sum(((v>>bit)&1)<<g for g,v in enumerate(updates))) for bit in range(2)):
                    exists=True;break
            self.assertEqual(holds,exists)
            if holds:lift_plane(system,q,entries,require_gain=False)
        bad=copy.deepcopy(q);bad['target_neutral_lifts_hex'][0]=hex(int(bad['target_neutral_lifts_hex'][0],16)^1)
        bad['quotient_sha256']=digest({k:v for k,v in bad.items() if k!='quotient_sha256'})
        with self.assertRaises(AssertionError):validate_plane(system,bad)

    def test_plane_deduplication_and_active_rank_certificate(self):
        system,delta=split_system();certificate=active_certificate(system)
        self.assertTrue(validate_active_certificate(system,certificate))
        plans=plane_plan(system)
        self.assertEqual(len(plans),len({tuple(p['plane']) for p in plans}))
        for item in plans:
            self.assertEqual(item['plane'][0]^item['plane'][1],item['plane'][2])
        bad=copy.deepcopy(certificate);bad['basis'][0][2]='0x0'
        with self.assertRaises(AssertionError):validate_active_certificate(system,bad)

    def test_hard_timeout_and_inherited_handler_cleanup(self):
        system,delta=split_system();other=next(v for v in system['baseline_vectors'] if v and v!=delta)
        q=prepare_plane(system,[delta,other,delta^other])
        def stall(*args):
            self.assertEqual(signal.getsignal(signal.SIGTERM),signal.SIG_DFL);time.sleep(10)
        previous=signal.signal(signal.SIGTERM,lambda *_:None)
        try:
            with patch('mmsearch.observed_plane42._worker',stall):result=search_plane_bounded(q,seconds=.02,memory_mb=256)
            self.assertEqual(result['status'],'UNKNOWN');self.assertTrue(result['worker_reaped'])
            self.assertLess(result['elapsed_seconds'],.5)
        finally:signal.signal(signal.SIGTERM,previous)


if __name__=='__main__':unittest.main()
import ast
