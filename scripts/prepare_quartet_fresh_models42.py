"""Audit frontier exports and freeze up to4 distinct fresh raw93 W cases."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.free_factor_kernel import decode_checked
from mmsearch.free_factor_kernel_wide import native_input
from mmsearch.free_factor_sat import build_system
from mmsearch.kernel_quartet_frontier import fingerprint,model_bytes,matrix_rank
from mmsearch.search import decode_candidate
from mmsearch.verify import verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-frontier',type=Path,required=True);p.add_argument('--catalog',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--max-models',type=int,default=4)
    args=p.parse_args();source=args.source_frontier.resolve();out=args.output_dir.resolve()
    if not 1<=args.max_models<=4:p.error('fresh-model cap4 exceeded')
    original=read_json((source/'system.json').read_bytes());old_vectors=original['baseline_vectors'];old_sha=sha(model_bytes(old_vectors))
    source_summary=read_json((source/'summary.json').read_bytes())
    raw_native=(source/'native_frontier.txt').read_bytes()
    if sha(raw_native)!=source_summary['native_frontier_sha256'] or source_summary['source_model_sha256']!=old_sha:
        raise ValueError('source frontier model/archive binding mismatch')
    native_counts=Counter(int(line.split()[10]) for line in raw_native.decode().splitlines()[1:])
    records=read_json((source/'frontier-index.json').read_bytes());pairs=original['pairs'];pair_ids={tuple(pair):i for i,pair in enumerate(pairs)}
    permutation=original['metadata']['mode_permutation'];orientation=original['metadata']['orientation']
    audit=[];eligible=[]
    def inspect(candidate):
        report=verify_candidate(candidate,random_trials=0)
        if not report['valid'] or report['exact_entries_checked']!=15625:raise ValueError('source export failed full tensor audit')
        terms=list(decode_candidate(candidate,5));hist=Counter(tuple(matrix_rank(mask,5) for mask in term) for term in terms)
        included=all((term[permutation[0]],term[permutation[1]]) in pair_ids for term in terms)
        vectors=[0]*len(pairs) if included else None
        if included:
            for term in terms:vectors[pair_ids[term[permutation[0]],term[permutation[1]]]]^=term[permutation[2]]
        return report,{'/'.join(map(str,key)):value for key,value in sorted(hist.items())},vectors
    for record in records:
        raw_path=Path(record['path']);raw_bytes=raw_path.read_bytes();candidate=read_json(raw_bytes)
        compressed_path=raw_path.with_name(raw_path.stem+'.compressed.json');compressed_bytes=compressed_path.read_bytes()
        raw_report,raw_hist,raw_vectors=inspect(candidate);compressed_report,compressed_hist,compressed_vectors=inspect(read_json(compressed_bytes))
        if raw_report['rank']!=record['rank'] or compressed_report['rank']!=record['compressed_rank'] or raw_hist!=record['factor_rank_histogram'] or compressed_hist!=record['compressed_factor_rank_histogram']:
            raise ValueError('source rank/histogram differs from fresh audit')
        raw_sha=sha(model_bytes(raw_vectors)) if raw_vectors is not None else None
        compressed_sha=sha(model_bytes(compressed_vectors)) if compressed_vectors is not None else None
        item=dict(raw_rank=raw_report['rank'],compressed_rank=compressed_report['rank'],raw_model_sha256=raw_sha,
            compressed_model_sha256=compressed_sha,raw_fixed_pair_inclusion=raw_vectors is not None,
            compressed_fixed_pair_inclusion=compressed_vectors is not None,compressed_is_original_model=compressed_sha==old_sha,
            raw_histogram=raw_hist,compressed_histogram=compressed_hist,source_path=str(raw_path),
            source_certificate_sha256=sha(raw_bytes),source_compressed_certificate_sha256=sha(compressed_bytes))
        audit.append(item)
        if raw_report['rank']==93 and raw_vectors is not None and raw_sha!=old_sha:
            if raw_sha!=record['model_sha256']:raise ValueError('raw export model hash mismatch')
            eligible.append(dict(candidate=candidate,raw_bytes=raw_bytes,vectors=raw_vectors,model_sha256=raw_sha,
                                 histogram=raw_hist,source_record=record,audit=item))
    distinct={item['model_sha256']:item for item in eligible};eligible=sorted(distinct.values(),key=lambda item:item['model_sha256'])
    selected=[]
    while eligible and len(selected)<args.max_models:
        def diversity(item):
            hist=item['histogram'];support=sum(1<<i for i,w in enumerate(item['vectors']) if w)
            hist_distance=min((sum(abs(hist.get(k,0)-other['histogram'].get(k,0)) for k in set(hist)|set(other['histogram'])) for other in selected),default=0)
            active_distance=min(((support^sum(1<<i for i,w in enumerate(other['vectors']) if w)).bit_count() for other in selected),default=0)
            return hist_distance,active_distance
        best=max(eligible,key=diversity);eligible.remove(best);selected.append(best)
    out.mkdir(parents=True,exist_ok=False)
    for name in ('dictionary','circuits'):
        freeze(out/'inputs'/(name+'.json'),(source/'inputs'/(name+'.json')).read_bytes())
    freeze(out/'quartets.txt',args.catalog.read_bytes())
    for name in ('summary.json','frontier-index.json','manifest.json'):
        freeze(out/'source'/name,(source/name).read_bytes())
    freeze(out/'source/native_frontier.txt',raw_native)
    code_hashes={}
    for directory in ('mmsearch','scripts'):
        for path in sorted((ROOT/directory).rglob('*.py')):
            name=str(path.relative_to(ROOT));raw=path.read_bytes();freeze(out/'code'/name,raw);code_hashes[name]=sha(raw)
    old=ROOT/'artifacts/rl_campaign42_20261103T033116Z/quartet-block-ready-v1'
    for name in ('native/free_factor_quartet_block_worker_wide.cpp','native/kernel_quartet_optimizer.hpp'):
        raw=(old/'code'/name).read_bytes();freeze(out/'code'/name,raw);code_hashes[name]=sha(raw)
    freeze(out/'native-worker',(old/'native-worker').read_bytes());(out/'native-worker').chmod(0o555)
    freeze(out/'launch-closure.json',json_bytes(code_hashes));cases=[]
    dictionary=read_json((out/'inputs/dictionary.json').read_bytes());circuits=read_json((out/'inputs/circuits.json').read_bytes())
    for number,item in enumerate(selected):
        case_id=f'case-{number:02d}-{item["model_sha256"][:12]}';directory=out/'cases'/case_id
        system=build_system(dictionary,5,orientation,item['candidate'])
        if [list(pair) for pair in system['pairs']]!=pairs or system['baseline_vectors']!=item['vectors']:raise ValueError('fresh case changed fixed-pair indexing')
        _,report=decode_checked(system,system['baseline_vectors'])
        if report['rank']!=93 or report['exact_entries_checked']!=15625:raise ValueError('fresh case is not verified93')
        raw_input=native_input(system,circuits)
        freeze(directory/'baseline.json',item['raw_bytes']);freeze(directory/'baseline.w.txt',model_bytes(item['vectors']))
        freeze(directory/'kernel_input.txt',raw_input);freeze(directory/'verification.json',json_bytes(report))
        changes=[dict(group=i,before=old_vectors[i],after=w) for i,w in enumerate(item['vectors']) if w!=old_vectors[i]]
        case=dict(id=case_id,baseline=str((directory/'baseline.json').relative_to(out)),model_sha256=item['model_sha256'],
            input_sha256=sha(raw_input),factor_rank_histogram=fingerprint(system,item['vectors']),changes=changes,
            source_export=item['source_record']['path'],fixed_pair_inclusion=True,pair_order_unchanged=True,
            initial_completed_rows=0,inherited_old_model_exclusions=False)
        freeze(directory/'case.json',json_bytes(case));cases.append(case)
    freeze(out/'EXPORT-AUDIT.json',json_bytes(dict(native_shortlist_rank_counts=dict(native_counts),
        verified_export_count=len(records),raw_rank_counts=dict(Counter(item['raw_rank'] for item in audit)),
        compressed_rank_counts=dict(Counter(item['compressed_rank'] for item in audit)),
        raw93_new_models=len(distinct),compressed93_collapses_to_original=sum(item['compressed_rank']==93 and item['compressed_is_original_model'] for item in audit),
        unexported_native_candidates_compression_untested=source_summary['unexported_shortlist_compression_untested'],exports=audit)))
    files={str(path.relative_to(out)):sha(path.read_bytes()) for path in sorted(out.rglob('*')) if path.is_file()}
    plan=dict(cases=cases,dictionary='inputs/dictionary.json',circuits='inputs/circuits.json',catalog='quartets.txt',binary='native-worker',
        launcher='code/scripts/campaign_kernel_quartet_block_wide.py',orientation=orientation,files=files,
        original_model_sha256=old_sha,catalog_sha256=sha((out/'quartets.txt').read_bytes()),binary_sha256=sha((out/'native-worker').read_bytes()),
        source_frontier=str(source),fresh_coverage_each_case=True,no_old_model_exclusions=True)
    freeze(out/'batch.json',json_bytes(plan))
    if cases:
        command=[sys.executable,'-B',str(out/'code/scripts/verify_quartet_fresh_batch42_ready.py'),'--bundle',str(out)]
        done=subprocess.run(command,cwd='/tmp',capture_output=True,text=True,timeout=30)
        if done.returncode:raise ValueError(done.stderr)
        print(done.stdout)
    print(json.dumps(dict(status='PREPARED',cases=len(cases),outdir=str(out),distinct_factor_histograms=len({tuple(case['factor_rank_histogram'].items()) for case in cases}))))
    return 0


if __name__=='__main__':raise SystemExit(main())
