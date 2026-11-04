"""Unreviewed draft parity walk; unused by the exact-component controller.

No production runner calls this draft. Exact component preprocessing superseded
the initial annealing proposal before any production walk was launched.
"""
from __future__ import annotations
import copy
import random
import math
from collections import Counter
from mmsearch.tensor_code7 import digest,rng_restore

SCHEMA='tensor_code7.even_walk.v1'

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

def _config(starts,cycles,seed,ceiling,target):
 return digest(dict(starts=starts,cycles=[hex(z) for z in cycles],seed=seed,ceiling=ceiling,target=target,profiles=['neutral96','anneal98','novelty98'],archive_cap=32,restart_interval=256))

def walk(starts,cycles,seed=20261103165901,ceiling=98,target=92,max_steps=100000000,cancelled=None,on_target=None,checkpoint=None,resume=None):
 """Only even generators; bounded uphill, neutral novelty, no optimality claim.

 A checkpoint is a committed step boundary. Cancellation during scoring or a
 target callback restores the preceding cursor/RNG; the controller retains raw
 target evidence separately. Resume binds exact starts/generators/parameters.
 """
 if type(seed) is not int or type(ceiling) is not int or ceiling%2 or type(target) is not int or target%2 or target>ceiling or type(max_steps) is not int or max_steps<1:raise ValueError('walk parameters')
 if not starts or len(starts)>16 or not cycles or any(type(z) is not int or z<=0 or z.bit_count()%2 for z in cycles):raise ValueError('nonzero even generators required')
 initial=[int(t['state_hex'],16) for t in starts]
 if any(x<0 or x.bit_count()%2 or x.bit_count()>ceiling for x in initial):raise ValueError('even bounded starts required')
 cfg=_config(starts,cycles,seed,ceiling,target);rng=random.Random(seed)
 if resume is None:
  slots=[dict(state_hex=hex(x),best=x.bit_count(),pool=[hex(x)],recent=[hex(x)],accepted=0) for x in initial]
  cp=dict(schema=SCHEMA,config_sha256=cfg,step=0,slots=slots,rng=rng.getstate(),stats=dict(accepted_neutral=0,accepted_uphill=0,accepted_downhill=0,rejected=0,restarts=0,evaluated=0),best_weight=min(x.bit_count() for x in initial),target_found=False)
 else:
  cp=copy.deepcopy(resume)
  if cp.get('schema')!=SCHEMA or cp.get('config_sha256')!=cfg or type(cp.get('step')) is not int or cp['step']<0 or len(cp.get('slots',[]))!=len(initial):raise ValueError('checkpoint configuration/cursor')
  for slot in cp['slots']:
   if type(slot.get('best')) is not int or type(slot.get('accepted')) is not int or slot['accepted']<0 or not 1<=len(slot['pool'])<=32 or not 1<=len(slot['recent'])<=32:raise ValueError('checkpoint slot')
   vals=[int(slot['state_hex'],16)]+[int(x,16) for x in slot['pool']+slot['recent']]
   if any(x<0 or x.bit_count()%2 or x.bit_count()>ceiling for x in vals) or any(int(x,16).bit_count()!=slot['best'] for x in slot['pool']):raise ValueError('checkpoint parity/bounds')
  if any(type(v) is not int or v<0 for v in cp['stats'].values()):raise ValueError('checkpoint counters')
  rng=rng_restore(cp['rng'])
 def reason():return cancelled() if cancelled else None
 stop=reason()
 while not stop and cp['step']<max_steps and not cp['target_found']:
  old=copy.deepcopy(cp);oldrng=rng.getstate();index=cp['step']%len(initial);slot=cp['slots'][index];profile=(cp['step']//(len(initial)*256))%3;limit=96 if profile==0 and slot['best']<=96 else ceiling
  if cp['step'] and cp['step']%(len(initial)*256)==index:
   slot['state_hex']=rng.choice(slot['pool']);slot['recent']=[slot['state_hex']];cp['stats']['restarts']+=1
  state=int(slot['state_hex'],16);weight=state.bit_count();choices=[];recent=set(slot['recent'])
  for j,z in enumerate(cycles):
   if j%32==0:
    stop=reason()
    if stop:break
   nxt=state^z;nw=nxt.bit_count();cp['stats']['evaluated']+=1
   if nw<=limit and hex(nxt) not in recent:choices.append((nw-weight,j,nxt))
  if not stop and choices:
   down=[t for t in choices if t[0]<0];neutral=[t for t in choices if t[0]==0];up=[t for t in choices if t[0]>0]
   if down:
    delta=min(t[0] for t in down);choice=rng.choice([t for t in down if t[0]==delta])
   elif neutral and (not up or rng.random()<(.92 if profile==0 else .70 if profile==1 else .50)):choice=rng.choice(neutral)
   elif up:
    choice=rng.choice(up);temperature=.4 if profile==0 else 1.1 if profile==1 else 2.0
    if rng.random()>=math.exp(-choice[0]/temperature):choice=None
   else:choice=rng.choice(neutral) if neutral else None
   if choice is not None:
    delta,j,nxt=choice;nw=nxt.bit_count()
    if nw<=target:
     item=dict(state_hex=hex(nxt),new_weight=nw,old_weight=weight,start_index=index,cycle_index=j,step=cp['step'],profile=profile)
     if on_target:on_target(item)
     stop=reason()
     if not stop:cp['target_found']=True;cp['target']=item
    if not stop:
     slot['state_hex']=hex(nxt);slot['accepted']+=1;slot['recent']=(slot['recent']+[hex(nxt)])[-32:]
     cp['stats']['accepted_downhill' if delta<0 else 'accepted_uphill' if delta>0 else 'accepted_neutral']+=1
     if nw<slot['best']:slot['best']=nw;slot['pool']=[hex(nxt)]
     elif nw==slot['best'] and hex(nxt) not in slot['pool']:
      if len(slot['pool'])<32:slot['pool'].append(hex(nxt))
      else:slot['pool'][rng.randrange(32)]=hex(nxt)
     cp['best_weight']=min(cp['best_weight'],nw)
   else:cp['stats']['rejected']+=1
  elif not stop:
   cp['stats']['rejected']+=1;slot['state_hex']=rng.choice(slot['pool']);slot['recent']=[slot['state_hex']]
  if not stop:stop=reason()
  if stop:cp=old;rng.setstate(oldrng);break
  cp['step']+=1;cp['rng']=rng.getstate()
  if checkpoint and (cp['step']%1024==0 or cp['target_found']):checkpoint(copy.deepcopy(cp))
  stop=reason()
 cp['rng']=rng.getstate()
 if checkpoint:checkpoint(copy.deepcopy(cp))
 return dict(status='TARGET_FOUND' if cp['target_found'] else 'UNKNOWN',complete=bool(cp['target_found']),stop_reason=str(stop) if stop else 'step_budget',checkpoint=cp,scope='Fixed even-generator cosets only; no code optimum claim.')
