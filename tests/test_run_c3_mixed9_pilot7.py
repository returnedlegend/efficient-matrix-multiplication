import json
from pathlib import Path
import tempfile
import unittest
from mmsearch.search import naive_terms,encode_candidate
from mmsearch.extend_eight_bulk43 import SourceCache
from mmsearch.sat_neighborhoods import factor_masks
from mmsearch.local_guard43 import CampaignHold
from mmsearch.compact_rank2_edges43 import solve_core
from scripts.run_c3_mixed9_pilot7 import run_case

class Guard:
    def __init__(self):self.now=0.;self.monotonic=lambda:self.now;self.utc_clock=lambda:0.;self.deadline=1000.;self.started=0.;self.seconds=60;self.signal_stop=False
    def reason(self,force=False):return None
    def check(self,name):
        if self.signal_stop:raise CampaignHold('stop signal',name)

def planted(directory,k):
    terms=list(naive_terms(3));selected=[]
    for i in range(3):
        for j in range(3):
            z=(i+j)%3;selected.append((1<<(i*3+j),1<<(j*3+z),1<<(z*3+i)))
    old=selected[:k];inflated=[]
    for index,term in enumerate(old):
        if index<9-k:
            other=old[index+2][2];inflated.extend([(term[0],term[1],term[2]^other),(term[0],term[1],other)])
        else:inflated.append(term)
    outside=[term for term in terms if term not in old];source=encode_candidate(outside+inflated,3);path=directory/'source.json';path.write_text(json.dumps(source));case={'id':'tiny'+str(k),'source':'source.json','source_products':len(source['terms']),'source_local_products':9,'source_indices':sorted(factor_masks(source).index(term) for term in inflated),'target_local_products':8,'shape':[k]*3,'mode_rank':k,'free_axis':0}
    return case

class PilotControls(unittest.TestCase):
    def test_positive_full_n3_images7_and8_repair_globally27(self):
        for k in [7,8]:
            with self.subTest(k=k),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);case=planted(root,k);result=run_case(SourceCache(root),case,root/'out',Guard(),control_expected_rank=27)
                self.assertEqual(result['status'],'SMALL_CONTROL_PASSED');self.assertEqual(result['candidate_rank'],27)
                self.assertEqual(result['primary']['exact_entries_checked'],729);self.assertEqual(result['independent']['exact_entries_checked'],729)
                self.assertFalse((root/'out/WINNER.json').exists())

    def test_late_sat_retains_raw_hidden_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);case=planted(root,8);guard=Guard()
            def late(*args,**kwargs):
                result=solve_core(*args,**kwargs);guard.now=6;return result
            result=run_case(SourceCache(root),case,root/'out',guard,solver=late,control_expected_rank=27)
            self.assertEqual(result['status'],'UNKNOWN');self.assertFalse(result['complete']);self.assertTrue(result['decoder_called'])
            self.assertFalse((root/'out/records').exists());self.assertTrue(list((root/'out/.raw-returns').glob('*.raw')))

if __name__=='__main__':unittest.main()
