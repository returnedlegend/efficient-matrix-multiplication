import copy,unittest,sys
from mmsearch.cyclic_native_corpus7 import complete_orbits,choose_diverse,validate_train_node,validate_command,validate_outer,RUNS
class CyclicNativeSourceControls(unittest.TestCase):
    def test_complete_orbit_not_reflection_or_partial(self):
        terms=[(1,2,4),(2,4,1),(4,1,2)];self.assertEqual(complete_orbits(terms,2),frozenset({(1,2,4)}))
        for bad in [terms[:-1],terms+terms[:1]]:
            with self.assertRaises(ValueError):complete_orbits(bad,2)
        self.assertNotEqual(complete_orbits([(1,4,2),(4,2,1),(2,1,4)],2),complete_orbits(terms,2))
    def test_source_selection_mandatory_abovebest_strata(self):
        records=[]
        for i,(run,rank) in enumerate([(RUNS[0],93),(RUNS[1],93),(RUNS[2],93),(RUNS[0],95),(RUNS[0],97),(RUNS[0],100)]):records.append(dict(run=run,rank=rank,identity=f'{i:064x}',orbits=frozenset({(1,2,i+1)})))
        selected,report=choose_diverse(records,6);self.assertEqual(len(selected),6);self.assertEqual(set(report['by_rank']),{93,95,97,100});self.assertFalse(report['optimization_called'])
        with self.assertRaises(ValueError):choose_diverse(records[:-1],6)
    def test_original_train_root_rejects_heldout_and_parent_edges(self):
        identity=dict(term_set_sha256='terms',rl_source_sha256='rl');ev=dict(approval_owner='root',selector=['initial_pool',0],plan_sha256='plan');node=dict(node_type='native_initial_train',root_id='id',id='id',parent_ids=[],parent_files=[],root_approved_train=True,split='train',heldout_excluded=True,evaluation_excluded=True,identity=identity,sha256='raw',root_training_evidence=ev);entry=dict(id='id',sha256='raw',identity=identity);pool=dict(sha256='raw',term_hash='terms',rl_source_hash='rl');armed=dict(armed=True,owner='root',plan_sha256='plan');split=dict(v43_source_split=dict(train=['rl']))
        validate_train_node(node,entry,0,pool,armed,split,[])
        for change in [dict(parent_ids=['unknown']),dict(split='heldout'),dict(root_approved_train=False)]:
            bad=copy.deepcopy(node);bad.update(change)
            with self.assertRaises(ValueError):validate_train_node(bad,entry,0,pool,armed,split,[])
        with self.assertRaises(ValueError):validate_train_node(node,entry,0,pool,armed,split,['rl'])
    def test_command_binds_single_cyclic_flag_and_exact_profile(self):
        profile=dict(seed=123,plus_every=2000,plus_burst=1,reduction_dwell=0);pairs={'--input':'/tmp/input','--output':'/tmp/walk','--n':'5','--target':'92','--max-rank':'105','--seed':'123','--steps':'1000000000000','--seconds':'120','--checkpoint-seconds':'3','--archive-size':'16','--archive-every':'1000','--plus-every':'2000','--restart-every':'50000000','--plus-burst':'1','--reduction-dwell':'0'};argv=['/tmp/worker']+[x for kv in pairs.items() for x in kv]+['--cyclic'];validate_command(argv,profile,'/tmp/worker','/tmp/input','/tmp/walk')
        for bad in [argv[:-1],argv+['--cyclic'],argv[:-1]+['--dwell-hold-rank','1','--cyclic']]:
            with self.assertRaises(ValueError):validate_command(bad,profile,'/tmp/worker','/tmp/input','/tmp/walk')
    def test_outer_envelope_rejects_resource_or_driver_drift(self):
        p='/tmp/portfolio';run=RUNS[0];d='/tmp/'+run
        outer=dict(cpu=0,memory_mb=768,wall_seconds=150,exit_code=0,timed_out=False,interrupted=False,command=[sys.executable,'-B',p+'/code/scripts/campaign_native_portfolio7.py','--bundle',p,'--expected-manifest-sha256',__import__('mmsearch.cyclic_native_corpus7',fromlist=['PORTFOLIO_SHA']).PORTFOLIO_SHA,'--profile-id',run,'--output-dir',d])
        validate_outer(outer,run,p,d)
        for change in [dict(cpu=1),dict(memory_mb=1024),dict(wall_seconds=300),dict(timed_out=True),dict(command=outer['command']+['--other'])]:
            bad=copy.deepcopy(outer);bad.update(change)
            with self.assertRaises(ValueError):validate_outer(bad,run,p,d)

if __name__=='__main__':unittest.main()
