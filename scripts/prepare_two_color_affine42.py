"""Freeze at most6 additive triangles and coupled color-profile formulas."""
from collections import Counter
import argparse
import hashlib
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import pair_column
from mmsearch.two_color_affine_sat42 import build_problem,control_assumptions,quotient_certificate,independent_basis
from mmsearch.local_eliminated42sat import write_problem
from mmsearch.recombine import digest
from mmsearch.search import encode_candidate
from mmsearch.slice_compression import canonical_masks
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes

ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,action='append',required=True)
    p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[];inventory=[];eligible={}
    for number,path in enumerate(args.source):
        raw=path.read_bytes();candidate=json.loads(raw);terms,_=canonical_masks(candidate);report=verify_candidate(candidate,random_trials=0)
        if len(terms)!=93 or report['rank']!=93 or not report['valid'] or report['exact_entries_checked']!=15625:raise ValueError('strict active93 source required')
        label=f'source-{number:02d}-{sha(raw)[:12]}';freeze(out/'sources'/(label+'.json'),raw)
        sources.append(dict(label=label,candidate=candidate,terms=terms,raw_sha256=sha(raw)))
        axes=[]
        for axis in range(3):
            counts=Counter(term[axis] for term in terms);singles=sorted(value for value,count in counts.items() if count==1)
            triangles=sorted({tuple(sorted((d,e,d^e))) for d,e in combinations(singles,2) if counts[d^e]==1})
            others=[a for a in range(3) if a!=axis];columns=[pair_column([term[a] for a in others],25) for term in terms]
            positions={term[axis]:g for g,term in enumerate(terms) if counts[term[axis]]==1};entries=[]
            for palette in triangles:
                selected={positions[color] for color in palette};neutral=[column for g,column in enumerate(columns) if g not in selected]
                matrices=[columns[positions[palette[0]]]^columns[positions[palette[2]]],columns[positions[palette[1]]]^columns[positions[palette[2]]]]
                certificate=quotient_certificate(matrices,neutral)
                entry=dict(palette=palette,quotient_rank=certificate['quotient_syndrome_rank'],neutral_span_rank=certificate['neutral_span_rank'])
                entries.append(entry)
                if entry['quotient_rank']==2:eligible.setdefault((number,axis),[]).append(palette)
            axes.append(dict(free_axis=axis,multiplicity_histogram=dict(Counter(counts.values())),additive_triangle_count=len(triangles),
                rank2_triangle_count=sum(entry['quotient_rank']==2 for entry in entries),triangles=entries))
        inventory.append(dict(source_id=label,source_path=str(path.resolve()),source_raw_sha256=sha(raw),
            source_canonical_sha256=digest(encode_candidate(terms,5)),strict_active_rank=93,axes=axes))
    desired=[(0,0),(1,1),(2,2),(3,0),(0,1),(1,2)]
    desired += [key for key in sorted(eligible) if key not in desired]
    chosen=[];affine_signatures=set();selected_signatures=[]
    for key in desired:
        if key not in eligible or key[0]>=len(sources):continue
        source_number,axis=key;terms=sources[source_number]['terms'];others=[a for a in range(3) if a!=axis]
        columns=[pair_column([term[a] for a in others],25) for term in terms]
        for palette in eligible[key]:
            selected={g for g,term in enumerate(terms) if term[axis] in palette}
            neutral=[column for g,column in enumerate(columns) if g not in selected]
            matrices=[0,0]
            for g in selected:
                color=palette.index(terms[g][axis])
                if color in (0,2):matrices[0]^=columns[g]
                if color in (1,2):matrices[1]^=columns[g]
            basis=independent_basis(neutral)
            for bit in sorted(basis):
                for other in basis:
                    if other!=bit and basis[other]>>bit&1:basis[other]^=basis[bit]
            residuals=[]
            for matrix in matrices:
                for bit in sorted(basis,reverse=True):
                    if matrix>>bit&1:matrix^=basis[bit]
                residuals.append(matrix)
            signature=digest([sorted(basis.values()),residuals])
            if signature in affine_signatures:continue
            affine_signatures.add(signature);selected_signatures.append(signature);chosen.append((*key,palette));break
        if len(chosen)==6:break
    cases=[];spaces=[]
    for number,(source_number,axis,palette) in enumerate(chosen):
        source=sources[source_number];space_id=f'space-{number:02d}-{source["label"]}-a{axis}'
        directory=out/'spaces'/space_id;control=build_problem(source['candidate'],axis,palette[0],palette[1],(1,1,1))
        if control['metadata']['selected_color_counts']!=[1,1,1] or control['quotient_certificate']['quotient_syndrome_rank']!=2:
            raise ValueError('selected space lacks its exact triangle/quotient conditions')
        freeze(directory/'control.json',json_bytes(control));freeze(directory/'control.assumptions.json',json_bytes(control_assumptions(control)))
        freeze(directory/'quotient-certificate.json',json_bytes(control['quotient_certificate']));write_problem(control,directory/'control')
        (directory/'control.cnf').chmod(0o444)
        profiles=[]
        for profile in ((1,1,0),(1,0,1),(0,1,1)):
            profile_name=''.join(map(str,profile));problem=build_problem(source['candidate'],axis,palette[0],palette[1],profile)
            path=directory/f'profile-{profile_name}.json';freeze(path,json_bytes(problem));write_problem(problem,directory/f'profile-{profile_name}')
            (directory/f'profile-{profile_name}.cnf').chmod(0o444)
            case=dict(id=space_id+'-p'+profile_name,space_id=space_id,source_sha256=source['raw_sha256'],free_axis=axis,palette=palette,
                profile=profile,selected_k=3,target_q=2,candidate_product_bound=92,target=str(path.relative_to(out)),
                control=str((directory/'control.json').relative_to(out)),control_assumptions=str((directory/'control.assumptions.json').relative_to(out)),
                formula_sha256=problem['metadata']['formula_sha256'],family_sha256=problem['metadata']['family_sha256'],
                variables=problem['nv'],CNF=len(problem['clauses']),native_XOR=len(problem['xors']),quotient_syndrome_rank=2)
            cases.append(case);profiles.append(case)
        space=dict(id=space_id,canonical_affine_pair_signature=selected_signatures[number],source_id=source['label'],source_sha256=source['raw_sha256'],free_axis=axis,palette=palette,
            selected_color_counts=[1,1,1],neutral_terms=90,target_profiles=[case['profile'] for case in profiles],
            omitted_monochrome_profiles=[[2,0,0],[0,2,0],[0,0,2]],omission_reason='exact quotient-syndrome rank2',
            quotient_certificate=control['quotient_certificate'])
        spaces.append(space);freeze(directory/'space.json',json_bytes(space))
    freeze(out/'TRIANGLE-INVENTORY.json',json_bytes(inventory));freeze(out/'SPACES.json',json_bytes(spaces))
    paths=[]
    for name in ('mmsearch','scripts'):paths.extend(sorted((ROOT/name).rglob('*.py')))
    paths.extend(ROOT/name for name in ('tests/test_two_color_affine_sat42.py','tests/test_affine_slice_rank_sat42.py'))
    closure={}
    for path in paths:
        name=str(path.relative_to(ROOT));raw=path.read_bytes();freeze(out/'code'/name,raw);closure[name]=sha(raw)
    freeze(out/'code/tests/__init__.py',b'');closure['tests/__init__.py']=sha(b'');freeze(out/'launch-closure.json',json_bytes(closure))
    for path in sorted((ROOT/'.xor-deps').rglob('*')):
        if path.is_file() and '__pycache__' not in str(path):freeze(out/'deps'/path.relative_to(ROOT/'.xor-deps'),path.read_bytes())
    files={str(path.relative_to(out)):sha(path.read_bytes()) for path in sorted(out.rglob('*')) if path.is_file()}
    freeze(out/'portfolio.json',json_bytes(dict(cases=cases,spaces=spaces,files=files,source_count=len(sources),
        target_n5_queries_dispatched=0,scope='Only fixed source/two-dimensional color space/free-axis/profile families; no global rank92 UNSAT.')))
    command=[sys.executable,'-B',str(out/'code/scripts/verify_two_color_affine42_ready.py'),'--bundle',str(out)]
    done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=30)
    if done.returncode:raise ValueError(done.stderr)
    print(done.stdout);print(json.dumps(dict(status='PREPARED',spaces=len(spaces),target_profiles=len(cases),target_n5_queries=0,outdir=str(out))))
    return 0


if __name__=='__main__':raise SystemExit(main())
