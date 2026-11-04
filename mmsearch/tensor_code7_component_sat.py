"""Bounded native-XOR/cardinality minimization of one binary affine code coset."""
from __future__ import annotations
import multiprocessing as mp
from pathlib import Path
import sys,time,resource,math
from mmsearch.tensor_code7_even_components import residue

def canonical_basis(basis,support):
 pivots={}
 for value in basis:
  if type(value) is not int or value<=0 or value&~support or value.bit_count()%2:raise ValueError('nonzero even component basis')
  x=value
  while x:
   k=x.bit_length()-1
   if k not in pivots:pivots[k]=x;break
   x^=pivots[k]
  if not x:raise ValueError('dependent component basis')
 return [pivots[k] for k in sorted(pivots,reverse=True)]

def _worker(origin,basis,positions,bound,seconds,sender):
 try:
  resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
  resource.setrlimit(resource.RLIMIT_CPU,(max(1,math.ceil(seconds)),max(1,math.ceil(seconds))))
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.xor-deps'))
  import pycryptosat
  from pysat.card import CardEnc,EncType
  start=time.monotonic();m=len(positions);r=len(basis)
  cnf=CardEnc.atmost(lits=list(range(1,m+1)),bound=bound,top_id=m+r,encoding=EncType.seqcounter)
  solver=pycryptosat.Solver(threads=1,verbose=0,time_limit=seconds)
  solver.add_clause([max(cnf.nv,m+r),-max(cnf.nv,m+r)])
  for clause in cnf.clauses:solver.add_clause(clause)
  equations=[]
  for i,p in enumerate(positions):
   variables=[i+1]+[m+j+1 for j,z in enumerate(basis) if z>>p&1];rhs=bool(origin>>p&1)
   solver.add_xor_clause(variables,rhs);equations.append((variables,rhs))
  left=seconds-(time.monotonic()-start)
  status,model=solver.solve(time_limit=max(.001,left)) if left>0 else (None,None)
  out=dict(status='SAT' if status is True else 'UNSAT' if status is False else 'UNKNOWN',bound=bound)
  if status is True:
   if len(model)<=max(cnf.nv,m+r) or any(type(v) is not bool for v in model[1:]):raise ValueError('incomplete native assignment')
   if any(not any(model[abs(l)]==(l>0) for l in c) for c in cnf.clauses) or any(bool(sum(model[v] for v in vs)%2)!=rhs for vs,rhs in equations):raise ValueError('native model violates formula')
   state=sum((1<<p) for i,p in enumerate(positions) if model[i+1]);coefficient=sum((1<<j) for j in range(r) if model[m+j+1]);replay=origin
   for j,z in enumerate(basis):
    if coefficient>>j&1:replay^=z
   if state!=replay or state.bit_count()>bound:raise ValueError('native selection replay/bound differs')
   out.update(state_hex=hex(state),coefficient_hex=hex(coefficient))
  out['worker_cpu_seconds']=sum(resource.getrusage(resource.RUSAGE_SELF)[:2]);sender.send(out)
 except BaseException as exc:
  try:sender.send(dict(status='ERROR',error=type(exc).__name__+':'+str(exc),bound=bound))
  except Exception:pass
 finally:sender.close()

def solve_bound(origin,basis,support,bound,seconds=2,cancelled=None):
 if type(origin) is not int or origin<0 or type(support) is not int or support<=0 or origin&~support or type(bound) is not int or bound<0 or not isinstance(seconds,(float,int)) or isinstance(seconds,bool) or not math.isfinite(seconds) or not 0<seconds<=10:raise ValueError('component formula/limits')
 basis=tuple(canonical_basis(tuple(basis),support))
 positions=[i for i in range(support.bit_length()) if support>>i&1]
 if any(type(z) is not int or z<=0 or z&~support or z.bit_count()%2 for z in basis):raise ValueError('component basis')
 if cancelled and cancelled():return dict(status='UNKNOWN',solver_called=False,worker_reaped=True,reason='cancelled before dispatch')
 start=time.monotonic();before=sum(resource.getrusage(resource.RUSAGE_CHILDREN)[:2]);ctx=mp.get_context('spawn');receiver,sender=ctx.Pipe(False);child=ctx.Process(target=_worker,args=(origin,basis,positions,bound,seconds,sender));child.start();sender.close();result=None
 try:
  while result is None:
   if time.monotonic()-start>=seconds or (cancelled and cancelled()):result=dict(status='UNKNOWN',reason='wall limit or campaign stop')
   elif receiver.poll(.02):
    try:result=receiver.recv()
    except EOFError:result=dict(status='UNKNOWN',reason='worker exited without result')
    if time.monotonic()-start>=seconds or (cancelled and cancelled()):result=dict(status='UNKNOWN',reason='late worker result',raw=result)
 finally:
  child.join(.02)
  if child.is_alive():child.terminate();child.join(.1)
  if child.is_alive():child.kill();child.join()
  receiver.close()
 result.update(solver_called=True,worker_reaped=not child.is_alive(),worker_pid=child.pid,worker_exitcode=child.exitcode,cpu_seconds=sum(resource.getrusage(resource.RUSAGE_CHILDREN)[:2])-before,wall_seconds=time.monotonic()-start,bound=bound)
 if result['status']=='SAT':
  state=int(result['state_hex'],16)
  if state.bit_count()>bound or residue(state^origin,basis):raise ValueError('parent rejects native coset model')
 if cancelled and cancelled():result=dict(status='UNKNOWN',reason='late after parent model validation',raw=result,solver_called=True,worker_reaped=True,cpu_seconds=result.get('cpu_seconds',0))
 return result

def minimize_local(origin,basis,support,seconds=5,cancelled=None,solve=solve_bound):
 if type(origin) is not int or origin<0 or type(support) is not int or support<=0 or origin&~support or not isinstance(seconds,(float,int)) or isinstance(seconds,bool) or not math.isfinite(seconds) or not 0<seconds<=10:raise ValueError('literal local state/support/seconds required')
 basis=tuple(canonical_basis(tuple(basis),support))
 start=time.monotonic();best=origin;lower=origin.bit_count()%2;queries=[];cpu=0.;stop=None
 while best.bit_count()>lower:
  left=seconds-(time.monotonic()-start)
  if left<=.05 or (cancelled and cancelled()):stop='budget or cancellation';break
  query=solve(origin,basis,support,best.bit_count()-1,min(2.5,left),cancelled)
  if cancelled and cancelled():query=dict(status='UNKNOWN',reason='late after local query callback',raw=query,cpu_seconds=query.get('cpu_seconds',0))
  queries.append(query);cpu+=query.get('cpu_seconds',0)
  if query['status']=='SAT':
   state=int(query['state_hex'],16)
   if state.bit_count()>=best.bit_count() or residue(state^origin,basis):raise ValueError('invalid improving coset model')
   best=state
  elif query['status']=='UNSAT':lower=best.bit_count();break
  else:stop=query.get('reason',query['status']);break
 if cancelled and cancelled():stop='late after local validation'
 return dict(status='EXACT_LOCAL_MINIMUM' if not stop and lower==best.bit_count() else 'UNKNOWN',complete=not stop and lower==best.bit_count(),lower_bound=lower,upper_bound=best.bit_count(),minimizer_hex=hex(best),queries=queries,cpu_seconds=cpu,stop_reason=stop)
