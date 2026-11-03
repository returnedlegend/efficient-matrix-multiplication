"""Lazy compact-core construction and strict post-call campaign barriers."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import time

from .compact_coset43 import digest,mode_slices,pair_column,expand_products
from .compact_coset_fast43 import solve_core as fast_solve
from .compact_eight43 import bits,factor_core,expand_core,packed_tensor,opposite_pair_ranks
from .forced_span43 import solve_span
from .sat_neighborhoods import factor_masks
from .verify import verify_candidate

HARD_DEADLINE=datetime(2026,11,4,21,31,16,tzinfo=timezone.utc).timestamp()
CAP=128*1024**2


class CampaignBarrier:
    def __init__(self,campaign,guard_path,seconds,deadline_utc='2026-11-04T21:31:16Z',clock=time.monotonic,utc=time.time):
        self.campaign=Path(campaign);self.guard_path=Path(guard_path);self.clock=clock;self.utc=utc;self.start=clock();self.seconds=seconds;self.stopped=False
        cutoff=datetime.fromisoformat(deadline_utc.replace('Z','+00:00'))
        if cutoff.tzinfo is None:raise ValueError('deadline requires UTC timezone')
        self.deadline=min(HARD_DEADLINE,cutoff.timestamp());self.cache={};self.last_poll=-float('inf');self.last_reason=None;self.children=[];self.root_stamp=None

    def _json(self,path):
        stamp=path.stat().st_mtime_ns
        if path not in self.cache or self.cache[path][0]!=stamp:self.cache[path]=(stamp,json.loads(path.read_bytes()))
        return self.cache[path][1]

    def _check(self,force=False):
        now=self.utc()
        if self.stopped:return 'campaign signal'
        if now>=self.deadline:return 'absolute campaign UTC cutoff'
        if self.clock()-self.start>=self.seconds:return 'launch monotonic cutoff'
        if not force and self.clock()-self.last_poll<.1:return self.last_reason
        self.last_poll=self.clock()
        try:
            if (self.campaign/'guard_stopped.json').exists():return 'canonical guard_stopped marker'
            if (self.campaign/'WINNER.json').exists():return 'campaign winner marker'
            stamp=self.campaign.stat().st_mtime_ns
            if stamp!=self.root_stamp:
                self.children=[Path(entry.path)/'WINNER.json' for entry in os.scandir(self.campaign) if entry.is_dir(follow_symlinks=False)];self.root_stamp=stamp
            for marker in self.children:
                if marker.exists():return 'immediate campaign winner marker: '+str(marker)
            queue=self._json(self.campaign/'queue_state.json')
            if queue.get('stop_reason'):return 'queue stop_reason: '+str(queue['stop_reason'])
            state=self._json(self.guard_path)
            age=now-datetime.fromisoformat(state['updated_utc'].replace('Z','+00:00')).timestamp()
            if age< -5 or age>60:return 'resource guard stale'
            if state.get('stop_reason'):return 'resource guard stop_reason: '+str(state['stop_reason'])
            pid=int(state['pid']);tail=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
            if tail[0] in ('Z','X') or int(tail[19])!=int(state['process_identity']['start_ticks']):return 'resource guard process no longer live'
            allocated=state['campaign_allocated_bytes']
            if type(allocated) is not int or allocated<0:return 'invalid resource storage count'
            if allocated>=5*1024**3:return 'fresh campaign storage reached 5GiB'
        except (OSError,ValueError,KeyError,TypeError):return 'canonical stop/resource state unavailable'
        if self.stopped:return 'campaign signal'
        if self.utc()>=self.deadline:return 'absolute campaign UTC cutoff'
        if self.clock()-self.start>=self.seconds:return 'launch monotonic cutoff'
        return None

    def check(self,force=False):
        reason=self._check(force);self.last_reason=reason;return reason


def guarded_call(function,barrier,*args,**kwargs):
    held=barrier.check(force=True)
    if held:return dict(status='UNKNOWN',raw_result=None,after_cutoff=False,reason=held)
    raw=function(*args,cancelled=lambda:barrier.check() is not None,**kwargs)
    held=barrier.check(force=True)
    if held:return dict(status='UNKNOWN',raw_result=raw,after_cutoff=True,reason=held)
    return dict(status=raw['status'],raw_result=raw,after_cutoff=False,reason=None)


class SourceRuntime:
    def __init__(self,source,small_control=False):
        report=verify_candidate(source,random_trials=0);self.source=source;self.terms=factor_masks(source);self.width=source['dimension']**2
        expected=7 if small_control else 93;dimension=2 if small_control else 5
        if not report['valid'] or source['dimension']!=dimension or report['rank']!=expected or report['exact_entries_checked']!=dimension**6 or opposite_pair_ranks(self.terms,self.width)!=[expected]*3:raise ValueError('source full tensor/pair independence failed')
        self.tensors=[packed_tensor(t,self.width) for t in self.terms]

    def prepare(self,case):
        mask=case['mask_lo']|(case['mask_hi']<<64);ids=list(bits(mask))
        if len(ids)!=case.get('source_local_products',8) or mask>>len(self.terms):raise ValueError('invalid lazy selected mask')
        bases,core,shape=factor_core(self.terms,ids)
        if shape!=case['shape']:raise ValueError('native scan/image dimension mismatch')
        ambient=0
        for i in ids:ambient^=self.tensors[i]
        if expand_core(core,shape,bases,self.width)!=ambient or hashlib.sha256(ambient.to_bytes((self.width**3+7)//8,'little')).hexdigest()!=case['residual_sha256']:raise ValueError('lazy exact ambient expansion mismatch')
        return dict(shape=shape,core=core,image_bases=bases,source_indices=ids,core_sha256=digest(dict(shape=shape,core=core)),basis_sha256=digest(bases))


def solve_cp_core(core,shape,target=7,axis=None,max_points=3969,max_branches=1000000,cancelled=None):
    if axis is None:axis=max(range(3),key=lambda a:(shape[a],-a))
    d=shape[axis]
    if target<=d+1:return fast_solve(core,shape,target,axis,max_points,cancelled)
    if target!=d+2:return dict(status='UNKNOWN',complete=False,case='unsupported_surplus_gt_two')
    slices,other=mode_slices(core,shape,axis);a,b=[shape[j] for j in other];count=((1<<a)-1)*((1<<b)-1)
    if count>max_points:return dict(status='UNKNOWN',complete=False,case='generic_catalog_cap')
    pairs=[(x,y) for x in range(1,1<<a) for y in range(1,1<<b)];columns=[pair_column(x,y,b) for x,y in pairs]
    result=solve_span(columns,slices,target,max_branches,cancelled);result['algorithm']='reviewed_generic_forced_inside_surplus_two'
    if result['status']=='SAT':
        support=result['support'];free=[0]*len(support)
        for coordinate,coeff in enumerate(result['target_coordinates']):
            for j in bits(coeff):free[j]^=1<<coordinate
        products=[]
        for j,index in enumerate(support):
            term=[0,0,0];term[axis]=free[j];term[other[0]],term[other[1]]=pairs[index]
            if all(term):products.append(term)
        if len(products)>target or expand_products(products,shape)!=core:raise AssertionError('generic lifted CP core failed')
        result['products']=products
    return result
