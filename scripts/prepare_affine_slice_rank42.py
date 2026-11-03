"""Freeze a small all-axis affine-slice portfolio without target solving."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.affine_slice_rank_sat42 import build_problem,control_assumptions,write_problem
from mmsearch.recombine import digest
from mmsearch.search import encode_candidate
from mmsearch.slice_compression import canonical_masks
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes

ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,action='append',required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    inventory=[];proposals=[]
    for number,path in enumerate(args.source):
        raw=path.read_bytes();candidate=json.loads(raw);terms,_=canonical_masks(candidate);report=verify_candidate(candidate,random_trials=0)
        if report['rank']!=93 or not report['valid'] or report['exact_entries_checked']!=15625:raise ValueError('requires full verified93 sources')
        label=f'source-{number:02d}-{sha(raw)[:12]}';freeze(out/'sources'/(label+'.json'),raw)
        axes=[]
        for axis in range(3):
            counts=Counter(term[axis] for term in terms)
            repeated=sorted(((delta,k) for delta,k in counts.items() if k>=2),key=lambda item:(-item[1],item[0]))
            axes.append(dict(free_axis=axis,multiplicity_histogram=dict(Counter(counts.values())),repeated=[dict(delta=d,k=k) for d,k in repeated]))
            # All axes of AE/current original, plus the changed free axis of
            # the two raw frontier sources; the complete inventory is retained.
            if repeated and (number<2 or axis==1):proposals.append((label,candidate,axis,repeated[0][0],sha(raw)))
        inventory.append(dict(source_id=label,path=str(path.resolve()),raw_sha256=sha(raw),canonical_sha256=digest(encode_candidate(terms,5)),
                              rank=93,exact_entries_checked=15625,axes=axes))
    cases=[];seen={};duplicates=[]
    for label,candidate,axis,delta,source_sha in proposals:
        target=build_problem(candidate,axis,delta);k=target['metadata']['selected_count']
        if target['metadata']['formula_sha256'] in seen:
            duplicates.append(dict(source_id=label,free_axis=axis,delta=delta,exact_formula_same_as=seen[target['metadata']['formula_sha256']]));continue
        case_id=f'case-{len(cases):02d}-{label}-a{axis}-k{k}';seen[target['metadata']['formula_sha256']]=case_id
        control=build_problem(candidate,axis,delta,rank_bound=k);directory=out/'cases'/case_id
        freeze(directory/'target.json',json_bytes(target));freeze(directory/'control.json',json_bytes(control))
        freeze(directory/'control.assumptions.json',json_bytes(control_assumptions(control)))
        write_problem(target,directory/'target');write_problem(control,directory/'control')
        for name in ('target.cnf','control.cnf'):(directory/name).chmod(0o444)
        case=dict(id=case_id,source_id=label,source_sha256=source_sha,free_axis=axis,delta=delta,k=k,target_rank_bound=k-1,
            candidate_product_bound=target['metadata']['candidate_rank_bound'],unmixed_matrix_rank=target['metadata']['unmixed_matrix_rank'],
            target=str((directory/'target.json').relative_to(out)),control=str((directory/'control.json').relative_to(out)),
            control_assumptions=str((directory/'control.assumptions.json').relative_to(out)),
            target_formula_sha256=target['metadata']['formula_sha256'],control_formula_sha256=control['metadata']['formula_sha256'],
            target_variables=target['nv'],target_cnf_clauses=len(target['clauses']),target_native_xors=len(target['xors']),
            control_variables=control['nv'],family_sha256=target['metadata']['family_sha256'])
        freeze(directory/'case.json',json_bytes(case));cases.append(case)
    freeze(out/'MULTIPLICITY-INVENTORY.json',json_bytes(inventory));freeze(out/'EXACT-FORMULA-DEDUP.json',json_bytes(duplicates))
    closure={}
    paths=[]
    for name in ('mmsearch','scripts'):paths.extend(sorted((ROOT/name).rglob('*.py')))
    paths.append(ROOT/'tests/test_affine_slice_rank_sat42.py')
    for path in paths:
        name=str(path.relative_to(ROOT));raw=path.read_bytes();freeze(out/'code'/name,raw);closure[name]=sha(raw)
    freeze(out/'code/tests/__init__.py',b'');closure['tests/__init__.py']=sha(b'')
    freeze(out/'launch-closure.json',json_bytes(closure))
    for path in sorted((ROOT/'.xor-deps').rglob('*')):
        if path.is_file() and '__pycache__' not in str(path):freeze(out/'deps'/path.relative_to(ROOT/'.xor-deps'),path.read_bytes())
    files={str(path.relative_to(out)):sha(path.read_bytes()) for path in sorted(out.rglob('*')) if path.is_file()}
    portfolio=dict(cases=cases,files=files,source_count=len(inventory),target_queries_dispatched=0,
        formula_policy='AND products plus complete native XOR matrix equations; arbitrary other-axis rank factors; zero columns allowed; no full-rank restriction.',
        scope='Each source/delta/free-axis affine slice separately; exact formula dedup only, no global UNSAT claim.')
    freeze(out/'portfolio.json',json_bytes(portfolio))
    command=[sys.executable,'-B',str(out/'code/scripts/verify_affine_slice_rank42_ready.py'),'--bundle',str(out)]
    done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=25)
    if done.returncode:raise ValueError(done.stderr)
    print(done.stdout);print(json.dumps(dict(status='PREPARED',cases=len(cases),sources=len(inventory),target5_queries=0,outdir=str(out))))
    return 0


if __name__=='__main__':raise SystemExit(main())
