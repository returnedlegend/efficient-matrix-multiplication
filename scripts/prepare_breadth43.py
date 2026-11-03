"""Prepare four diverse fresh fixed-pair baselines; never run target queries."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from mmsearch.breadth43 import factor_histogram,map_source,select_farthest
from mmsearch.free_factor_sat import build_system,decode_vectors
from mmsearch.observed_plane42 import active_certificate,plane_plan
from mmsearch.recombine import canonical_terms,digest
from mmsearch.verify import verify_candidate
from scripts.campaign_breadth43 import SOURCE_FILES


def frozen_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
    path.chmod(0o444)


def tested_inventory(coverage_root,master):
    references={};evidence=[];system_hashes={}
    for path in sorted(Path(coverage_root).rglob('config.json')):
        report_path=path.parent/'result.json'
        if not report_path.exists():continue
        config=json.loads(path.read_text())
        if not {'prepared_dir','case','max_deltas'}<=set(config):continue
        report=json.loads(report_path.read_text())
        if not report.get('target_queries',0):continue
        prepared=Path(config['prepared_dir']);system_path=prepared/'cases'/config['case']/'system.json'
        if hashlib.sha256((prepared/'integrity.json').read_bytes()).hexdigest()!=config['prepared_integrity_sha256']:
            raise AssertionError('tested common source preparation changed')
        system=json.loads(system_path.read_text());candidate=decode_vectors(system,system['baseline_vectors'])
        mapped=map_source(master,candidate)
        if mapped['status']!='ELIGIBLE':raise AssertionError('tested reference cannot be mapped as exact rank93 in master family')
        mapped.update(label=config['case'],source_system=system,source_system_path=str(system_path))
        references.setdefault(mapped['model_sha256'],mapped);system_hashes[digest(system)]=mapped['model_sha256']
        evidence.append(dict(stage='common',model_sha256=mapped['model_sha256'],term_hash=mapped['term_hash'],
            config_path=str(path),config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            report_path=str(report_path),report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
            status=report['status'],target_queries=report['target_queries']))
    for path in sorted(Path(coverage_root).rglob('config.json')):
        config=json.loads(path.read_text())
        if not {'source_system_sha256','full_plan_sha256','controls_only'}<=set(config) or config['controls_only']:continue
        reports=[p for p in path.parent.glob('report-launch*.json') if json.loads(p.read_text()).get('target_decoder_calls_this_launch',0)]
        if not reports:continue
        if config['source_system_sha256'] not in system_hashes:
            raise AssertionError('a tested plane-only model lacks a resolved common reference; do not silently omit it')
        model_hash=system_hashes[config['source_system_sha256']]
        evidence.append(dict(stage='plane',model_sha256=model_hash,config_path=str(path),
            config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            reports=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                status=json.loads(p.read_text())['status']) for p in reports]))
    if not references:raise ValueError('no actual target-tested pipeline reference models found')
    return list(references.values()),evidence


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dictionary',type=Path,required=True)
    parser.add_argument('--template-system',type=Path,required=True)
    parser.add_argument('--candidate-dir',type=Path,action='append',required=True)
    parser.add_argument('--holdout-manifest',type=Path,required=True)
    parser.add_argument('--coverage-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv);started=time.process_time();root=args.output_dir;root.mkdir(parents=True,exist_ok=False)
    master=json.loads(args.template_system.read_text());dictionary=json.loads(args.dictionary.read_text())
    hold_manifest=json.loads(args.holdout_manifest.read_text());heldout=set(hold_manifest['v43_source_split']['heldout'])
    if len(heldout)!=4 or heldout!=set(hold_manifest['declaration']['partition']['heldout']):
        raise AssertionError('V43 heldout source declaration is inconsistent')
    tested,evidence=tested_inventory(args.coverage_root,master)
    tested_terms={item['term_hash'] for item in tested};tested_models={item['model_sha256'] for item in tested}
    frozen_json(root/'tested-coverage.json',dict(scope='Actual common/observed-plane target-tested models only; unrelated native-search use does not transfer pipeline negatives',
        evidence=evidence,references=[{k:v for k,v in item.items() if k not in ['source_system','vectors']} for item in tested]))
    (root/'inputs').mkdir();(root/'inputs/v43-manifest.json').write_bytes(args.holdout_manifest.read_bytes());(root/'inputs/dictionary.json').write_bytes(args.dictionary.read_bytes())
    frozen_json(root/'holdout-exclusion.json',dict(heldout_source_term_hashes=sorted(heldout),
        source_manifest_sha256=hashlib.sha256(args.holdout_manifest.read_bytes()).hexdigest(),
        source_hash_definition='SHA256(compact JSON sorted canonical term triples), matching V43 term_hash',
        policy='Only source split identities are used; heldout task outcomes are not selection features'))
    for item in tested:frozen_json(root/'tested'/f'{item["model_sha256"]}.system.json',item['source_system'])
    records=[];eligible=[];seen_models=set()
    for path in sorted({p for directory in args.candidate_dir for p in directory.glob('*.json')}):
        raw=path.read_bytes();candidate=json.loads(raw);record=map_source(master,candidate,heldout,tested_terms,tested_models)
        record.update(source_path=str(path.resolve()),source_sha256=hashlib.sha256(raw).hexdigest())
        if record['status']=='ELIGIBLE':
            verification=verify_candidate(candidate,random_trials=0)
            if not verification['valid'] or verification['rank']!=93 or verification['exact_entries_checked']!=15625:
                raise AssertionError(f'candidate is not independently exact rank93: {path}')
            record['source_verification']=verification
            if record['model_sha256'] in seen_models:record['status']='DUPLICATE_CORPUS_MODEL'
            else:
                seen_models.add(record['model_sha256']);eligible.append(dict(record,candidate=candidate))
        records.append({k:v for k,v in record.items() if k!='vectors'})
    selected,trace=select_farthest(eligible,tested,4)
    frozen_json(root/'corpus-inventory.json',dict(counts=Counter(item['status'] for item in records),records=records))
    frozen_json(root/'selection-trace.json',trace)
    selected_records=[]
    for index,(item,step) in enumerate(zip(selected,trace)):
        label=f'b{index:02d}-{item["term_hash"][:12]}'
        source=Path(item['source_path']);target=root/'sources'/source.name;target.parent.mkdir(exist_ok=True)
        target.write_bytes(source.read_bytes());target.chmod(0o444)
        system=build_system(dictionary,5,'wu',item['candidate'])
        if system['pairs']!=tuple(tuple(p) for p in master['pairs']) or system['coefficients']!=master['coefficients'] or system['right_sides']!=master['right_sides']:
            raise AssertionError('selected baseline changed the complete P1553 family')
        if digest(system['baseline_vectors'])!=item['model_sha256']:raise AssertionError('selected model mapping changed')
        verification=verify_candidate(decode_vectors(system,system['baseline_vectors']),random_trials=0)
        if not verification['valid'] or verification['rank']!=93 or verification['exact_entries_checked']!=15625:
            raise AssertionError('independent mapped source verification failed')
        certificate=active_certificate(system);counts=Counter(v for v in system['baseline_vectors'] if v)
        common_plan=[dict(delta=d,delta_hex=hex(d),k=k,weight_bound=k-1) for d,k in sorted(counts.items(),key=lambda row:(-row[1],row[0]))]
        planes=plane_plan(system);plane_hist=Counter(p['k'] for p in planes)
        for stage,plan in [('common',common_plan),('plane',planes)]:
            case=root/stage/'cases'/label
            frozen_json(case/'system.json',system);frozen_json(case/'plan.json',plan)
            if stage=='plane':frozen_json(case/'active-certificate.json',certificate)
        scope=dict(common='All observed single deltas, exact through weight4; any required bound>4 remains partial.',
            plane='All observed distinct two-dimensional spans, exact through groupweight3; larger required bounds remain partial for a later root phase.',
            fixed_pairs=1553,field=2,negative_transfer='None except exact duplicate model exclusion before selection.',novelty_claim=False)
        description=dict(case=label,term_hash=item['term_hash'],model_sha256=item['model_sha256'],
            source_path=item['source_path'],source_sha256=item['source_sha256'],source_verification=verification,
            factor_rank_histogram=item['factor_rank_histogram'],selection_step=step['step'],
            minimum_difference_rank=step['minimum_difference_rank'],minimum_histogram_l1=step['minimum_histogram_l1'],
            active_column_rank=certificate['rank'],active_columns_independent=certificate['independent'],
            delta_count=len(common_plan),delta_k_histogram=Counter(counts.values()),maximum_delta_k=max(counts.values()),
            common_required_weight_above4=[p for p in common_plan if p['weight_bound']>4],
            plane_count=len(planes),plane_k_histogram=plane_hist,maximum_plane_k=max(plane_hist),
            plane_required_weight_above3=[dict(index=i,plane=p['plane'],k=p['k'],weight_bound=p['weight_bound'])
                for i,p in enumerate(planes) if p['weight_bound']>3],scope=scope)
        selected_records.append(description)
    frozen_json(root/'selected.json',selected_records)
    source_files=sorted(set(SOURCE_FILES+['scripts/prepare_breadth43.py']))
    for name in source_files:
        path=root/'code'/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((REPO/name).read_bytes());path.chmod(0o444)
    for name in ['mmsearch/tensor.py','tests/test_breadth43.py']:
        path=root/'code'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((REPO/name).read_bytes());path.chmod(0o444)
    for stage in ['common','plane']:
        directory=root/stage
        frozen_json(directory/'integrity.json',{str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob('*')) if p.is_file()})
    for item in selected_records:
        command=['nice','-n','10',sys.executable,str(root.resolve()/'code/scripts/campaign_breadth43.py'),
            '--prepared-dir',str(root.resolve()),'--case',item['case'],'--output-dir',str(root.resolve().parent/f'breadth43-{item["case"]}'),
            '--seconds','900','--common-seconds','240','--per-query-seconds','5','--deadline-utc','2026-11-04T21:31:16Z']
        frozen_json(root/'jobs'/f'{item["case"]}.json',dict(id=f'breadth43-{item["case"]}',enabled=False,cpu=1,
            memory_mb=1024,seconds=915,command=command,note='Fresh distinct model: common delta then plane<=3. Larger-bound gaps remain explicit. Root owns queue. No target query during preparation.'))
    frozen_json(root/'preparation.json',dict(status='PREPARED_NO_TARGET_QUERY',source_files=source_files,
        selected_cases=[item['case'] for item in selected_records],cpu_seconds=time.process_time()-started,
        corpus_status_counts=Counter(item['status'] for item in records),target_queries=0,
        source_parameters={k:str(v) if not isinstance(v,list) else [str(p) for p in v] for k,v in vars(args).items()}))
    frozen_json(root/'integrity.json',{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts})
    for p in root.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:p.chmod(0o444)
    print(json.dumps(dict(status='PREPARED_NO_TARGET_QUERY',selected=[item['case'] for item in selected_records],
        cpu_seconds=time.process_time()-started)),flush=True)


if __name__=='__main__':raise SystemExit(main())
