"""Exact bounded SAT for one finite weighted whole-C3 tensor code.

No production inputs are loaded here; any SAT model still needs literal orbit
expansion and independent full ambient tensor checks before publication.
"""
from datetime import datetime,timezone
import copy,math,multiprocessing as mp,time
from .sat_neighborhoods import gf2_rank
from .cyclic_tensor_code7 import xor_columns
from .compact_coset43 import digest
from .cyclic_code_worker7 import worker
DEADLINE='2026-11-03T19:24:17Z'
HARD_DEADLINE=datetime.fromisoformat(DEADLINE.replace('Z','+00:00')).timestamp()
SCOPE='Exact supplied finite whole-C3 dictionary only; UNSAT is not a global bilinear rank lower bound.'

def validate_code(columns,target,seed,kernel,weights,rank):
    n=len(columns)
    if not 1<=n<=2000 or len(weights)!=n or any(type(w)is not int or w not in(1,3) for w in weights) or any(type(v)is not int or v<0 for v in columns) or type(target)is not int or target<0:raise ValueError('invalid finite weighted code')
    if type(seed)is not int or not 0<=seed<1<<n or type(rank)is not int or rank!=gf2_rank(columns) or len(kernel)!=n-rank or any(type(v)is not int or not 0<v<1<<n for v in kernel) or gf2_rank(kernel)!=len(kernel):raise ValueError('complete independent kernel/rank certificate required')
    if xor_columns(columns,seed)!=target or any(xor_columns(columns,v) for v in kernel):raise ValueError('seed/kernel fails exact tensor syndrome')

def atmost(variables,bound,top):
    if bound<0:return [[]],top
    if bound>=len(variables):return [],top
    from pysat.card import CardEnc,EncType
    card=CardEnc.atmost(lits=variables,bound=bound,top_id=top,encoding=EncType.seqcounter)
    return card.clauses,max(top,card.nv)

def build_problem(columns,target,seed,kernel,weights,rank,budget=92):
    columns=list(columns);kernel=list(kernel);weights=list(weights);validate_code(columns,target,seed,kernel,weights,rank)
    if type(budget)is not int or budget<0 or budget%3!=2 or sum(w==1 for w in weights)>5:raise ValueError('this exact two-branch encoder requires budget2mod3 andatmost5cubes')
    n=len(columns);alphas=list(range(1,len(kernel)+1));xs=list(range(len(kernel)+1,len(kernel)+n+1));gate=len(kernel)+n+1;nv=gate;nf=[xs[i] for i,w in enumerate(weights) if w==3];cubes=[xs[i] for i,w in enumerate(weights) if w==1];q=budget//3
    xors=[([xs[i]]+[alphas[j] for j,v in enumerate(kernel) if v>>i&1],bool(seed>>i&1)) for i in range(n)];clauses=[]
    # gate=false: N<=q-1. gate=true: N<=q and C<=2.
    for variables,bound,guardlit in [(nf,q-1,gate),(nf,q,-gate),(cubes,2,-gate)]:
        rows,nv=atmost(variables,bound,nv);clauses.extend([guardlit]+row for row in rows)
    problem=dict(nv=nv,clauses=clauses,xors=xors,alpha_variables=alphas,orbit_variables=xs,gate_variable=gate,columns=columns,target=target,seed=seed,kernel=kernel,weights=weights,rank=rank,budget=budget)
    problem['metadata']=dict(algorithm='cyclic_code_sat7',scope=SCOPE,formula_sha256=digest(problem),orbit_variables=n,kernel_selectors=len(kernel),native_xors=len(xors),cnf_clauses=len(clauses),variables=nv,budget=budget)
    return problem

def validate_decode(problem,assignment,assumptions=()):
    if not isinstance(assignment,(list,tuple)) or len(assignment)!=problem['nv']+1 or any(type(v)is not bool for v in assignment[1:]):raise AssertionError('complete literal Boolean model required')
    if any(assignment[abs(lit)]!=(lit>0) for lit in assumptions):raise AssertionError('model violates assumptions')
    if any(not any(assignment[abs(lit)]==(lit>0) for lit in row) for row in problem['clauses']):raise AssertionError('model violates cardinality CNF')
    if any(bool(sum(assignment[v] for v in row)%2)!=rhs for row,rhs in problem['xors']):raise AssertionError('model violates kernel XOR')
    state=sum(int(assignment[v])<<i for i,v in enumerate(problem['orbit_variables']));alpha=sum(int(assignment[v])<<i for i,v in enumerate(problem['alpha_variables']));expected=problem['seed']
    for j,v in enumerate(problem['kernel']):
        if alpha>>j&1:expected^=v
    if state!=expected or xor_columns(problem['columns'],state)!=problem['target']:raise AssertionError('literal finite-code syndrome failed')
    cost=sum(w for i,w in enumerate(problem['weights']) if state>>i&1)
    if cost>problem['budget']:raise AssertionError('integer weighted product budget failed')
    return dict(state_hex=hex(state),alpha_hex=hex(alpha),product_cost=cost,selected_orbits=state.bit_count(),finite_code_membership_verified=True)


class _Guard:
    def __init__(self, seconds, deadline_utc, cancelled):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('positive finite seconds required')
        stamp = datetime.fromisoformat(deadline_utc.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('deadline requires timezone')
        self.until = time.monotonic()+seconds
        self.deadline = min(HARD_DEADLINE, stamp.timestamp())
        self.cancelled = cancelled
    def reason(self):
        if time.time() >= self.deadline:
            return 'deadline'
        if time.monotonic() >= self.until:
            return 'timeout'
        if self.cancelled and self.cancelled():
            return 'cancelled'
        # Callback IO may itself cross either clock boundary.
        if time.time() >= self.deadline:
            return 'deadline'
        if time.monotonic() >= self.until:
            return 'timeout'
        return None


def solve(problem, seconds=20, memory_mb=1024, cancelled=None, deadline_utc=DEADLINE, assumptions=()):
    if type(memory_mb) is not int or not 128 <= memory_mb <= 1024:
        raise ValueError('worker memory must be 128..1024 MiB')
    assumptions = list(assumptions)
    if any(type(v) is not int or not 1 <= abs(v) <= problem['nv'] for v in assumptions):
        raise ValueError('invalid Boolean assumptions')
    guard = _Guard(seconds, deadline_utc, cancelled)
    caller_problem = problem
    problem = copy.deepcopy(caller_problem)
    expected_hash = problem['metadata']['formula_sha256']
    def formula_hash(value):
        return digest({k:v for k,v in value.items() if k != 'metadata'})
    if formula_hash(problem) != expected_hash:
        raise ValueError('formula bytes differ from their construction hash')
    def checked_reason():
        reason = guard.reason()
        if reason:
            return reason
        try:
            if (caller_problem['metadata']['formula_sha256'] != expected_hash
                    or problem['metadata']['formula_sha256'] != expected_hash
                    or formula_hash(caller_problem) != expected_hash
                    or formula_hash(problem) != expected_hash):
                return 'formula_changed'
        except (KeyError, TypeError, ValueError):
            return 'formula_changed'
        # Hashing is work too; never cache clocks across the binding barrier.
        if time.time() >= guard.deadline:
            return 'deadline'
        if time.monotonic() >= guard.until:
            return 'timeout'
        return None
    started = time.monotonic()
    base = dict(algorithm='cyclic_code_sat7', scope=SCOPE, complete=False,
                formula_sha256=problem['metadata']['formula_sha256'], memory_mb=memory_mb,
                effective_deadline_utc=datetime.fromtimestamp(guard.deadline, timezone.utc).isoformat(),
                assumptions=assumptions)
    reason = checked_reason()
    if reason:
        return dict(base, status='UNKNOWN', reason=reason, worker_started=False)
    context = mp.get_context('spawn');receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=worker, args=(problem, max(.001, guard.until-time.monotonic()), memory_mb, sender, assumptions))
    try:
        child.start()
    except Exception as exc:
        receiver.close();sender.close()
        return dict(base, status='ERROR', error=type(exc).__name__+': '+str(exc), worker_started=False)
    sender.close();raw = None
    try:
        while raw is None:
            reason = checked_reason()
            if reason:
                raw = dict(status='UNKNOWN', reason=reason)
            elif receiver.poll(min(.05, max(0, guard.until-time.monotonic()))):
                try:
                    raw = receiver.recv()
                except EOFError:
                    raw = dict(status='ERROR', error='worker exited without a result')
    finally:
        child.join(timeout=.03)
        if child.is_alive():child.terminate()
        child.join(timeout=.2)
        if child.is_alive():child.kill();child.join()
        receiver.close()
    result = dict(base, worker_started=True, worker_pid=child.pid, worker_exitcode=child.exitcode,
                  worker_reaped=not child.is_alive(), elapsed_seconds=time.monotonic()-started)
    reason = checked_reason()
    if reason:
        return dict(result, status='UNKNOWN', reason=reason, raw_worker_result=raw,
                    after_cutoff=True, publication_eligible=False)
    assignment = raw.pop('assignment', None)
    result.update(raw)
    if result['status'] == 'SAT':
        try:witness = validate_decode(problem, assignment, assumptions)
        except (AssertionError,ValueError,TypeError) as error:
            return dict(result,status='ERROR',complete=False,error='malformed_model: '+str(error),raw_assignment=assignment,publication_eligible=False)
        reason = checked_reason()
        if reason:
            return dict(result, status='UNKNOWN', reason=reason, raw_compact=witness,
                        after_cutoff=True, publication_eligible=False)
        result.update(witness, complete=True, complete_assignment=assignment,
                      publication_eligible=False)  # Ambient/global verification is a caller gate.
    elif result['status'] == 'FINITE_CODE_UNSAT':
        if assumptions:result['status'] = 'FINITE_CODE_ASSUMPTIONS_UNSAT'
        result['complete'] = True
        result['finite_dictionary_complete'] = not assumptions
    reason = checked_reason()
    if reason:
        return dict(status='UNKNOWN', complete=False, reason=reason, raw_compact=result,
                    after_cutoff=True, publication_eligible=False, scope=SCOPE)
    return result
