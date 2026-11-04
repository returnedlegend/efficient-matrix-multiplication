"""One exact three-parent seed crossover census; no heuristic UNSAT claim."""
import hashlib, itertools, json, os, pathlib, resource, sys, time
ROOT=pathlib.Path('/workspace/efficient-matrix-multiplication')
sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
from mmsearch.marathon7_cached_guard import CampaignGuard
from mmsearch.tensor_code7 import xor_columns
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts import campaign_native_baseline7 as safe
from scripts.campaign_native_plus_burst42 import encode_candidate

def main():
    os.sched_setaffinity(0,{1});resource.setrlimit(resource.RLIMIT_AS,(384*1024**2,384*1024**2))
    c=ROOT/'artifacts/marathon7_20261103T122417Z';out=c/'seed-crossover36-triples-002'
    guard=CampaignGuard(20,'2026-11-03T19:24:17Z',guard_state=c/'operations-v3/state.json',campaign_dir=c)
    guard.check('pre_crossover');poller=CancelPoller(guard);started=time.monotonic();cpu=time.process_time()
    raw=(c/'tensor-code-native-corpus-prep-001/prepared.json').read_bytes()
    source_sha=hashlib.sha256(raw).hexdigest()
    if source_sha!='2302ae5e82fe7afd1845dd50ffd5c12f17e1efb56b8f4adf1ed09bd31a71e886':raise ValueError('prepared source changed')
    # Planted linear-code crossover: three weight-three valid parents yield weight one.
    assert 0b0111 ^ 0b1011 ^ 0b1101 == 1
    assert min((a^b^d).bit_count() for a,b,d in itertools.combinations([7,11,13],3))==1
    p=json.loads(raw);columns=[int(x,16) for x in p['columns_hex']];target=int(p['target_hex'],16)
    seeds=[int(x,16) for x in p['seed_states_hex']]
    if len(seeds)!=36 or any(xor_columns(columns,x)!=target or x.bit_count()!=w for x,w in zip(seeds,p['seed_weights'])):raise ValueError('seed tensor/weight binding differs')
    out.mkdir();hist={};seen=set();best=10000;best_parents=None;attempted=0;record=False
    def fresh(barrier):
        try:guard.check(barrier);return True
        except Exception:return False
    for parents in itertools.combinations(range(36),3):
        
        if poller.cancelled():guard.check('crossover_cancelled')
        a,b,d=parents;state=seeds[a]^seeds[b]^seeds[d]
        # Full packed coefficient identity checks every one of the 15,625 entries.
        if xor_columns(columns,state)!=target:raise ValueError('crossover syndrome differs')
        attempted+=1;seen.add(state);weight=state.bit_count();hist[weight]=hist.get(weight,0)+1
        if weight<best:best=weight;best_parents=parents
        if weight<=92:
            atoms=[p['atoms'][i] for i in range(522) if (state>>i)&1]
            candidate=encode_candidate(atoms,5,method='exact-three-parent-crossover',parents=list(parents),prepared_sha256=source_sha)
            record=safe.retain_target(out,candidate,fresh,target=92)
            break
    guard.check('post_crossover')
    result={'status':'TARGET_EMITTED_TO_GLOBAL_GUARD' if record else 'FINITE_TRIPLE_CENSUS_COMPLETE' if attempted==7140 else 'UNKNOWN','source_prepared_sha256':source_sha,'code_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'seed_count':36,'seed_weights':p['seed_weights'],'attempted_triples':attempted,'distinct_masks':len(seen),'minimum_support_count':best,'best_parent_indices':best_parents,'support_count_histogram':hist,'full_coefficients_per_crossover':15625,'record_emitted':record,'elapsed_seconds':time.monotonic()-started,'cpu_seconds':time.process_time()-cpu,'guard':guard.observation(),'scope':'Only XOR of three distinct members of this frozen 36-seed corpus; no global nonexistence or novelty claim.'}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['guard','support_count_histogram','seed_weights']}))

if __name__=='__main__':main()
