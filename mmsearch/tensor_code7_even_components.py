"""Exact minima in disjoint small support components of a fixed even cycle span."""
from __future__ import annotations
from collections import defaultdict
import copy
from mmsearch.tensor_code7 import digest
SCHEMA='tensor_code7.even_components.v1'

def select_starts(seed_states,kernel,max_starts=16,ceiling=98):
 if type(max_starts) is not int or not 1<=max_starts<=16:raise ValueError('start cap')
 original=[dict(kind='original_even',seed_index=i,state_hex=hex(x),weight=x.bit_count()) for i,x in enumerate(seed_states) if x.bit_count()%2==0 and x.bit_count()<=ceiling]
 odd=[(j,z) for j,z in enumerate(kernel) if z.bit_count()%2]
 derived=sorted((dict(kind='odd_initialization',seed_index=i,odd_basis_index=j,state_hex=hex(x^z),weight=(x^z).bit_count()) for i,x in enumerate(seed_states) if x.bit_count()%2 for j,z in odd if (x^z).bit_count()<=ceiling),key=lambda t:(t['weight'],t['seed_index'],t['odd_basis_index']))
 seen=set();out=[]
 for t in original+derived:
  if t['state_hex'] not in seen:out.append(t);seen.add(t['state_hex'])
  if len(out)==max_starts:break
 return out

def component_basis(cycles):
 if not cycles or any(type(z) is not int or z<=0 or z.bit_count()%2 for z in cycles):raise ValueError('nonzero even generators required')
 parent={}
 def find(x):
  parent.setdefault(x,x)
  while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
  return x
 for z in cycles:
  ids=[]
  while z:
   bit=z&-z;ids.append(bit.bit_length()-1);z^=bit
  for i in ids:parent[find(i)]=find(ids[0])
 groups=defaultdict(list)
 for z in cycles:groups[find((z&-z).bit_length()-1)].append(z)
 out=[]
 for zs in groups.values():
  b={};support=0
  for x in zs:
   support|=x
   while x:
    k=x.bit_length()-1
    if k not in b:b[k]=x;break
    x^=b[k]
  basis=[b[k] for k in sorted(b,reverse=True)]
  out.append(dict(support_hex=hex(support),atom_count=support.bit_count(),rank=len(basis),basis_hex=[hex(x) for x in basis],generator_count=len(zs)))
 return sorted(out,key=lambda t:(t['rank'],int(t['support_hex'],16)))

def residue(state,basis):
 for z in basis:
  if state>>(z.bit_length()-1)&1:state^=z
 return state

def minimize_components(starts,cycles,max_rank=20,max_states=10000000,cancelled=None,checkpoint=None,on_target=None,target=92,large_solver=None):
 if type(max_rank) is not int or not 1<=max_rank<=20 or type(max_states) is not int or max_states<1:raise ValueError('enumeration caps')
 if not starts or len(starts)>16 or any(type(x) is not int or x<0 or x.bit_count()%2 for x in starts):raise ValueError('nonnegative even starts required')
 starts=tuple(starts);cycles=tuple(cycles)
 components=component_basis(cycles);support=0
 for c in components:support|=int(c['support_hex'],16)
 states=list(starts);lower=[(x&~support).bit_count() for x in starts];records=[];enumerated=0;stop=None;skipped=0;cache_hits=0;target_found=False
 def reason():return cancelled() if cancelled else None
 def report():
  done=len(records)==len(components)
  return dict(schema=SCHEMA,status='UNKNOWN' if stop else 'TARGET_CANDIDATE_FOUND' if target_found else 'EXACT_SELECTED_SPAN_MINIMA' if done and not skipped else 'UNKNOWN',complete=not stop and done and not skipped,stop_reason=str(stop) if stop else 'unfinished_components' if skipped or not done else None,scope='Only listed starting cosets of this even-generator span; no full-code or global optimum claim.',parameters=dict(max_rank=max_rank,max_states=max_states),target_found=target_found,component_count=len(components),processed_components=len(records),span_rank=sum(t['rank'] for t in components),fixed_atom_weights=[(x&~support).bit_count() for x in starts],components=records,skipped_components=skipped,enumerated_states=enumerated,cache_hits=cache_hits,states_hex=[hex(x) for x in states],weights=[x.bit_count() for x in states],lower_bounds=lower,all_large_components_computed=done and not skipped and all(r['complete'] for r in records if r['rank']>max_rank))
 stop=reason()
 for ci,c in enumerate(components):
  if stop:break
  mask=int(c['support_hex'],16);basis=tuple(int(z,16) for z in c['basis_hex']);record=dict(c,component_index=ci,start_results=[]);cache={}
  if c['rank']>max_rank:
   record.update(status='LOCAL_SAT_MINIMA' if large_solver else 'UNCOMPUTED_RANK_CAP',complete=True)
   for si,x in enumerate(starts):
    stop=reason()
    if stop:break
    local=x&mask;key=hex(residue(local,basis))
    if key in cache:answer=cache[key];cache_hits+=1
    elif large_solver:
     answer=copy.deepcopy(large_solver(local,basis,mask,ci,si))
     stop=reason()
     if stop:break
     cache[key]=answer
    else:answer=dict(complete=False,lower_bound=local.bit_count()%2,upper_bound=local.bit_count(),minimizer_hex=hex(local),status='UNCOMPUTED_RANK_CAP')
    minimum=int(answer['minimizer_hex'],16)
    if minimum&~mask or residue(minimum^local,basis) or answer['upper_bound']!=minimum.bit_count() or not 0<=answer['lower_bound']<=minimum.bit_count():raise ValueError('invalid local SAT bounds/state')
    if answer['complete'] and answer['lower_bound']!=minimum.bit_count():raise ValueError('false local exact claim')
    states[si]=(states[si]&~mask)|minimum;lower[si]+=answer['lower_bound']
    record['start_results'].append(dict(answer,start_index=si,coset_residue_hex=key))
    if not answer['complete']:record['complete']=False
   if not record['complete']:skipped+=1
  else:
   record.update(status='EXACT_LOCAL_COSET_MINIMA',complete=True)
   for si,x in enumerate(starts):
    stop=reason()
    if stop:break
    local=residue(x&mask,basis);key=hex(local);count=1<<len(basis)
    if key in cache:minimum=cache[key];cache_hits+=1
    else:
     if enumerated+count>max_states:stop='state_budget';break
     value=local;best=value;weight=value.bit_count();bw=weight
     for index in range(count):
      if index%256==0:
       stop=reason()
       if stop:break
      if index:
       value^=basis[(index&-index).bit_length()-1];weight=value.bit_count()
       if (weight,value)<(bw,best):best=value;bw=weight
      enumerated+=1
     if not stop:stop=reason()
     if stop:break
     minimum=best;cache[key]=minimum
    stop=reason()
    if stop:break
    states[si]=(states[si]&~mask)|minimum;lower[si]+=minimum.bit_count()
    record['start_results'].append(dict(start_index=si,coset_residue_hex=key,minimum_weight=minimum.bit_count(),minimizer_hex=hex(minimum),complete=True))
  if stop:record.update(status='UNKNOWN',complete=False,stop_reason=str(stop))
  records.append(record)
  if checkpoint:checkpoint(copy.deepcopy(report()))
  if not stop:stop=reason()
  if not stop and on_target:
   for si,x in enumerate(states):
    if x.bit_count()<=target:
     accepted=on_target(dict(state_hex=hex(x),new_weight=x.bit_count(),old_weight=starts[si].bit_count(),start_index=si,method=SCHEMA))
     stop=reason()
     if stop:break
     if accepted:target_found=True;break
  if stop or target_found:break
 if not stop:stop=reason()
 final=report()
 if stop:
  # Bounds omit unfinished components; zero remains a valid local lower bound.
  final.update(status='UNKNOWN',complete=False)
 if checkpoint:checkpoint(copy.deepcopy(final))
 late=reason()
 if late:final.update(status='UNKNOWN',complete=False,target_found=False,stop_reason=str(late))
 return final
