"""Prepare 16 bounded weight-four hyperplanes; solve only small n2 controls."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'.xor-deps'))
from mmsearch import hyperplane_rankone42 as hp
from mmsearch.search import encode_candidate,naive_terms
from scripts.campaign_hyperplane_rankone42 import run_family
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json


def cpu():
    return sum(r.ru_utime+r.ru_stime for r in
               [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def closure(initial):
    pending=list(initial);found=set()
    while pending:
        name=pending.pop()
        if name in found:continue
        path=ROOT/name
        if not path.is_file():continue
        found.add(name);package=name.replace('/','.').removesuffix('.py').split('.')[:-1]
        for node in ast.walk(ast.parse(path.read_text())):
            modules=[]
            if isinstance(node,ast.Import):modules=[alias.name for alias in node.names]
            elif isinstance(node,ast.ImportFrom):
                base=package[:len(package)-node.level+1] if node.level else []
                if node.module:base+=node.module.split('.')
                modules=['.'.join(base),*['.'.join([*base,alias.name])for alias in node.names]]
            for module in modules:
                if not module.startswith(('mmsearch','scripts')):continue
                candidate=module.replace('.','/')+'.py'
                if (ROOT/candidate).is_file():pending.append(candidate)
                for top in ['mmsearch/__init__.py','scripts/__init__.py']:
                    if (ROOT/top).is_file():pending.append(top)
    return sorted(found)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,action='append',required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--cases',type=int,default=16)
    p.add_argument('--job-id',default='hyperplane-rankone42-pilot2')
    p.add_argument('--cpu',type=int,choices=range(4),default=1)
    p.add_argument('--formula-reference',type=Path)
    a=p.parse_args()
    if not 8<=a.cases<=16:p.error('prepare8..16 cases')
    started=time.monotonic();start_cpu=cpu();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    data=[];source_manifest=[];rejected=[]
    for source in a.source:
        raw=source.read_bytes();candidate=read_json(raw);sha=hashlib.sha256(raw).hexdigest()
        snapshot=out/'sources'/(sha+'.json');freeze(snapshot,raw)
        source_manifest.append(dict(original_path=str(source.resolve()),snapshot=str(snapshot),sha256=sha))
        for axis in range(3):
            try:
                prepared=hp.prepare_source(candidate,axis)
                if prepared['dimension']!=5 or prepared['R']!=93:raise ValueError('production source must be5x5 rank93')
                lambdas=hp.weight_four_lambdas(prepared,limit=32)
                data.append(dict(source_path=str(snapshot),source_sha256=sha,prepared=prepared,lambdas=lambdas,axis=axis))
            except ValueError as exc:rejected.append(dict(source_sha256=sha,axis=axis,reason=str(exc)))
    physical=set();specs=[];first_metadata=[]
    for round_index in range(32):
        for item in data:
            if round_index>=len(item['lambdas']):continue
            lam=item['lambdas'][round_index];family=hp.build_family(item['prepared'],lam)
            if family['physical_H_sha256']in physical:continue
            physical.add(family['physical_H_sha256']);index=len(specs);support=list(hp.bits(lam))
            spec=dict(source_path=item['source_path'],source_sha256=item['source_sha256'],free_axis=item['axis'],
                      lambda_mask=lam,lambda_support=support,lambda_weight=4,
                      selected_W_values=[item['prepared']['W_rows'][i]for i in support],selected_W_rank=3,
                      physical_H_sha256=family['physical_H_sha256'],max_new_points=3)
            freeze(out/f'cases/case-{index:02d}.json',json_bytes(spec));specs.append(spec)
            problem=hp.build_oracle(family);freeze(out/f'prepared/case-{index:02d}.first_problem.json',json_bytes(problem))
            first_metadata.append(problem['metadata'])
            if len(specs)>=a.cases:break
        if len(specs)>=a.cases:break
    if len(specs)<8:raise RuntimeError('insufficient distinct admissible weight-four hyperplanes')
    freeze(out/'sources_manifest.json',json_bytes(source_manifest))
    freeze(out/'case_audit.json',json_bytes(dict(cases=specs,initial_formula_metadata=first_metadata,rejected=rejected,
           distinct_physical_H=len(physical),production_oracle_queries=0)))
    if a.formula_reference:
        previous=read_json((a.formula_reference/'case_audit.json').read_bytes())
        before={case['physical_H_sha256']:metadata['formula_sha256']for case,metadata in zip(previous['cases'],previous['initial_formula_metadata'])}
        after={case['physical_H_sha256']:metadata['formula_sha256']for case,metadata in zip(specs,first_metadata)}
        if before!=after:raise AssertionError('seed repair changed production formulas')
        freeze(out/'formula_equivalence.json',json_bytes(dict(reference=str(a.formula_reference.resolve()),
               identical_physical_hyperplanes=len(after),identical_formula_hashes=True,formula_changes=False)))
    names=closure(['scripts/campaign_hyperplane_rankone42.py','mmsearch/hyperplane_rankone42.py',
                   'scripts/freeze_campaign_dictionary.py'])
    code={}
    for name in names:
        raw=(ROOT/name).read_bytes();code[name]=hashlib.sha256(raw).hexdigest();freeze(out/'runtime'/name,raw)
    dependencies={}
    depfiles=[*list((ROOT/'.xor-deps').glob('pycryptosat*.so')),
              *list((ROOT/'.xor-deps/pycryptosat.libs').glob('*')),
              *list((ROOT/'.xor-deps/pycryptosat-5.17.0.dist-info').rglob('*'))]
    for path in depfiles:
        if not path.is_file():continue
        relative=path.relative_to(ROOT/'.xor-deps');raw=path.read_bytes();dependencies[str(relative)]=hashlib.sha256(raw).hexdigest()
        freeze(out/'runtime'/relative,raw)
    for name in ['scripts/prepare_hyperplane_rankone42.py','tests/test_hyperplane_rankone42.py']:
        freeze(out/'provenance'/name,(ROOT/name).read_bytes())
    # This invokes the frozen launch closure from outside the repository and
    # prepares every formula. It is explicitly forbidden to query n5 in prep.
    wrapper=out/'runtime/scripts/campaign_hyperplane_rankone42.py'
    command=['python3',str(wrapper),'--cases-dir',str(out/'cases'),'--output-dir',str(out/'frozen-prepare-control'),
             '--seconds','60','--prepare-only']
    result=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=20)
    freeze(out/'frozen-prepare-control.log',(result.stdout+result.stderr).encode())
    if result.returncode:raise RuntimeError('frozen formula-only launch failed')
    summary=read_json((out/'frozen-prepare-control/summary.json').read_bytes())
    if any(row['status']!='PREPARED_NO_QUERY'for row in summary['results']):raise AssertionError('unexpected production solve')
    # Small full-MM controls only. Certificates use CONTROL names so a broad
    # campaign collector cannot confuse their filenames with an n5 WINNER.
    positive=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]
    candidate=dict(field=2,dimension=2,terms=[encode_candidate([t],2)['terms'][0]for t in positive])
    family=hp.build_family(hp.prepare_source(candidate,2),7)
    with tempfile.TemporaryDirectory() as directory:
        state=run_family(family,directory,oracle_seconds=2,memory_mb=256,seed=429051)
        if state['status']!='WINNER' or len(state['points'])!=2:raise AssertionError('n2 positive failed')
        winner,verification=hp.decode_containment(family,state['points'])
        freeze(out/'controls/n2-positive.certificate.json',json_bytes(winner))
        freeze(out/'controls/n2-positive.verification.json',json_bytes(verification))
        freeze(out/'controls/n2-positive.checkpoint.json',(Path(directory)/'checkpoint.json').read_bytes())
    negative=hp.prepare_source(encode_candidate(naive_terms(2),2),2)
    lam=sum(1<<i for i,w in enumerate(negative['W_rows'])if w==1)
    with tempfile.TemporaryDirectory() as directory:
        state=run_family(hp.build_family(negative,lam),directory,oracle_seconds=2,memory_mb=256)
        if state['status']!='HYPERPLANE_SPAN_UNSAT':raise AssertionError('n2 negative failed')
        freeze(out/'controls/n2-negative.result.json',json_bytes(state))
    test=subprocess.run(['python3','-m','unittest','tests.test_hyperplane_rankone42'],cwd=ROOT,
                        env=None,capture_output=True,text=True,timeout=10)
    # The prepare process selected .xor-deps through sys.path; subprocesses use
    # their inherited PYTHONPATH, which is recorded by the launch invocation.
    freeze(out/'tests.log',(test.stdout+test.stderr).encode())
    if test.returncode:raise RuntimeError('hyperplane tests failed')
    job=dict(id=a.job_id,cpu=a.cpu,memory_mb=1536,seconds=1215,enabled=True,
             command=['python3',str(wrapper),'--cases-dir',str(out/'cases'),'--output-dir',str(out.parent/a.job_id),
                      '--seconds','1200','--oracle-seconds','20','--max-points','3','--memory-mb','1536',
                      '--conflicts','10000000','--seed','2026110342905'])
    freeze(out/'proposed_job.json',json_bytes(job))
    ready=dict(status='READY',production_oracle_queries=0,queue_modified=False,test_count=7,test_exit_code=0,
               cases=len(specs),lambda_weight=4,selected_W_rank=3,distinct_physical_H=len(physical),
               full_A_rank_required=93,hyperplane_dimension=92,initial_U_dimension=89,max_new_points_per_case=3,
               oracle_seconds=20,memory_mb=1536,proposed_seconds=1200,runtime_code_sha256=code,
               solver_dependencies_sha256=dependencies,python_version=sys.version,
               mandatory_positive=dict(dimension=2,source_rank=8,new_points=2,verified_rank=7,exact_entries=64),
               mandatory_negative='Schoolbook8 chosen two-equal-W hyperplane UNSAT; global Strassen7 still exists.',
               checkpoint_policy='Points, formulas, complete SAT assignments and results are retained; fresh solver each oracle. UNKNOWN preserves points; terminal WINNER/ERROR does not resubmit. No learned-clause serialization.',
               scope='UNSAT excludes only rank-one spanning in one physical H with fixed old active-pair span; never global rank92.',
               proposed_job=str(out/'proposed_job.json'),preparation_cpu_seconds=cpu()-start_cpu,
               preparation_wall_seconds=time.monotonic()-started,formula_changes=False,
               requested_seed=2026110342905,solver_seed_base=2026110342905%2147483647,
               solver_seed_policy='requested nonnegative integer modulo2147483647; both values recorded per oracle',
               cli_error_policy='Any case ERROR produces portfolio status ERROR and exit code2, even when other cases complete.')
    if ready['preparation_cpu_seconds']>30:raise RuntimeError('preparation exceeded30 CPU seconds')
    freeze(out/'READY.json',json_bytes(ready));freeze(out/'checksums.json',json_bytes({
        str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest()for f in out.rglob('*')if f.is_file()}))
    for f in out.rglob('*'):
        if f.is_file():f.chmod(0o555 if '.so'in f.name else 0o444)
    print(json.dumps({k:v for k,v in ready.items()if k not in ['runtime_code_sha256','solver_dependencies_sha256']},indent=2))


if __name__=='__main__':main()
