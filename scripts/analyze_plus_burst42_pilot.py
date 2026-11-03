"""Read-only audit of completed matched dwell pilots; never starts native work."""
from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, sys, time
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.campaign_native_plus_burst42 import read, raw_json, source_identity, validate_stats
from scripts.verify_record42_independent import verify_bytes
from mmsearch.native_bridge import canonical_terms,term_set_sha256

def sha(raw):return hashlib.sha256(raw).hexdigest()
def rank(rows):
    basis={}
    for x in rows:
        while x:
            p=x.bit_length()-1
            if p not in basis:basis[p]=x;break
            x^=basis[p]
    return len(basis)
def matrix_rank(x):return rank((x>>(i*5))&31 for i in range(5))
def structure(terms):
    hist=collections.Counter('/'.join(str(matrix_rank(x)) for x in t) for t in terms)
    spans=[rank(t[i] for t in terms) for i in range(3)]
    pair_counts=[];merged=[]
    for a,b,c in [(0,1,2),(1,2,0),(2,0,1)]:
        pairs={}
        for t in terms:pairs[t[a],t[b]]=pairs.get((t[a],t[b]),0)^t[c]
        pair_counts.append(len(pairs));merged.append(sum(bool(v) for v in pairs.values()))
    return dict(joint_factor_rank_histogram=dict(sorted(hist.items())),factor_span_ranks=spans,
                fixed_pair_group_counts_uv_vw_wu=pair_counts,merged_active_counts_uv_vw_wu=merged)

def audit(campaign,arm,offset=0,count=32):
    start=time.process_time();out=campaign/arm['job_id'];summary,sraw=read(out/'summary.json');manifest,mraw=read(out/'manifest.json')
    result,rraw=read(campaign/(arm['job_id']+'-job.result.json'));queue,qraw=read(campaign/'queue.json')
    jobs=[j for j in queue['jobs'] if j['id']==arm['job_id']]
    assert len(jobs)==1 and set(jobs[0])=={'id','cpu','memory_mb','seconds','enabled','command'}
    job=jobs[0];assert result['command']==job['command'] and result['exit_code']==0 and not result['timed_out'] and not result['interrupted']
    assert manifest['source']['raw_sha256']==arm['input_sha256']==sha((out/'input.json').read_bytes())
    assert manifest['seed']==arm['paired_seed'] and manifest['reduction_dwell']==arm['reduction_dwell']
    assert manifest['binary_sha256']==sha((out/'frozen/native-worker').read_bytes())
    for name,digest in manifest['runtime_code_sha256'].items():assert sha((out/'frozen/runtime'/name).read_bytes())==digest
    assert sha(raw_json(manifest['runtime_code_sha256']))==manifest['runtime_sha256']
    stats,digest=validate_stats(out/'native/walk.stats.json',seed=arm['paired_seed'],dwell=arm['reduction_dwell'],plus_burst=arm['plus_burst'])
    assert digest==summary['stats_sha256'] and summary['stats']==stats
    assert summary['winner'] is False and stats['best_rank']==stats['current_rank']==93 and not (out/'WINNER.json').exists()
    source=canonical_terms(json.loads((out/'input.json').read_bytes()));source_struct=structure(source)
    certificates={};histograms=collections.Counter();span_counts=collections.Counter();merged_counts=collections.Counter()
    selected=list(summary['exported_diversity']['certificates'].items())[offset:offset+count]
    for identity,item in selected:
        path=pathlib.Path(item['path']);assert path.parent==out/'verified'
        raw=path.read_bytes();assert sha(raw)==item['sha256']
        report=verify_bytes(raw);assert report['valid'] and report['exact_entries_checked']==15625 and report['essential_rank']==item['rank'] and not report['record_eligible']
        terms=canonical_terms(json.loads(raw));assert term_set_sha256(terms)==identity and len(terms)==item['rank']
        st=structure(terms);hkey=json.dumps(st['joint_factor_rank_histogram'],sort_keys=True,separators=(',',':'));histograms[hkey]+=1
        span_counts[str(st['factor_span_ranks'])]+=1;merged_counts[str(st['merged_active_counts_uv_vw_wu'])]+=1
        l1=sum(abs(st['joint_factor_rank_histogram'].get(k,0)-source_struct['joint_factor_rank_histogram'].get(k,0)) for k in set(st['joint_factor_rank_histogram'])|set(source_struct['joint_factor_rank_histogram']))
        certificates[identity]=dict(raw_sha256=sha(raw),canonical_source_identity=source_identity(terms),histogram_l1_from_input=l1,**st)
    assert len(certificates)==len(selected)
    return dict(job_id=arm['job_id'],source=arm['source'],seed=arm['paired_seed'],dwell=arm['reduction_dwell'],plus_burst=arm['plus_burst'],
        hashes=dict(summary_sha256=sha(sraw),manifest_sha256=sha(mraw),job_result_sha256=sha(rraw),queue_snapshot_sha256=sha(qraw),
                    job_spec_sha256=sha(raw_json(job)),input_sha256=arm['input_sha256'],binary_sha256=manifest['binary_sha256'],runtime_sha256=manifest['runtime_sha256'],stats_sha256=digest),
        status=summary['status'],best_rank=stats['best_rank'],current_rank=stats['current_rank'],winner=False,execution=summary['execution'],job_result=result,
        steps_per_measured_child_cpu_second=stats['steps']/summary['execution']['child_cpu_seconds'],
        above_best_fraction=1-stats['rank_excess_residency_steps'].get('0',0)/stats['steps'],
        stats=stats,exported_diversity={k:v for k,v in summary['exported_diversity'].items() if k!='certificates'},
        exported_states_per_archive_addition=len(certificates)/stats['archive_additions'],source_structure=source_struct,
        distinct_joint_factor_rank_histograms=len(histograms),joint_factor_rank_histogram_counts=dict(histograms),
        factor_span_counts=dict(span_counts),merged_active_counts=dict(merged_counts),certificates=certificates,
        offset=offset,count=count,total_certificates=summary['exported_diversity']['unique_certificates'],
        independent_reverified_certificates=len(certificates),independent_entries_checked=15625*len(certificates),audit_cpu_seconds=time.process_time()-start)

def main():
    p=argparse.ArgumentParser();p.add_argument('--campaign',type=pathlib.Path,required=True);p.add_argument('--job-id',required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--offset',type=int,default=0);p.add_argument('--count',type=int,default=32);a=p.parse_args()
    campaign=a.campaign.resolve();plan,_=read(campaign/'plus-burst42-pilot-ready-v1/plan.json');arm=next(x for x in plan['arms'] if x['job_id']==a.job_id)
    report=audit(campaign,arm,a.offset,a.count);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as f:f.write(raw_json(report))
    print(json.dumps({k:report[k] for k in ['job_id','best_rank','steps_per_measured_child_cpu_second','above_best_fraction','independent_reverified_certificates','distinct_joint_factor_rank_histograms','factor_span_counts','merged_active_counts','audit_cpu_seconds']},sort_keys=True))
if __name__=='__main__':main()
