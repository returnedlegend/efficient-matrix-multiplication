"""Read-only audit and algebraic/implied coverage certificates; never invokes a solver."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time


def sha(raw):return hashlib.sha256(raw).hexdigest()


def rank_witness(rows):
    basis={}
    for i,value in enumerate(rows):
        witness=1<<i
        while value:
            pivot=value.bit_length()-1
            if pivot not in basis:basis[pivot]=(value,witness);break
            old,proof=basis[pivot];value^=old;witness^=proof
    for value,proof in basis.values():
        check=0
        for i,row in enumerate(rows):
            if proof>>i&1:check^=row
        if check!=value:raise AssertionError('row-rank witness mismatch')
    return [dict(pivot=p,row=basis[p][0],input_row_combination=basis[p][1])for p in sorted(basis)]


def canonical_source(source,hp):
    rows={p:[row,c]for p,(row,c)in hp.linear_basis(source['A_columns']).items()}
    for p in sorted(rows):
        for q in rows:
            if p!=q and rows[q][0]>>p&1:rows[q][0]^=rows[p][0];rows[q][1]^=rows[p][1]
    values=[rows[p][0]for p in sorted(rows)];labels=[rows[p][1]for p in sorted(rows)]
    if values!=hp.canonical_span(source['A_columns']):raise AssertionError('noncanonical source basis')
    if any(hp.combine(source['A_columns'],c)!=v for v,c in zip(values,labels)):raise AssertionError('canonical basis witness failed')
    return values,labels


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['bundle','selection','state','hyper-bundle','hyper-state','output-dir']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();started=time.monotonic();cpu0=time.process_time();bundle=a.bundle.resolve();selection=a.selection.resolve();state=a.state.resolve()
    hyper=a.hyper_bundle.resolve();hypstate=a.hyper_state.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(bundle/'runtime'))
    from mmsearch import hyperplane_rankone42 as hp,rankone_census42 as rc,old_span_support42 as support
    from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json
    from scripts.prototype_rankone_census42 import load_state
    from scripts.campaign_hyperplane_catalog42 import model_identity
    from scripts.verify_record42_independent import verify_bytes
    def save(name,value):freeze(out/name,json_bytes(value))
    def pin(path):return dict(path=str(path),sha256=sha(path.read_bytes()))
    for directory in [bundle,selection,hyper]:
        manifest=read_json((directory/('manifest.json'if directory==hyper else'full-manifest.json')).read_bytes())
        for name,expected in manifest['files'].items():
            if sha((directory/name).read_bytes())!=expected:raise AssertionError('frozen input changed: '+name)
    catalog=read_json((bundle/'catalog.json').read_bytes());selected=read_json((selection/'selection.json').read_bytes());byid={c['id']:c for c in catalog['cases']}
    summary=read_json((state/'summary.json').read_bytes());coverage=read_json((state/'coverage.json').read_bytes())
    check=dict(coverage);digest=check.pop('coverage_sha256')
    if hp.digest(check)!=digest or summary['production_queries']!=20 or summary['coverage_counts']!={'OLD_S_ONLY_UNSAT':10}:raise AssertionError('production coverage mismatch')
    freeze(out/'recorded-production-summary.json',(state/'summary.json').read_bytes());freeze(out/'recorded-production-coverage.json',(state/'coverage.json').read_bytes())
    parents={};sources={};source_proofs={};actual_queries=0;all_native=[]
    for caseid in selected['representative_ids']:
        spec=byid[caseid];raw=(bundle/spec['source_file']).read_bytes();candidate=read_json(raw)
        source=hp.prepare_source(candidate,spec['free_axis']);sources[caseid]=source
        if spec['source_file']not in source_proofs:
            proof=verify_bytes(raw)
            if not proof['valid']or proof['canonical_essential_products']!=93 or proof['exact_entries_checked']!=15625:raise AssertionError('source independent full tensor failed')
            save('source-verification/'+Path(spec['source_file']).name,proof);source_proofs[spec['source_file']]=proof
        folder=state/'cases'/caseid;cp=load_state(folder/'census',source,4096);points=cp['points']
        if not(cp['census_complete']and cp['status']=='CENSUS_COMPLETE'and cp['oracle_attempts']==1):raise AssertionError('not one complete census oracle')
        if sha((folder/'case-result.json').read_bytes())!=coverage['cases'][caseid]['result_sha256']:raise AssertionError('case result checksum mismatch')
        census_problem=read_json((folder/'census/oracle-0000/problem.json').read_bytes());expected_oracle=rc.build_oracle(source,points)
        if hp.digest(census_problem)!=hp.digest(expected_oracle):raise AssertionError('complete census did not block this exact catalog')
        census_result=read_json((folder/'census/oracle-0000/result.json').read_bytes())
        support_cp=read_json((folder/'support-checkpoint.json').read_bytes());copy=dict(support_cp);expected=copy.pop('checkpoint_sha256')
        if expected!=hp.digest(copy)or support_cp['point_catalog_sha256']!=hp.digest(points):raise AssertionError('support checkpoint mismatch')
        resultfile=folder/support_cp['result_file'];support_result=read_json(resultfile.read_bytes())
        if sha(resultfile.read_bytes())!=support_cp['result_sha256']:raise AssertionError('support result changed')
        support_problem=read_json(gzip.open(resultfile.parent/'problem.json.gz','rb').read());expected_support=support.build_problem(candidate,source,points,92)
        if support_problem!=read_json(json_bytes(expected_support)):raise AssertionError('support formula does not match full point catalog')
        for result,problem,status,seconds in [(census_result,census_problem,'CENSUS_COMPLETE_UNSAT',5),(support_result,support_problem,'SUPPORT_CATALOG_UNSAT',60)]:
            if not(result['status']==status and result['formula_sha256']==problem['metadata']['formula_sha256']and result['worker_exitcode']==0
                   and result['worker_reaped']and result['threads']==1 and result['memory_mb']==1536 and result['wall_seconds']==seconds
                   and not result['assumptions']and result['solver_seed']==result['requested_seed']%2147483647
                   and result['solver_options']['seed']==str(result['solver_seed'])):raise AssertionError('native result/provenance/limits mismatch')
            all_native.append(dict(case=caseid,status=status,formula_sha256=result['formula_sha256'],requested_seed=result['requested_seed'],solver_seed=result['solver_seed'],
                 worker_pid=result['worker_pid'],worker_reaped=True,elapsed_seconds=result['elapsed_seconds']));actual_queries+=1
        # Independently validate every625-cell rank-one column and coefficient label.
        for point in points:
            outer=0
            for i in range(25):
                for j in range(25):outer|=((point['a']>>i&1)&(point['b']>>j&1))<<(25*i+j)
            if outer!=hp.combine(source['A_columns'],point['c']):raise AssertionError('census point physical matrix mismatch')
        dsu=list(range(93))
        def find(i):
            while dsu[i]!=i:dsu[i]=dsu[dsu[i]];i=dsu[i]
            return i
        for point in points:
            indices=list(hp.bits(point['c']))
            for i in indices[1:]:dsu[find(i)]=find(indices[0])
        groups={}
        for i in range(93):groups.setdefault(find(i),[]).append(i)
        blocks=sorted(groups.values(),key=lambda x:x[0]);component={i:b for b,block in enumerate(blocks)for i in block};point_components=[]
        for point in points:
            comps={component[i]for i in hp.bits(point['c'])}
            if len(comps)!=1:raise AssertionError('point crosses certified coefficient components')
            point_components.append(next(iter(comps)))
        blockcerts=[]
        for block in blocks:
            rows=[source['W_rows'][i]for i in block];rankcert=rank_witness(rows)
            blockcerts.append(dict(coordinates=block,W_rows=rows,rank=len(rankcert),echelon_witness=rankcert))
        bound=sum(b['rank']for b in blockcerts)
        if bound!=93 or any(b['rank']!=len(b['coordinates'])for b in blockcerts):raise AssertionError('unexpected algebraic support bound')
        canonical,_=canonical_source(source,hp)
        cert=dict(id=caseid,dimension=5,field=2,free_axis=source['free_axis'],source=spec,source_A_rank=93,
             A_columns=source['A_columns'],canonical_S_basis=canonical,physical_S_sha256=hp.digest(canonical),
             target_columns=source['target_columns'],target_sha256=source['target_sha256'],
             W_rows=source['W_rows'],W_columns=source['W_columns'],points=points,C_columns=[p['c']for p in points],
             C_rows=[sum(1<<j for j,p in enumerate(points)if p['c']>>i&1)for i in range(93)],point_components=point_components,
             components=blockcerts,sum_component_W_ranks=bound,catalog_minimum_product_count=93,
             baseline_upper_bound_products=93,complete_census=True,old_S_minimum_product_count=93,
             census_result=pin(folder/'census/oracle-0000/result.json'),census_problem=pin(folder/'census/oracle-0000/problem.json'),
             census_checkpoint=pin(folder/'census/checkpoint.json'),support_result=pin(resultfile),
             support_problem=pin(resultfile.parent/'problem.json.gz'),support_checkpoint=pin(folder/'support-checkpoint.json'),
             census_formula_sha256=census_result['formula_sha256'],support_formula_sha256=support_result['formula_sha256'],
             point_catalog_sha256=hp.digest(points),point_matrix_columns_sha256=hp.digest([hp.combine(source['A_columns'],p['c'])for p in points]),
             fresh_solver_queries=0,scope='Minimum93 only among decompositions with fixed pairs in this old S; full-S extension relies on the recorded complete census UNSAT.')
        save(f'parents/{caseid}.json',cert);parents[caseid]=cert
    if actual_queries!=20:raise AssertionError('actual query count changed')
    save('actual-production-oracles.json',dict(recorded_oracles=all_native,recorded_query_count=20,fresh_audit_queries=0))
    # Bind every source/axis to a complete parent with exact actual arrays.
    maps={};deferred=[]
    for spec in catalog['cases']:
        source=hp.prepare_source(read_json((bundle/spec['source_file']).read_bytes()),spec['free_axis']);canonical,labels=canonical_source(source,hp)
        matches=[name for name,parent in parents.items()if parent['free_axis']==source['free_axis']and parent['canonical_S_basis']==canonical and parent['target_columns']==source['target_columns']]
        if len(matches)!=1:raise AssertionError('missing or ambiguous exact parent S/target')
        parentid=matches[0];parent=parents[parentid];column_coords=[hp.coordinates(parent['canonical_S_basis'],column)for column in source['A_columns']]
        if any(c is None or hp.combine(parent['canonical_S_basis'],c)!=column for c,column in zip(column_coords,source['A_columns'])):raise AssertionError('source-to-parent exact span witness mismatch')
        name=f"source-maps/{spec['id']}.json";mapping=dict(source_case_id=spec['id'],parent_case_id=parentid,source_sha256=spec['source_sha256'],source_identity=rc.source_identity(source),
             source_canonical_S_basis=canonical,parent_canonical_S_basis=parent['canonical_S_basis'],
             source_target_columns=source['target_columns'],parent_target_columns=parent['target_columns'],
             exact_basis_equality=True,exact_target_equality=True,free_axis=source['free_axis'],
             source_A_columns=source['A_columns'],source_column_coordinates_in_parent_S=column_coords,
             canonical_S_row_coordinates_in_source_A=labels,parent_certificate_sha256=sha((out/f'parents/{parentid}.json').read_bytes()))
        save(name,mapping);maps[spec['id']]=(source,canonical,labels,parentid,name)
        if spec['id']not in selected['representative_ids']:
            if (state/'cases'/spec['id']).exists():raise AssertionError('deferred duplicate was unexpectedly queried')
            deferred.append(dict(id=spec['id'],direct_solver_status='DEFERRED_UNSEARCHED',direct_solver_queries=0,
                 implication_status='IMPLIED_BY_EQUAL_COMPLETE_PARENT_S',parent_case_id=parentid,exact_equality_witness=name))
    save('deferred-source-models.json',deferred)
    hypercoverage_raw=(hypstate/'coverage.json').read_bytes();hypercoverage=read_json(hypercoverage_raw);check=dict(hypercoverage);digest=check.pop('coverage_sha256')
    if hp.digest(check)!=digest:raise AssertionError('historical hyperplane coverage digest mismatch')
    for caseid,record in hypercoverage['cases'].items():
        if sha((hypstate/'cases'/caseid/'checkpoint.json').read_bytes())!=record['checkpoint_sha256']:raise AssertionError('historical hyperplane checkpoint changed')
    freeze(out/'recorded-hyperplane-coverage.json',hypercoverage_raw)
    hypercatalog=read_json((hyper/'catalog.json').read_bytes());status_counts=Counter();weight_counts=Counter();parent_counts=Counter();ledger=out/'hyperplane-implications.jsonl'
    with ledger.open('xb')as stream:
        for entry in hypercatalog['cases']:
            spec=read_json((hyper/entry['file']).read_bytes());key=f"source-{spec['source_id']}-axis-{spec['free_axis']}";source,values,labels,parentid,mapfile=maps[key]
            raw=(hyper/spec['source_file']).read_bytes()
            if sha(raw)!=spec['source_sha256']or raw!=(bundle/byid[key]['source_file']).read_bytes():raise AssertionError('hyperplane source bytes mismatch')
            lam=spec['lambda_mask'];dual=[(lam&c).bit_count()%2 for c in labels];k=next(i for i,b in enumerate(dual)if b)
            coords=[(1<<i)^((1<<k)if dual[i]else 0)for i in range(93)if i!=k]
            H=[value^(values[k]if dual[i]else 0)for i,value in enumerate(values)if i!=k]
            source_coeffs=[label^(labels[k]if dual[i]else 0)for i,label in enumerate(labels)if i!=k]
            if any((lam&c).bit_count()%2 or hp.combine(source['A_columns'],c)!=row for c,row in zip(source_coeffs,H)):raise AssertionError('H kernel/source witness failed')
            if any(hp.combine(parents[parentid]['canonical_S_basis'],c)!=row for c,row in zip(coords,H)):raise AssertionError('H is not contained in complete parent S')
            pivotmask=sum(1<<(row.bit_length()-1)for row in H)
            if len(H)!=92 or pivotmask.bit_count()!=92 or any(row&pivotmask!=1<<(row.bit_length()-1)for row in H):raise AssertionError('H basis not exact canonical rank92')
            physical=hp.digest(dict(axis=source['free_axis'],target=source['target_sha256'],span=H))
            if physical!=spec['physical_H_sha256']or model_identity(source,lam)!=spec['model_sha256']:raise AssertionError('H/model hash does not match catalog')
            if any((lam&w).bit_count()%2 for w in source['W_columns']):raise AssertionError('H does not contain target columns')
            old=hypercoverage['cases'].get(entry['id']);actual=old['status']if old else'UNVISITED'
            record=dict(id=entry['id'],status='IMPLIED_BY_PARENT',new_solver_queries=0,recorded_direct_solver_status=actual,
                recorded_direct_oracle_attempts=old.get('oracle_attempts',0)if old else 0,parent_case_id=parentid,parent_minimum93=True,
                source_map_file=mapfile,source_map_sha256=sha((out/mapfile).read_bytes()),source_id=spec['source_id'],free_axis=source['free_axis'],
                lambda_mask=lam,lambda_weight=spec['lambda_weight'],physical_H_sha256=physical,model_sha256=spec['model_sha256'],
                H_basis_coefficients_in_parent_canonical_S=coords,H_basis_coefficients_in_source_A=source_coeffs,
                H_dimension=92,H_subset_parent_S=True,exact_parent_basis_and_target_equality=True,
                reason='Every rank-one fixed pair in H lies in complete parent S; parent minimum93 excludes support≤92 in H. This is an implication, not a new oracle UNSAT.')
            stream.write(json.dumps(record,sort_keys=True,separators=(',',':')).encode()+b'\n');status_counts[actual]+=1;weight_counts[spec['lambda_weight']]+=1;parent_counts[parentid]+=1
    if sum(status_counts.values())!=2707:raise AssertionError('not all2707 hyperplanes mapped')
    report=dict(status='PASS',complete_parent_spans=10,parent_census_points=[len(x['points'])for x in parents.values()],
        parent_algebraic_minima={name:p['catalog_minimum_product_count']for name,p in parents.items()},
        recorded_parent_census_queries=10,recorded_parent_support_queries=10,new_solver_queries=0,
        hyperplanes_total=2707,hyperplanes_implied_by_parent=2707,historical_direct_H_status_counts=dict(status_counts),
        historical_direct_H_oracle_attempts=sum(v['oracle_attempts']for v in hypercoverage['cases'].values()),
        unvisited_H_now_implied=status_counts['UNVISITED'],hyperplane_weights=dict(weight_counts),hyperplanes_by_parent=dict(parent_counts),
        deferred_source_models_unqueried=2,deferred_models_scope='Same S/axis/target implication only; no fabricated census or direct UNSAT results.',
        hyperplane_ledger_sha256=sha(ledger.read_bytes()),input_pins={name:pin(path)for name,path in [
            ('v2_READY',bundle/'READY.json'),('v2_full_manifest',bundle/'full-manifest.json'),('v3_READY',selection/'READY.json'),
            ('v3_full_manifest',selection/'full-manifest.json'),('production_summary',state/'summary.json'),('production_coverage',state/'coverage.json'),
            ('hyperplane_catalog',hyper/'catalog.json'),('hyperplane_coverage',hypstate/'coverage.json')]},
        CPU_seconds=time.process_time()-cpu0,wall_seconds=time.monotonic()-started,
        scope='F2 only. Exact minimum93 within each specified old active-pair span S; no global rank lower bound. A ≤92 algorithm must escape these spaces.')
    save('REPORT.json',report)
    freeze(out/'PROOF.md',('For each full-rank source A, the completed point oracle blocks every verified rank-one Q=A c in S and returns UNSAT. '
        'Thus the stored finite point dictionary is complete only inside S. Unite coefficient indices appearing together in each c. '
        'Every point lies wholly in one resulting component B. In C Y=W, rows split across components; each active point contributes a rank-one matrix to its block, '
        'so the number of active products in B is at least rank_F2(W_B). Summing gives a necessary support bound. '
        'All ten certificates give sum rank(W_B)=93 and the original source achieves93; hence exact old-S minimum93 without an additional support solver call. '
        'The lower bound for a partial dictionary would apply only to that dictionary; the old-S extension relies on the existing complete-census UNSAT. '
        'Every hyperplane ledger entry reconstructs its canonical92-row physical basis from exact parent-S coordinates, checks catalog H/model hashes, '
        'and checks exact source/parent canonical basis and target arrays. H is contained in that parent S, so parent minimum93 excludes a≤92 algorithm using only H points. '
        'All2707 entries are labeled IMPLIED_BY_PARENT. Existing direct solver records are retained separately; unvisited entries get no invented oracle result. '
        'The two deferred duplicate source models were never queried and retain that direct status. No queue or production artifact was modified.\n').encode())
    freeze(out/'audit.py',Path(__file__).read_bytes());save('manifest.json',dict(files={str(file.relative_to(out)):sha(file.read_bytes())for file in out.rglob('*')if file.is_file()}))
    for file in out.rglob('*'):
        if file.is_file():file.chmod(0o444)
    print(json_bytes(report).decode())


if __name__=='__main__':main()
