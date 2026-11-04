import contextlib
import copy
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_conditional_c3_packets7 as subject
from scripts.run_c3_mixed12_pilot7 import run_case
from mmsearch.binary_block_descent7 import scalar_loss


def fixture():
    bvals=[4,5,7,7,4,0,4,0,0];counts=[18,12,15,15,22,40,22,40,40]
    base=dict(core_pins_complete=True,selected_cases_sha256='ninepin',input_sha256={},cases=[]);metadata=[]
    for i,(b,count) in enumerate(zip(bvals,counts)):
        row=dict(id=str(i),branch_metadata=dict(actual_core_sha256='core'+str(i),core_input_sha256='input'+str(i),ambient_sha256='ambient'+str(i)))
        base['cases'].append(row)
        metadata.append(dict(case=str(i),ordinal=i,shape=[11]*3,image_rank=11,axis=0,
            native_core_sha256='core'+str(i),input_core_sha256='input'+str(i),ambient_sha256='ambient'+str(i),
            backbone_rank=b,distinct_child_count=count,distinct_child_cosets=[dict(coset_hex=hex(j+1)) for j in range(count)],
            conditional_forced_pair_complete=b<=6))
    manifest=dict(input_core_manifest_sha256='f0487990ecff816bf6f3b51605071f22e35b32c9cc5d0cdfa8b8378daeffb571',
        source_sha256=subject.SOURCE_SHA,decoder_calls=0)
    return base,manifest,metadata


class ConditionalC3RunnerTests(unittest.TestCase):
    def test_exact_seven_qualification_and_no_b7_closure(self):
        base,manifest,metadata=fixture();plan=subject.restrict_plan(base,manifest,metadata,{'metadata':'pin'})
        self.assertEqual([r['id'] for r in plan['cases']],['0','1','4','5','6','7','8'])
        self.assertEqual(plan['excluded_b7_cases'],['2','3'])
        self.assertEqual(sum(r['conditional_metadata']['distinct_child_count'] for r in plan['cases']),194)
        self.assertEqual(plan['limits']['parent_cosets'],40)
        self.assertIs(subject.guarded_run_case,run_case)

    def test_strict_metadata_provenance_and_classification_fail_closed(self):
        for mutation in ('core','input','floatshape','boolrank','oversized','wrongbound','missingcoset','reordered'):
            base,manifest,metadata=fixture()
            if mutation=='core':metadata[0]['native_core_sha256']='forged'
            elif mutation=='input':metadata[0]['input_core_sha256']='forged'
            elif mutation=='floatshape':metadata[0]['shape']=[11.0]*3
            elif mutation=='boolrank':metadata[0]['backbone_rank']=True
            elif mutation=='oversized':metadata[0]['distinct_child_count']=41
            elif mutation=='wrongbound':metadata[0]['conditional_forced_pair_complete']=False
            elif mutation=='missingcoset':metadata[0]['distinct_child_cosets'].pop()
            else:metadata[0],metadata[1]=metadata[1],metadata[0]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):subject.restrict_plan(base,manifest,metadata,{})

    def test_actual_diagonal_positive_has_full_integer_loss_zero(self):
        core=[int(i in (0,13,26)) for i in range(27)]
        solve=subject.conditional_bridge(SimpleNamespace(),allow_tiny=True)
        result=solve(core,[3]*3,3)
        self.assertEqual(result['status'],'SAT')
        self.assertEqual(scalar_loss(core,[3]*3,result['products']),0)
        forged=dict(status='SAT',complete=True,products=[[0,0,0]]*3)
        with patch.object(subject.decoder,'solve_core',return_value=forged),self.assertRaises(ValueError):solve(core,[3]*3,3)

    def test_parent_negative_requires_prior_and_every_bound_child(self):
        meta=dict(backbone_rank=4,distinct_child_count=2,distinct_child_cosets=[dict(coset_hex='0x1'),dict(coset_hex='0x2')])
        cache=SimpleNamespace(current_metadata=meta);solve=subject.conditional_bridge(cache)
        negative=dict(status='LOCAL_UNSAT',complete=True,case='all_conditional_repeated_pair_extensions_negative',
            target_rank=11,inside_rank=4,conditional_pair_theorem_applies=True,budget=14,total_extensions=2,
            extension_cursor=2,extension_cosets=[1,2],prior_result_sha256='priorpin',
            tested_extensions=[dict(coset=i,status='LOCAL_UNSAT',child_result_sha256='childpin') for i in (1,2)])
        with patch.object(subject.decoder,'solve_core',return_value=negative) as decoder:
            self.assertEqual(solve([0]*1331,[11]*3,14)['status'],'LOCAL_UNSAT')
        kwargs=decoder.call_args.kwargs
        self.assertEqual(kwargs['max_extensions'],40);self.assertEqual(kwargs['max_child_vectors'],8191)
        self.assertEqual(kwargs['timeout_seconds'],30)
        for key,value in (('prior_result_sha256',None),('extension_cursor',1),('extension_cosets',[1]),('tested_extensions',negative['tested_extensions'][:1])):
            changed=copy.deepcopy(negative);changed[key]=value
            with self.subTest(key=key),patch.object(subject.decoder,'solve_core',return_value=changed),self.assertRaises(ValueError):
                solve([0]*1331,[11]*3,14)
        unknown=dict(status='UNKNOWN',complete=False,last_child_result=dict(status='SAT',support=['raw']))
        with patch.object(subject.decoder,'solve_core',return_value=unknown):
            self.assertIs(solve([0]*1331,[11]*3,14),unknown)

    def test_scope_and_disabled_cli(self):
        solve=subject.conditional_bridge(SimpleNamespace())
        for shape,target,axis in (([12]*3,14,0),([11]*3,13,0),([11]*3,14,1)):
            with self.assertRaises(ValueError):solve([],shape,target,axis=axis)
        with patch.object(subject,'select_plan',side_effect=AssertionError('disabled read')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main([]),0)


if __name__=='__main__':unittest.main()
