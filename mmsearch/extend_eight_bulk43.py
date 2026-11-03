"""Lazy compact-residual inputs and compact, source-bound completion journals."""
import gzip
import hashlib
import json
from pathlib import Path
from .compact_eight43 import factor_core,packed_tensor,expand_core
from .compact_coset43 import mode_slices
from .sat_neighborhoods import factor_masks,gf2_rank
from .verify import verify_candidate
from .recombine import digest
from .observed_rank3_lazy42 import chain_read,chain_append
from .local_guard43 import CampaignHold


def read(path):return json.loads(Path(path).read_text())
def raw(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def sha(raw_bytes):return hashlib.sha256(raw_bytes).hexdigest()
def checked_path(bundle,name):
    path=(Path(bundle)/name).resolve()
    if not path.is_relative_to(Path(bundle).resolve()):raise ValueError('input path outside frozen bundle')
    return path


def indices(lo,hi):
    if type(lo) is not int or type(hi) is not int or lo<0 or lo>>64 or hi<0 or hi>>29:raise ValueError('mask outside93source terms')
    mask=lo|(hi<<64)
    return [i for i in range(93) if mask>>i&1]


def select_plan(bundle,chunk_id=None,max_cases=0,small_control=False):
    bundle=Path(bundle);plan=read(bundle/('small-plan.json' if small_control else 'plan.json'))
    if small_control or 'catalog' not in plan:
        # Static tiny fixtures only; production bulk has an immutable catalog.
        cases=plan['cases'];identity='small-control' if small_control else 'static-fixture'
        family=dict(point_cap=3969)
    else:
        if chunk_id is None:raise ValueError('select an explicit frozen chunk')
        chunk=next((c for c in plan['chunks'] if c['id']==chunk_id),None)
        if chunk is None:raise ValueError('unknown chunk')
        compressed=checked_path(bundle,plan['catalog']).read_bytes()
        if sha(compressed)!=plan['catalog_sha256']:raise ValueError('compact catalog changed')
        catalog=json.loads(gzip.decompress(compressed));rows=catalog[chunk['start']:chunk['stop']]
        if len(rows)!=chunk['count'] or digest(rows)!=chunk['rows_sha256']:raise ValueError('selected catalog chunk changed')
        family=plan['family'];cases=[]
        for row in rows:
            s,lo,hi,*rest=row;shape=rest[:3];axis,points=rest[3:]
            ids=indices(lo,hi)
            if len(ids)!=family['local_products'] or max(shape)!=family['mode_rank'] or points>family['point_cap'] or shape[axis]!=family['mode_rank']:
                raise ValueError('catalog shape/support outside reviewed scope')
            source=plan['sources'][str(s)]
            cases.append(dict(id=f's{s}-{hi:08x}{lo:016x}',source=f'source-{s}.json',source_id=s,source_sha256=source['sha256'],
                mask_lo=lo,mask_hi=hi,source_indices=ids,shape=shape,free_axis=axis,mode_rank=family['mode_rank'],all_pair_points=points,
                source_products=family['source_products'],source_local_products=family['local_products'],target_local_products=family['target_products']))
        identity=chunk_id
    if type(max_cases) is not int or max_cases<0:raise ValueError('nonnegative selected prefix required')
    if max_cases:cases=cases[:max_cases]
    if not cases:raise ValueError('empty selected case scope')
    return dict(cases=cases,identity=identity,family=family,selected_sha256=digest(cases),catalog_plan_sha256=digest(plan))


class SourceCache:
    def __init__(self,bundle):self.bundle=Path(bundle);self.cache={}
    def load(self,case):
        name=case['source'];path=checked_path(self.bundle,name)
        if name not in self.cache:
            source=read(path);verified=verify_candidate(source,random_trials=0);terms=factor_masks(source)
            if not verified['valid'] or verified['rank']!=case['source_products'] or verified['exact_entries_checked']!=source['dimension']**6:raise ValueError('source full tensor validation failed')
            if source['dimension']==5:
                from .compact_eight43 import opposite_pair_ranks
                if opposite_pair_ranks(terms)!=[93]*3:raise ValueError('source factor/mode image equality precondition failed')
            self.cache[name]=(source,verified,terms,[packed_tensor(term,source['dimension']**2) for term in terms],sha(path.read_bytes()))
        source,verified,terms,tensors,source_sha=self.cache[name]
        if case.get('source_sha256',source_sha)!=source_sha or verified['rank']!=case['source_products']:raise ValueError('cached source/model binding changed')
        return source,verified,terms,tensors,source_sha
    def core(self,case):
        source,verified,terms,tensors,source_sha=self.load(case)
        if case.get('core'):
            data=read(checked_path(self.bundle,case['core']))
        else:
            ids=case['source_indices'];bases,core,shape=factor_core(terms,ids)
            data=dict(shape=shape,core=core,image_bases=bases,source_indices=ids,outside_indices=[i for i in range(len(terms)) if i not in ids])
        ids=data['source_indices']
        if len(ids)!=case['source_local_products'] or len(set(ids))!=len(ids) or any(not 0<=i<len(terms) for i in ids):raise ValueError('lazy source support invalid')
        if case.get('source_indices',ids)!=ids or case.get('shape',data['shape'])!=data['shape']:raise ValueError('lazy shape/support differs from catalog')
        ambient=0
        for i in ids:ambient^=tensors[i]
        if expand_core(data['core'],data['shape'],data['image_bases'],source['dimension']**2)!=ambient:raise ValueError('lazy core failed full ambient expansion')
        actual=[gf2_rank(mode_slices(data['core'],data['shape'],axis)[0]) for axis in range(3)]
        if actual!=data['shape']:raise ValueError('lazy core not in complete mode-image bases')
        axis=case['free_axis'];other=[a for a in range(3) if a!=axis];points=((1<<data['shape'][other[0]])-1)*((1<<data['shape'][other[1]])-1)
        if case.get('mode_rank',actual[axis])!=actual[axis] or case.get('all_pair_points',points)!=points:raise ValueError('lazy mode/domain differs from catalog')
        return source,data,verified,source_sha,digest(dict(shape=data['shape'],core=data['core'])),sha(raw(data))


def compact_negative(result):
    if result['status']!='LOCAL_UNSAT' or result.get('complete') is not True:raise ValueError('only exact completed negatives can be compacted')
    value=dict(result);buckets=value.pop('bucket_span_ranks',None)
    if buckets is not None:
        d=value['mode_rank'];residues=[r[0] for r in buckets]
        if len(residues)!=len(set(residues)) or any(not r or n<1 or not 0<=rank<d for r,n,rank in buckets):raise ValueError('invalid negative bucket structural certificate')
        if value['inside_rank']>=d or value['inside_points']+sum(r[1] for r in buckets)!=value['all_nonzero_pair_points'] or len(buckets)!=value['nonzero_cosets']:
            raise ValueError('negative bucket census inconsistent')
        value.update(bucket_span_ranks_sha256=digest(buckets),bucket_count=len(buckets),bucket_span_max=max((r[2] for r in buckets),default=value['inside_rank']))
    value.update(algorithm_case=result.get('case'),raw_decoder_result_sha256=digest(result),negative_storage='Compact hash/statistics only; regenerate frozen source/mask core and rerun exact backend for full bucket rows.')
    return value


def directory_bytes(path):return sum(p.stat().st_size for p in Path(path).rglob('*') if p.is_file())
def ensure_room(path,cap=128*1024**2,reserve=8*1024**2):
    if directory_bytes(path)+reserve>cap:raise CampaignHold('phase logical-byte cap/reserve','phase_storage')


def restore_journal(out,cases,config_sha):
    values,chain=chain_read(Path(out)/'completed.jsonl',config_sha)
    for index,value in enumerate(values):
        if index>=len(cases) or value['index']!=index or value['case']!=cases[index]['id']:raise ValueError('completed journal scope/order changed')
        file=Path(out)/value['result_file']
        if sha(file.read_bytes())!=value['result_sha256']:raise ValueError('completed result bytes changed')
        result=read(file)
        if result['status']!=value['status'] or result['config_sha256']!=config_sha or result['case']!=cases[index]['id'] or result['status'] not in ('LOCAL_UNSAT','CONTROL_PASSED','VERIFIED_TARGET','SMALL_CONTROL_PASSED'):
            raise ValueError('completed result is not terminal evidence for selected case')
        if result['status']=='LOCAL_UNSAT' and result.get('complete') is not True:raise ValueError('incomplete negative in journal')
    return values,chain


def commit_journal(out,index,record,chain):return chain_append(Path(out)/'completed.jsonl',dict(record,index=index),chain)
