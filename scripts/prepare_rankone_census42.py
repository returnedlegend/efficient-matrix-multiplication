"""Freeze a bounded point-census prototype; query only tiny n2 controls."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'.xor-deps'))
from mmsearch import hyperplane_rankone42 as hp,rankone_census42 as rc,free_factor_sat as ff
from mmsearch.search import encode_candidate,naive_terms
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from scripts.verify_record42_independent import _check_all_basis_outputs


def cpu():
    return sum(r.ru_utime+r.ru_stime for r in
               [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def ordered(terms):return dict(field=2,dimension=2,terms=[encode_candidate([t],2)['terms'][0]for t in terms])


def brute(source):
    matrices={}
    for c in range(1,1<<source['R']):
        value=0
        for i,col in enumerate(source['A_columns']):
            if c>>i&1:value^=col
        if value in matrices:raise AssertionError('A is not injective')
        matrices[value]=c
    result=[]
    for a in range(1,16):
        for b in range(1,16):
            matrix=sum(int(bool(a>>i&1)and bool(b>>j&1))<<(i*4+j)for i in range(4)for j in range(4))
            if matrix in matrices:result.append(dict(a=a,b=b,c=matrices[matrix]))
    return result


def support_control(candidate,source,points,out,label):
    dictionary=[(p['a'],p['b'],0)for p in points]
    system=ff.build_system(dictionary,2,'uv',baseline=candidate)
    problem=ff.build_problem(system,rank=7,max_formula_mb=32)
    result=ff.solve(problem,seconds=2,memory_mb=512)
    freeze(out/(label+'.problem.json'),json_bytes(problem));freeze(out/(label+'.result.json'),json_bytes(result))
    if result['status']=='SAT':
        recovered=result['candidate'];proof=_check_all_basis_outputs(2,[[tuple(t[a])for a in ['u','v','w']]for t in recovered['terms']])
        if proof['mismatch_count']or result['verification']['rank']>7:raise AssertionError('support decoder full tensor failure')
        bypair={(p['a'],p['b']):p['c']for p in points}
        for bit,target in enumerate(source['W_columns']):
            observed=0
            for term in recovered['terms']:
                a,b,w=[sum(v<<i for i,v in enumerate(term[k]))for k in ['u','v','w']]
                if w>>bit&1:observed^=bypair[a,b]
            if observed!=target:raise AssertionError('support solution failed C*Y=W')
        freeze(out/(label+'.independent-control-verification.json'),json_bytes(proof))
    return result['status']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--v3-runtime',type=Path,required=True)
    p.add_argument('--fresh-sources',type=Path,required=True);a=p.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    started=time.monotonic();start_cpu=cpu();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    for path in a.v3_runtime.rglob('*'):
        if path.is_file()and '__pycache__'not in path.parts:freeze(out/'runtime'/path.relative_to(a.v3_runtime),path.read_bytes())
    for name in ['mmsearch/rankone_census42.py','scripts/prototype_rankone_census42.py']:
        freeze(out/'runtime'/name,(ROOT/name).read_bytes())
    for name in ['scripts/prepare_rankone_census42.py','tests/test_rankone_census42.py']:
        freeze(out/'provenance'/name,(ROOT/name).read_bytes())
    assessments=[];initial_metadata=None
    for index in range(4):
        raw=(a.fresh_sources/f'source-{index}.json').read_bytes();candidate=read_json(raw)
        freeze(out/f'sources/source-{index}.json',raw)
        for axis in range(3):
            source=hp.prepare_source(candidate,axis)
            if source['R']!=93:raise ValueError('rank93 source required')
            points,closure=rc.common_factor_closure(source,rc.initial_points(source),cap=4096,max_rounds=4)
            rc.validate_points(source,points)
            freeze(out/f'partial-points/source-{index}-axis-{axis}.json',json_bytes(dict(points=points,closure=closure,
                  source_identity=rc.source_identity(source),census_complete=False)))
            assessments.append(dict(source=index,free_axis=axis,A_rank=source['A_rank'],initial_points=93,**closure))
            if initial_metadata is None:
                initial=rc.build_oracle(source,rc.initial_points(source));initial_metadata=initial['metadata']
                freeze(out/'prepared-n5-initial-formula.json',json_bytes(initial))
    # Actual frozen CLI: start from the8 unit points, discover10 dependent
    # points, then prove there is no19th point in schoolbook S.
    schoolbook=ordered(naive_terms(2));schoolbook_source=hp.prepare_source(schoolbook,2)
    schoolbook_brute=brute(schoolbook_source)
    if len(schoolbook_brute)!=18:raise AssertionError('brute225 count is not18')
    freeze(out/'controls/schoolbook.source.json',json_bytes(schoolbook))
    freeze(out/'controls/schoolbook.brute225.points.json',json_bytes(schoolbook_brute))
    wrapper=out/'runtime/scripts/prototype_rankone_census42.py';control=out/'controls/schoolbook-native-cli'
    command=['python3','-B',str(wrapper),'--source',str(out/'controls/schoolbook.source.json'),
             '--output-dir',str(control),'--small-control','--cap','4096','--seconds','30','--oracle-seconds','2',
             '--seed','2026110343201']
    run=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=35)
    freeze(out/'controls/schoolbook-native-cli.log',(run.stdout+run.stderr).encode())
    if run.returncode:raise RuntimeError('frozen n2 census CLI failed')
    state=read_json((control/'checkpoint.json').read_bytes())
    if state['status']!='CENSUS_COMPLETE'or len(state['points'])!=18 or state['oracle_attempts']!=11:raise AssertionError('native census count/completeness failed')
    if {p['c']for p in state['points']}!={p['c']for p in schoolbook_brute}:raise AssertionError('native/brute point sets differ')
    # Native oracle once more with all18 blocks is independently visible.
    result=rc.solve_oracle(rc.build_oracle(schoolbook_source,state['points']),seconds=2,memory_mb=512,
                           options={'seed':'2026110343201'})
    if result['status']!='CENSUS_COMPLETE_UNSAT':raise AssertionError('blocked-known18 oracle not UNSAT')
    freeze(out/'controls/block-all18.result.json',json_bytes(result))
    positive=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
    positive_candidate=ordered(positive);positive_source=hp.prepare_source(positive_candidate,2)
    points,closure=rc.common_factor_closure(positive_source,rc.initial_points(positive_source))
    full_positive=brute(positive_source)
    if len(points)!=10 or len(full_positive)!=11 or not closure['closure_saturated']:raise AssertionError('partial-closure boundary failed')
    missing=rc.solve_oracle(rc.build_oracle(positive_source,points),seconds=2,memory_mb=512)
    if missing['status']!='SAT'or missing['point']!=dict(a=2,b=4,c=188):raise AssertionError('census failed to go beyond saturated closure')
    full_points=[*points,missing['point']]
    completed_oracle=rc.solve_oracle(rc.build_oracle(positive_source,full_points),seconds=2,memory_mb=512)
    if completed_oracle['status']!='CENSUS_COMPLETE_UNSAT':raise AssertionError('positive11 census not complete')
    freeze(out/'controls/positive-beyond-closure.point.json',json_bytes(missing))
    freeze(out/'controls/positive-complete11.result.json',json_bytes(completed_oracle))
    controls=out/'controls/support';controls.mkdir()
    partial=support_control(positive_candidate,positive_source,rc.initial_points(positive_source),controls,'positive-partial8')
    expanded=support_control(positive_candidate,positive_source,points,controls,'positive-partial10')
    completed=support_control(positive_candidate,positive_source,full_points,controls,'positive-complete11')
    negative=support_control(schoolbook,schoolbook_source,state['points'],controls,'schoolbook-complete18')
    if (partial,expanded,completed,negative)!=('UNSAT','SAT','SAT','UNSAT'):raise AssertionError('support-relative control boundary failed')
    test=subprocess.run(['python3','-m','unittest','tests.test_rankone_census42'],cwd=ROOT,capture_output=True,text=True,timeout=15)
    freeze(out/'tests.log',(test.stdout+test.stderr).encode())
    if test.returncode:raise RuntimeError('census prototype tests failed')
    freeze(out/'ASSESSMENT.json',json_bytes(dict(initial_n5_model=initial_metadata,
        cap4096_model=dict(variables=768,AND_gates=625,CNF_clauses=5973,native_XOR_equations=625,coefficient_block_literals=4096*93),
        common_factor_lower_bounds=assessments,full_point_upper_bound=min((1<<93)-1,((1<<25)-1)**2),
        coefficient_support_equivalence='A is injective: A*C*Y=A*W iff C*Y=W. Every SAT support witness still requires a full tensor verifier; partial-dictionary UNSAT is only dictionary-relative.',
        complete_census_scope='Only every nonzero rank-one point in the fixed old active-pair span S, not all algorithms or global rank.',
        optional_closure_scope='Verified lower bounds103..108 in the12fresh n5 models; closure saturation never asserts full census.',
        production_queries=0,production_support_queries=0,n5_solver_dispatch_enabled=False)))
    ready=dict(status='PROTOTYPE_READY_UNLAUNCHED',production_queries=0,n5_support_queries=0,n5_solver_dispatch_enabled=False,
        point_cap=4096,prep_AS_limit_MiB=512,test_count=5,test_exit_code=0,initial_n5_model=initial_metadata,
        common_factor_point_counts=[row['known_points']for row in assessments],
        mandatory_n2_control=dict(brute_a_b_pairs=225,source_rank=8,exact_points=18,new_native_points=10,
              native_oracle_calls=11,all18_blocked_oracle='UNSAT',full_census_scope='schoolbook active-pair span S only'),
        support_controls=dict(positive_partial8='UNSAT dictionary-relative',positive_partial10='SAT verified7/all64',
                              positive_complete11='SAT verified7/all64',
                              schoolbook_complete18='UNSAT old-span-relative; global Strassen7 remains valid'),
        closure_incompleteness_control=dict(saturated_closure_points=10,full_brute_points=11,
                         additional_census_point=dict(a=2,b=4,c=188)),
        production_formulas_prepared=1,active_v3_files_changed=False,queue_modified=False,
        preparation_CPU_seconds=cpu()-start_cpu,preparation_wall_seconds=time.monotonic()-started,
        parent_peak_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,children_peak_RSS_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        scope='Finite census and dictionary support questions inside chosen S only. Caps/UNKNOWN/closure saturation are not completeness or global lower bounds.')
    if ready['preparation_CPU_seconds']>60:raise RuntimeError('prototype prep exceeded60 CPU seconds')
    freeze(out/'READY.json',json_bytes(ready));freeze(out/'manifest.json',json_bytes(dict(files={
        str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()for p in out.rglob('*')if p.is_file()and '__pycache__'not in p.parts})))
    for p in out.rglob('*'):
        if p.is_file():p.chmod(0o555 if '.so'in p.name else 0o444)
    print(json.dumps(ready,indent=2))


if __name__=='__main__':main()
