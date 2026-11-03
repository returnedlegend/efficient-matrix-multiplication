"""Freeze an unlaunched twelve-span census/support job; query n2 controls only."""
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mmsearch import hyperplane_rankone42 as hp,rankone_census42 as rc,old_span_support42 as support
from mmsearch.search import naive_terms
from scripts.prepare_rankone_census42 import ordered,brute
from scripts.prototype_rankone_census42 import checkpoint
from scripts.campaign_hyperplane_catalog42 import pid_ticks
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
from scripts.verify_record42_independent import verify_bytes


def sha(raw):return hashlib.sha256(raw).hexdigest()


def manifest(path):
    value=dict(format='old-span-census-support42-v1',files={str(p.relative_to(path)):sha(p.read_bytes())for p in path.rglob('*')
               if p.is_file()and p.name!='manifest.json'and '__pycache__'not in p.parts})
    freeze(path/'manifest.json',json_bytes(value))


def cpu():return sum(x.ru_utime+x.ru_stime for x in [resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--prototype',type=Path,required=True);a=p.parse_args();start=time.monotonic();cpu0=cpu()
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);camp=out.parent
    for path in(a.prototype/'runtime').rglob('*'):
        if path.is_file()and '__pycache__'not in path.parts:freeze(out/'runtime'/path.relative_to(a.prototype/'runtime'),path.read_bytes())
    for name in ['mmsearch/old_span_support42.py','scripts/campaign_old_span_census_support42.py',
                 'scripts/campaign_hyperplane_catalog42.py','scripts/verify_record42_independent.py']:
        freeze(out/'runtime'/name,(ROOT/name).read_bytes())
    for name in ['scripts/prepare_old_span_census_support42.py','tests/test_old_span_census_support42.py']:
        freeze(out/'provenance'/name,(ROOT/name).read_bytes())
    # Only the cardinality encoder is needed; native SAT uses the existing
    # frozen pycryptosat closure, never a network/package installation.
    import pysat,pycard
    pyroot=Path(pysat.__file__).parent
    for name in ['__init__.py','card.py','formula.py','_utils.py','_fileio.py']:
        freeze(out/'runtime/pysat'/name,(pyroot/name).read_bytes())
    freeze(out/'runtime'/Path(pycard.__file__).name,Path(pycard.__file__).read_bytes())
    distribution=importlib.metadata.distribution('python-sat')
    for file in distribution.files:
        if '.dist-info/'in str(file):freeze(out/'runtime'/str(file),Path(distribution.locate_file(file)).read_bytes())
    cases=[];assessments=[]
    for index in range(4):
        raw=(a.prototype/f'sources/source-{index}.json').read_bytes();candidate=read_json(raw)
        proof=verify_bytes(raw)
        if not proof['valid']or proof['canonical_essential_products']!=93:raise ValueError('not an exact rank93 source')
        rel=f'sources/source-{index}.json';freeze(out/rel,raw);freeze(out/f'source-verification/source-{index}.json',json_bytes(proof))
        for axis in range(3):
            source=hp.prepare_source(candidate,axis);points,closure=rc.common_factor_closure(source,rc.initial_points(source))
            if source['A_rank']!=93:raise ValueError('noninjective source A')
            initial=support.build_problem(candidate,source,points,92)
            spec=dict(id=f'source-{index}-axis-{axis}',source_file=rel,source_sha256=sha(raw),free_axis=axis,
                 source_identity=rc.source_identity(source),source_A_rank=93,initial_points=len(points),closure_rounds=4,
                 initial_point_catalog_sha256=hp.digest(points),initial_support_formula_sha256=initial['metadata']['formula_sha256'])
            freeze(out/f"cases/{spec['id']}.json",json_bytes(spec));cases.append(spec)
            freeze(out/f"initial-points/{spec['id']}.json",json_bytes(dict(points=points,closure=closure,source_identity=spec['source_identity'])))
            assessments.append(dict(id=spec['id'],metadata=initial['metadata'],census_model=rc.build_oracle(source,points)['metadata']))
    freeze(out/'catalog.json',json_bytes(dict(format='old-span-census-support42-v1',small_controls=False,target=92,cases=cases)))
    freeze(out/'MODEL_ASSESSMENT.json',json_bytes(assessments))
    # The actual production entrypoint from /tmp, with the same large proposed
    # seed and reviewed limits, gets tiny exact positive/negative controls.
    small=out/'controls/small-bundle';entries=[]
    positive=ordered([(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)])
    controls=[('schoolbook-complete18',ordered(naive_terms(2)),2,0,False),
              ('positive-complete11',positive,2,4,False),('positive-axis0',positive,0,4,False),
              ('positive-axis1',positive,1,4,False),('positive-partial8',positive,2,0,True),
              ('positive-partial10',positive,2,4,True)]
    controlout=out/'controls/actual-native-cli'
    for name,candidate,axis,rounds,skip in controls:
        raw=json_bytes(candidate);rel=f'sources/{name}.json';freeze(small/rel,raw);source=hp.prepare_source(candidate,axis)
        spec=dict(id=name,source_file=rel,source_sha256=sha(raw),free_axis=axis,source_identity=rc.source_identity(source),
                  closure_rounds=rounds,skip_census=skip);entries.append(spec)
        if skip:
            points=rc.initial_points(source)
            if rounds:points,_=rc.common_factor_closure(source,points)
            folder=controlout/'cases'/name/'census';folder.mkdir(parents=True)
            checkpoint(folder,source,dict(status='PARTIAL',points=points,oracle_attempts=0,history=[],census_complete=False))
        if name=='schoolbook-complete18':freeze(out/'controls/independent-brute225.points.json',json_bytes(brute(source)))
    freeze(small/'catalog.json',json_bytes(dict(small_controls=True,target=7,cases=entries)));manifest(small)
    guard=out/'controls/fresh-guard.json'
    def metric(working):guard.write_bytes(json_bytes(dict(updated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),pid=os.getpid(),
            process_identity=dict(start_ticks=pid_ticks(os.getpid())),campaign_allocated_bytes=working,
            rss_bytes=128*1024**2,filesystem_free_bytes=16*1024**3,stop_reason=None)))
    wrapper=out/'runtime/scripts/campaign_old_span_census_support42.py'
    command=['python3','-B',str(wrapper),'--bundle',str(small),'--output-dir',str(controlout),'--guard',str(guard),
          '--small-controls','--seconds','1800','--census-seconds','60','--support-seconds','60','--oracle-seconds','5',
          '--memory-mb','1536','--phase-mb','128','--seed','2026110343301']
    metric(int(4.25*1024**3));run=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=45)
    freeze(out/'controls/native-cli.log',(run.stdout+run.stderr).encode())
    if run.returncode:raise RuntimeError('frozen native control CLI failed')
    summary=read_json((controlout/'summary.json').read_bytes());rows={r['id']:r for r in summary['events']}
    if summary['coverage_counts']!={'OLD_S_ONLY_UNSAT':1,'CONTROL_PASSED':4,'PARTIAL_CATALOG_UNSAT':1}:raise AssertionError('incorrect scoped native controls')
    if not(rows['schoolbook-complete18']['known_points']==18 and rows['schoolbook-complete18']['census_complete']
           and rows['positive-complete11']['known_points']==11 and rows['positive-complete11']['census_complete']
           and rows['positive-partial10']['known_points']==10 and not rows['positive-partial10']['census_complete']):raise AssertionError('census cardinality/scope failure')
    state=read_json((controlout/'cases/schoolbook-complete18/census/checkpoint.json').read_bytes())
    if state['oracle_attempts']!=11:raise AssertionError('schoolbook did not actually enumerate10 new points')
    brute_points=read_json((out/'controls/independent-brute225.points.json').read_bytes())
    if {x['c']for x in state['points']}!={x['c']for x in brute_points}:raise AssertionError('native census differs from independent brute225')
    metric(int(4.25*1024**3));again=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=15)
    resumed=read_json((controlout/'summary.json').read_bytes())
    if again.returncode or resumed['phase_queries']:raise AssertionError('terminal/control resume resubmitted query')
    freeze(out/'controls/native-cli-resume.log',(again.stdout+again.stderr).encode())
    # A winner exported just before a coverage crash is independently rechecked
    # and terminal on the actual CLI, without any new native query.
    winnerout=out/'controls/terminal-winner-cli'
    for name in ['WINNER.json','WINNER.sha256']:
        freeze(winnerout/name,(controlout/'cases/positive-complete11'/name).read_bytes())
    resumedwinner=subprocess.run([str(winnerout)if x==str(controlout)else x for x in command],cwd='/tmp',capture_output=True,text=True,timeout=10)
    winnerrow=read_json(resumedwinner.stdout.encode())
    if resumedwinner.returncode or winnerrow['phase_queries']or winnerrow['status']!='WINNER':raise AssertionError('terminal winner requery')
    freeze(out/'controls/terminal-winner-cli.log',(resumedwinner.stdout+resumedwinner.stderr).encode())
    errorbundle=out/'controls/error-bundle';errorcase=dict(entries[0],source_sha256='0'*64)
    freeze(errorbundle/errorcase['source_file'],(small/errorcase['source_file']).read_bytes())
    freeze(errorbundle/'catalog.json',json_bytes(dict(small_controls=True,target=7,cases=[errorcase])));manifest(errorbundle)
    errorout=out/'controls/error-cli'
    errorcmd=[str(errorbundle)if x==str(small)else str(errorout)if x==str(controlout)else x for x in command]
    errorrun=subprocess.run(errorcmd,cwd='/tmp',capture_output=True,text=True,timeout=10)
    errorrow=read_json((errorout/'summary.json').read_bytes())
    if errorrun.returncode!=2 or errorrow['status']!='ERROR'or errorrow['phase_queries']:raise AssertionError('CLI ERROR misreported as negative')
    freeze(out/'controls/error-cli.log',(errorrun.stdout+errorrun.stderr).encode())
    metric(5*1024**3);holdout=out/'controls/resource-hold-cli'
    held=subprocess.run([str(holdout)if x==str(controlout)else x for x in command],cwd='/tmp',capture_output=True,text=True,timeout=10)
    hold=read_json((holdout/'summary.json').read_bytes())
    if held.returncode or hold['phase_queries']or hold['status']!='UNKNOWN_RESOURCE_PAUSE':raise AssertionError('resource hold failed')
    freeze(out/'controls/resource-hold-cli.log',(held.stdout+held.stderr).encode())
    test=subprocess.run(['python3','-m','unittest','tests.test_old_span_census_support42','tests.test_rankone_census42'],cwd=ROOT,capture_output=True,text=True,timeout=15)
    freeze(out/'tests.log',(test.stdout+test.stderr).encode())
    if test.returncode:raise RuntimeError('new census/support tests failed')
    freeze(out/'PROOF.md',PROOF.encode())
    controlreport=dict(status='PASS',frozen_actual_CLI_from='/tmp',requested_seed=2026110343301,
        normalized_seed=2026110343301%2147483647,source_rank=8,schoolbook_census_points=18,
        schoolbook_native_census_oracles=11,brute_rankone_factor_pairs_checked=225,schoolbook_complete_support_bound7='UNSAT old-S-only',
        positive_complete11='SAT verified7/all64',positive_partial10='SAT verified7/all64; incomplete census',
        positive_partial8='UNSAT catalog-only',all_three_free_axes='SAT verified7/all64',
        resume_queries=0,terminal_winner_resume_queries=0,CLI_ERROR_exit_code=2,working5GiB_hold='clean UNKNOWN/noquery',production_queries=0)
    freeze(out/'controls/CONTROL_REPORT.json',json_bytes(controlreport));manifest(out)
    job=dict(id='old-span-census-support42-pilot2',cpu=1,memory_mb=1536,seconds=1815,enabled=False,
        command=['python3','-B',str(wrapper),'--bundle',str(out),'--output-dir',str(camp/'old-span-census-support42-state-v2'),
           '--guard',str(camp/'operations-v3/state.json'),'--seconds','1800','--census-seconds','60','--support-seconds','60',
           '--oracle-seconds','5','--memory-mb','1536','--phase-mb','128','--cap','4096','--seed','2026110343301',
           '--stop-file',str(camp/'WINNER.json'),'--deadline-utc','2026-11-04T21:31:16Z'])
    freeze(out/'PROPOSED-JOB.json',json_bytes(job))
    ready=dict(status='READY_UNLAUNCHED',production_queries=0,production_support_queries=0,cases=12,sources=4,free_axes=3,
        source_A_rank=93,initial_point_counts=[x['initial_points']for x in cases],target92=True,
        census_seconds_per_case=60,census_oracle_seconds=5,census_point_cap=4096,support_seconds_per_case=60,
        overall_inner_seconds=1800,outer_seconds=1815,cpu=1,memory_MiB=1536,working_hold_GiB=5,phase_artifact_cap_MiB=128,
        native_control=controlreport,test_count=9,manifest_sha256=sha((out/'manifest.json').read_bytes()),
        launch_script_sha256=sha(wrapper.read_bytes()),preparation_CPU_seconds=cpu()-cpu0,
        preparation_wall_seconds=time.monotonic()-start,active_v3_files_changed=False,queue_changed=False,
        scope='Complete census + support UNSAT excludes only these old active-pair spans; partial-catalog UNSAT excludes only those recorded points.')
    if ready['preparation_CPU_seconds']>60:raise RuntimeError('prep exceeded60CPU seconds')
    freeze(out/'READY.json',json_bytes(ready))
    freeze(out/'full-manifest.json',json_bytes(dict(files={str(x.relative_to(out)):sha(x.read_bytes())for x in out.rglob('*')if x.is_file()and'__pycache__'not in x.parts})))
    for file in out.rglob('*'):
        if file.is_file():file.chmod(0o555 if '.so'in file.name else 0o444)
    print(json_bytes(ready).decode())


PROOF='''# Exact old-span census and coefficient-support search over F2

For each verified source and free axis, let A be the625×93 matrix of the
nonzero rank-one fixed-pair columns and W the93×25 free-factor rows. Full
column rank93 is required and checked. Source verification proves A W=T.
Each rank-one point Q in S=im(A) has a unique nonzero coefficient c. Over F2,
its nonzero factor pair is unique. The oracle encodes a⊗b=A c in all625
cells, requires both factors nonzero, and blocks each known c individually.
It has no lambda or outside-linear-span restriction. Each SAT point passes
every Boolean CNF/XOR equation and an explicit625-cell matrix comparison.
UNSAT after blocking all recorded points proves completeness only in S.
UNKNOWN, timeout,4096 points, and common-factor closure saturation leave a
partial census. Optional closure adds independently checked rank-one points.

Put the discovered c labels into columns C. An algorithm using these fixed
pairs has arbitrary free-factor rows Y and tensor A C Y. Injectivity of A
gives A C Y=A W iff C Y=W. The support encoder uses the full dictionary,
including arbitrary new coefficient labels and linearly dependent columns.
Its existing exact physical fixed-pair equations and RHS are rechecked in
all625 cells against A C and A W. Exact nonzero-row indicators and a native
cardinality circuit enforce at most92 products. Every decoded model passes
all CNF/XOR equations, explicit C Y=W, all-axis slot restoration, the full
15625-entry tensor verifier and a separate stdlib record gate before WINNER.
Free axis1 reverses the physical fixed-pair order for cyclic (w,u) encoding;
all three axis restorations have actual n2 SAT/full64 positive controls.

Complete census UNSAT plus support UNSAT excludes every decomposition of
rank at most92 whose fixed pairs lie in this particular old S. It is not a
global lower bound. Partial-catalog support UNSAT excludes that dictionary
only. An exact SAT certificate is valid even with a partial census. The
schoolbook n2 old span has exactly18 rank-one points (two compatible j
blocks, each with9 nonzero rank-one2×2 matrices), independently brute checked
over225 nonzero factor pairs. Complete18 support≤7 is UNSAT even though the
global Strassen7 algorithm exists. The positive old span has11 points;
saturated closure10 remains partial and already admits a verified7 witness.

Each oracle is fresh and bounded; retained point/checkpoint data does not
claim learned-clause serialization. Requested seeds are recorded separately
from seed modulo2147483647. Hash-bound checkpoints preserve points, exact
formula identities, support dictionary identities and terminal negatives.
Unchanged complete-S negatives are never automatically queried again; a
partial dictionary negative is reused only for the identical point hash.
The CPU1 job allows60s census with5s/oracle then60s support per case,1800s
total and1536MiB child address space. Export sidecars precede the final WINNER marker; completed winner resumption
rechecks the independent certificate and performs zero queries. Logs are capped
at8MiB and support-formula audit copies at7MiB compressed; an overlarge
audit copy pauses UNKNOWN rather than truncating its point dictionary.
Fresh campaign guard checks occur
between oracles;5GiB working hold/128MiB phase artifact budget pause cleanly
as UNKNOWN with points and cursor. No production target queries run in prep.
'''


if __name__=='__main__':main()
