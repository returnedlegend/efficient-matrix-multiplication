"""Bounded exact merge3/flip4/plus5 whole-dictionary cycle catalogue.

No new atoms are introduced. Completeness refers only to these explicit identity
families, not all zero subsets or minimum tensor rank. Deterministic, no RNG.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from itertools import combinations,permutations

from mmsearch.tensor_code7 import atom_column,supports,term_from_atom,xor_columns

SCHEMA='tensor_code7.sparse_cycles.v1'
ORDERS=tuple(permutations(range(3)))


class Limit(Exception):pass


def _integer(value,name,low,high):
 if type(value) is not int or not low<=value<=high:raise ValueError('invalid '+name)


def _insert(basis,value):
 while value:
  pivot=value.bit_length()-1
  if pivot not in basis:basis[pivot]=value;return True
  value ^= basis[pivot]
 return False


def enumerate_cycles(atoms,n,max_trials=2000000,max_cycles=10000,cancelled=None,progress=None):
 _integer(n,'dimension',1,5);_integer(max_trials,'trial cap',1,2000000);_integer(max_cycles,'cycle cap',1,10000)
 atoms=[tuple(a) for a in atoms]
 if not atoms or len(atoms)>5000 or len(set(atoms))!=len(atoms):raise ValueError('distinct nonempty atom dictionary required')
 lookup={};columns=[]
 found={};span={};trials=0;by_trial=Counter();exhausted=[];cursor=None
 def trial(family,parents,axes):
  nonlocal trials,cursor
  cursor=dict(family=family,parent_atom_ids=list(parents),axis_permutation=list(axes),next_trial=trials+1)
  if cancelled:
   reason=cancelled()
   if reason:raise Limit('cancelled:'+str(reason))
  if trials>=max_trials:raise Limit('trial_cap')
  trials+=1;by_trial[family]+=1
  if progress and trials%100000==0:progress(dict(cursor=cursor,trials=trials,cycle_count=len(found),span_rank=len(span)))
 def accept(family,ids,parents,axes):
  if len(set(ids))!=len(ids):return
  mask=sum(1<<i for i in ids)
  if mask in found:return
  if xor_columns(columns,mask):raise ValueError('identity failed complete tensor syndrome')
  if len(found)>=max_cycles:raise Limit('cycle_cap')
  found[mask]=dict(mask_hex=hex(mask),weight=len(ids),family=family,parent_atom_ids=list(parents),
   axis_permutation=list(axes),full_tensor_syndrome_hex='0x0',tensor_entries_checked=n**6)
  _insert(span,mask)
 complete=False;stop_reason=None
 try:
  for index,atom in enumerate(atoms):
   cursor=dict(phase='full_column_regeneration',atom_index=index)
   if cancelled:
    reason=cancelled()
    if reason:raise Limit('cancelled:'+str(reason))
   term_from_atom(atom,n);lookup[atom]=index;columns.append(atom_column(atom,n))
  # Merge: two common factors, third vector XOR.
  for free in range(3):
   fixed=[axis for axis in range(3) if axis!=free];groups=defaultdict(list)
   for i,a in enumerate(atoms):groups[(a[fixed[0]],a[fixed[1]])].append(i)
   for key in sorted(groups):
    for i,j in combinations(groups[key],2):
     trial('merge3',(i,j),(*fixed,free));new=list(atoms[i]);new[free]^=atoms[j][free]
     k=lookup.get(tuple(new))
     if k is not None:accept('merge3',(i,j,k),(i,j),(*fixed,free))
  exhausted.append('merge3')
  # Flip: common first factor; both orders of the other two axes.
  for common in range(3):
   other=[axis for axis in range(3) if axis!=common];groups=defaultdict(list)
   for i,a in enumerate(atoms):groups[a[common]].append(i)
   for value in sorted(groups):
    for i,j in combinations(groups[value],2):
     for b,c in (other,other[::-1]):
      axes=(common,b,c);trial('flip4',(i,j),axes);x,y=atoms[i],atoms[j]
      first=list(x);second=list(y);first[b]^=y[b];second[c]^=x[c]
      if not all(first) or not all(second):continue
      k=lookup.get(tuple(first));l=lookup.get(tuple(second))
      if k is not None and l is not None:accept('flip4',(i,j,k,l),(i,j),axes)
  exhausted.append('flip4')
  # Plus path: all six coordinate paths, unordered endpoints. Reversing a path
  # is represented by another axis order; no endpoint-order family is omitted.
  for i,j in combinations(range(len(atoms)),2):
   x,y=atoms[i],atoms[j]
   for axes in ORDERS:
    trial('plus5',(i,j),axes);a,b,c=axes
    da=x[a]^y[a];db=x[b]^y[b];dc=x[c]^y[c]
    if not da or not db or not dc:continue
    first=list(x);first[a]=da
    second=list(y);second[b]=x[b];second[c]=dc
    third=list(y);third[b]=db
    ids=[lookup.get(tuple(t)) for t in (first,second,third)]
    if all(k is not None for k in ids):accept('plus5',(i,j,*ids),(i,j),axes)
  exhausted.append('plus5')
  if cancelled:
   reason=cancelled()
   if reason:raise Limit('cancelled:'+str(reason))
  complete=True
 except Limit as exc:stop_reason=str(exc)
 records=[found[mask] for mask in sorted(found)]
 return dict(schema=SCHEMA,status='COMPLETE_IDENTITY_FAMILIES' if complete else 'UNKNOWN',complete=complete,
  stop_reason=stop_reason,dimension=n,dictionary_size=len(atoms),tensor_entries=n**6,
  parameters=dict(max_trials=max_trials,max_cycles=max_cycles),trials=trials,trials_by_family=dict(by_trial),
  completed_families=exhausted,cursor=cursor,cycle_count=len(records),weight_distribution=dict(Counter(r['weight'] for r in records)),
  family_distribution=dict(Counter(r['family'] for r in records)),cycle_span_rank=len(span),
  cycle_span_basis_hex=[hex(span[p]) for p in sorted(span,reverse=True)],cycles=records,
  rng=None,resume_supported=False,scope='Exactly listed merge3/flip4/plus5 path families inside this fixed dictionary; no minimum/novelty claim.')


def validate_catalogue(catalogue,atoms,n):
 if type(catalogue.get('dimension')) is not int or type(catalogue.get('dictionary_size')) is not int or type(catalogue.get('cycle_count')) is not int or type(catalogue.get('cycle_span_rank')) is not int:raise ValueError('literal catalogue integer metadata required')
 if catalogue.get('schema')!=SCHEMA or catalogue.get('dimension')!=n or catalogue.get('dictionary_size')!=len(atoms):raise ValueError('catalogue input/schema differs')
 atoms=[tuple(a) for a in atoms];lookup={a:i for i,a in enumerate(atoms)}
 columns=[atom_column(a,n) for a in atoms];seen=set();basis={}
 for record in catalogue['cycles']:
  if type(record.get('weight')) is not int:raise ValueError('literal cycle weight required')
  parents=record['parent_atom_ids'];axes=record['axis_permutation']
  if len(parents)!=2 or any(type(i) is not int or not 0<=i<len(atoms) for i in parents) or parents[0]==parents[1] or type(axes) is not list or any(type(i) is not int for i in axes) or sorted(axes)!=[0,1,2]:raise ValueError('invalid identity witness')
  x,y=[atoms[i] for i in parents];a,b,c=axes
  if record['family']=='merge3':
   if x[a]!=y[a] or x[b]!=y[b]:raise ValueError('merge fixed factors differ')
   z=list(x);z[c]^=y[c];derived=[tuple(z)]
  elif record['family']=='flip4':
   if x[a]!=y[a]:raise ValueError('flip common factor differs')
   z=list(x);w=list(y);z[b]^=y[b];w[c]^=x[c];derived=[tuple(z),tuple(w)]
  elif record['family']=='plus5':
   z=list(x);z[a]^=y[a];w=list(y);w[b]=x[b];w[c]^=x[c];v=list(y);v[b]^=x[b];derived=[tuple(z),tuple(w),tuple(v)]
  else:raise ValueError('unknown cycle family')
  ids=parents+[lookup.get(t) for t in derived]
  if any(i is None for i in ids) or len(set(ids))!=len(ids):raise ValueError('identity point missing/degenerate')
  expected=sum(1<<i for i in ids)
  mask=int(record['mask_hex'],16)
  if mask!=expected:raise ValueError('mask differs from declared exact identity')
  if mask in seen or mask.bit_count()!=record['weight'] or record['weight'] not in (3,4,5) or xor_columns(columns,mask):raise ValueError('invalid zero cycle')
  seen.add(mask);_insert(basis,mask)
 if len(seen)!=catalogue['cycle_count'] or len(basis)!=catalogue['cycle_span_rank']:raise ValueError('cycle count/span rank differs')
 return [int(r['mask_hex'],16) for r in catalogue['cycles']]


def scan_seed_deltas(seeds,cycles,max_evaluations=360000,cancelled=None,on_negative=None):
 """One-hop independent scans of original seeds only; never feed candidates back."""
 _integer(max_evaluations,'evaluation cap',1,360000)
 seeds=list(seeds);cycles=list(cycles)
 if any(type(x) is not int or x<0 for x in seeds+cycles):raise ValueError('literal nonnegative states/cycles required')
 evaluated=0;negative=0;complete=False;reason=None;cursor=None
 try:
  for seed_index,state in enumerate(seeds):
   for cycle_index,cycle in enumerate(cycles):
    cursor=dict(seed_index=seed_index,cycle_index=cycle_index,next_evaluation=evaluated+1)
    if cancelled:
     stop=cancelled()
     if stop:raise Limit('cancelled:'+str(stop))
    if evaluated>=max_evaluations:raise Limit('evaluation_cap')
    evaluated+=1;delta=cycle.bit_count()-2*(state&cycle).bit_count()
    if delta<0:
     negative+=1;candidate=state^cycle
     item=dict(seed_index=seed_index,cycle_index=cycle_index,cycle_hex=hex(cycle),delta=delta,
      old_weight=state.bit_count(),new_weight=candidate.bit_count(),state_hex=hex(candidate))
     if on_negative and on_negative(item):raise Limit('callback_stop')
  if cancelled:
   stop=cancelled()
   if stop:raise Limit('cancelled:'+str(stop))
  complete=True
 except Limit as exc:reason=str(exc)
 return dict(status='COMPLETE_SEED_CYCLE_SCAN' if complete else 'UNKNOWN',complete=complete,stop_reason=reason,
  evaluated=evaluated,negative_moves=negative,cursor=cursor,scope='Only original verified seeds crossed with this exact catalogue; no global lower bound.')
