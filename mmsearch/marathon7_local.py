"""Marathon7 lazy CP(d+1) rank-two-edge metadata and strict barriers."""
from datetime import datetime,timezone
import json
from pathlib import Path
from .extend_eight_bulk43 import (SourceCache,indices,checked_path,read,sha,raw,
    ensure_room,restore_journal,commit_journal)
from .local_guard43 import CampaignGuard as OriginalGuard,CampaignHold
from .recombine import digest

DEADLINE='2026-11-03T19:24:17Z'
HARD_DEADLINE=datetime.fromisoformat(DEADLINE.replace('Z','+00:00')).timestamp()


class CampaignGuard(OriginalGuard):
    """Reject malformed external state, zombie guards, and cutoff extensions."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.deadline=min(self.deadline,HARD_DEADLINE)
        self.deadline_utc=datetime.fromtimestamp(self.deadline,timezone.utc).isoformat()
        self._typed_checked=-float('inf')

    def reason(self,force=False):
        # Validate before V1 accesses .get() on canonical objects.
        if not force and self.monotonic()-self._typed_checked<.1:return super().reason(force)
        self._typed_checked=self.monotonic()
        try:
            if self.campaign_dir:
                for path in [self.campaign_dir/'queue_state.json',self.campaign_dir/'operations-v3/state.json']:
                    if path.exists() and type(json.loads(path.read_bytes())) is not dict:return 'invalid canonical state type'
            if self.resources:
                state=json.loads(self.resources.path.read_bytes())
                if type(state) is not dict:return 'invalid resource state type'
                stamp=state['updated_utc'];identity=state['process_identity']
                if type(stamp) is not str or type(identity) is not dict:return 'invalid resource identity type'
                updated=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                if updated.tzinfo is None:return 'resource timestamp requires timezone'
                if any(type(value) is not int or value<=0 for value in [state['pid'],identity['start_ticks']]):return 'invalid resource pid/start ticks'
                storage=state['campaign_allocated_bytes']
                if type(storage) is not int or storage<0:return 'invalid resource storage type/value'
                tail=Path('/proc',str(state['pid']),'stat').read_text().rsplit(')',1)[1].split()
                if tail[0] in ('Z','X'):return 'resource process no longer live'
        except (OSError,ValueError,KeyError,TypeError,AttributeError):return 'resource/canonical state unavailable or invalid'
        return super().reason(force)


def select_plan(bundle,chunk_id=None,max_cases=0,small_control=False):
    bundle=Path(bundle);plan=read(bundle/('small-plan.json' if small_control else 'plan.json'))
    if small_control or 'chunks' not in plan:
        cases=plan['cases'];identity='small-control' if small_control else 'static-fixture'
        family=dict(max_vectors=65535)
    else:
        chunk=next((c for c in plan['chunks'] if c['id']==chunk_id),None)
        if chunk is None:raise ValueError('select an explicit frozen chunk')
        compressed=checked_path(bundle,chunk['catalog']).read_bytes()
        if sha(compressed)!=chunk['catalog_sha256']:raise ValueError('chunk catalog changed')
        import gzip
        rows=json.loads(gzip.decompress(compressed))
        if len(rows)!=chunk['count'] or digest(rows)!=chunk['rows_sha256']:raise ValueError('chunk row binding changed')
        family=plan['family'];cases=[]
        if (family['local_products'],family['target_products'],family['mode_rank']) not in ((10,9,8),(8,7,6)):raise ValueError('unsupported reviewed family')
        for row in rows:
            if len(row)!=9:raise ValueError('invalid row schema')
            s,lo,hi,*rest=row;shape=rest[:3];axis,points,ordinal=rest[3:];ids=indices(lo,hi)
            if type(s) is not int or str(s) not in plan['sources'] or axis not in (0,1,2) or any(type(v) is not int or not 0<v<=family['mode_rank'] for v in shape):raise ValueError('invalid source/axis/shape')
            other=[j for j in range(3) if j!=axis]
            if len(ids)!=family['local_products'] or shape[axis]!=family['mode_rank'] or points!=((1<<shape[other[0]])-1)*((1<<shape[other[1]])-1):raise ValueError('catalog outside reviewed residual scope')
            cases.append(dict(id=f's{s}-{hi:08x}{lo:016x}',source=f'source-{s}.json',source_id=s,source_sha256=plan['sources'][str(s)]['sha256'],
                mask_lo=lo,mask_hi=hi,source_indices=ids,shape=shape,free_axis=axis,mode_rank=family['mode_rank'],all_pair_points=points,catalog_ordinal=ordinal,
                source_products=93,source_local_products=family['local_products'],target_local_products=family['target_products']))
        identity=chunk_id
    if type(max_cases) is not int or max_cases<0:raise ValueError('nonnegative prefix required')
    if max_cases:cases=cases[:max_cases]
    if not cases:raise ValueError('empty selected scope')
    return dict(cases=cases,identity=identity,family=family,selected_sha256=digest(cases),catalog_plan_sha256=digest(plan))


def compact_negative(result):
    if result.get('status')!='LOCAL_UNSAT' or result.get('complete') is not True:raise ValueError('incomplete result cannot close a case')
    value=dict(result);buckets=value.pop('bucket_span_ranks',None);d=result['target_rank']
    if 'matrix_rank_classes' in result:
        classes=result['matrix_rank_classes'];count=(1<<d)-1
        if sum(classes.values())!=count or result['enumerated_vectors']!=count or result['span_vectors']!=count:raise ValueError('incomplete image enumeration census')
        if result['unordered_rank2_splits']!=3*classes['rank2'] and result['budget']==d+1:raise ValueError('rank-two split census differs')
    if buckets is not None:
        if len(buckets)!=result['nonzero_edge_cosets'] or len({r[0] for r in buckets})!=len(buckets):raise ValueError('edge bucket count differs')
        if any(not r or n<1 or not 0<=rank<d for r,n,rank in buckets) or result['inside_rank']>=d:raise ValueError('invalid exact edge negative ranks')
        value.update(bucket_span_ranks_sha256=digest(buckets),bucket_count=len(buckets),bucket_span_max=max((r[2] for r in buckets),default=result['inside_rank']))
    value.update(algorithm_case=result.get('case'),raw_decoder_result_sha256=digest(result),negative_storage='Compact exact statistics/hash; replay frozen source+mask through frozen rank2-edge backend for full buckets.')
    return value


def verify_winner_resume(out,config_sha,cases,verify_bytes):
    """Existing markers require the same durable immutable proof as publication."""
    out=Path(out).resolve();proof=read(out/'WINNER.proof.json')
    expected={'WINNER.verification.json','WINNER.independent.verification.json','WINNER.core-certificate.json'}
    if set(proof['files'])!=expected:raise ValueError('winner proof view registry changed')
    candidate=(out/'WINNER.json').read_bytes()
    if sha(candidate)!=proof['candidate_sha256']:raise ValueError('winner marker differs from bound candidate')
    directory=checked_path(out,proof['proof_directory'])
    if not directory.is_relative_to(out/'proofs') or not directory.is_dir():raise ValueError('winner immutable proof directory invalid')
    if (directory/'candidate.json').read_bytes()!=candidate:raise ValueError('winner differs from immutable proof candidate')
    for name in expected:
        content=(out/name).read_bytes()
        if sha(content)!=proof['files'][name]:raise ValueError('winner proof view checksum mismatch')
        original={'WINNER.verification.json':'verification.json','WINNER.independent.verification.json':'independent.json','WINNER.core-certificate.json':'core-certificate.json'}[name]
        if (directory/original).read_bytes()!=content:raise ValueError('winner proof view differs from immutable original')
    certificate=read(directory/'core-certificate.json');data=read(directory/'input-core.json')
    if certificate['config_sha256']!=config_sha or certificate['case'] not in {case['id'] for case in cases}:raise ValueError('winner certificate differs from selected configuration/case')
    if sha(raw(data))!=certificate['core_input_sha256'] or digest(dict(shape=data['shape'],core=data['core']))!=certificate['core_math_sha256']:raise ValueError('winner immutable core checksum mismatch')
    checked=verify_bytes(candidate)
    if not checked['record_eligible']:raise ValueError('corrupt prior winner')
    return checked
