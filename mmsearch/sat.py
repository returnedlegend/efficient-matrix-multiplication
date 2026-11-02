"""Exact local GF(2) tensor SAT, with frozen terms and bounded CaDiCaL runs.

Boolean coefficients are canonical representatives of {-1,0,1} in
characteristic two: -1=1. No coefficient is ever represented by a float.
UNSAT applies only to the explicitly frozen local neighborhood.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import math
import multiprocessing as mp
from pathlib import Path
import time

from .tensor import multiplication_tensor
from .verify import verify_candidate, write_standalone_verifier


class CNF:
    def __init__(self):
        self.clauses = []
        self.nv = 0
        self.and_cache = {}

    def variable(self):
        self.nv += 1
        return self.nv

    def conjunction(self, variables):
        # Factor entries are positive variables or the constant zero.
        if 0 in variables:
            return 0
        key = tuple(sorted(set(variables)))
        if len(key) == 1:
            return key[0]
        if key not in self.and_cache:
            q = self.variable()
            self.clauses.extend([[-q, x] for x in key])
            self.clauses.append([q] + [-x for x in key])
            self.and_cache[key] = q
        return self.and_cache[key]

    def parity(self, variables, required):
        # Remove constants and cancel duplicates in F2.
        odd = set()
        for x in variables:
            if x:
                if x in odd:
                    odd.remove(x)
                else:
                    odd.add(x)
        values = sorted(odd)
        if not values:
            if required:
                self.clauses.append([])
            return
        previous = values[0]
        for x in values[1:]:
            z = self.variable()
            # z iff previous xor x.
            self.clauses.extend([[-previous,-x,-z], [previous,x,-z],
                                 [previous,-x,z], [-previous,x,z]])
            previous = z
        self.clauses.append([previous if required else -previous])


def _normalize(candidate):
    checked = verify_candidate(candidate, random_trials=0)
    if checked['rank'] is None or candidate.get('field') != 2:
        raise ValueError('input must have a valid F2 certificate schema')
    result = copy.deepcopy(candidate)
    for term in result['terms']:
        for axis in ('u','v','w'):
            if any(x not in (-1,0,1) for x in term[axis]):
                raise ValueError('coefficients must belong to {-1,0,1}')
            term[axis] = [x % 2 for x in term[axis]]
    return result


def choose_active_terms(candidate, drop_term, count):
    """Prioritize terms whose factor supports overlap the deleted product."""
    if count < 1:
        raise ValueError('active count must be positive')
    deleted = candidate['terms'][drop_term]
    def score(index):
        term = candidate['terms'][index]
        overlap = sum(sum(bool(a) and bool(b) for a,b in zip(term[axis], deleted[axis]))
                      for axis in ('u','v','w'))
        difference = sum(sum(bool(a) != bool(b) for a,b in zip(term[axis],deleted[axis]))
                         for axis in ('u','v','w'))
        return (-overlap, difference, index)
    return sorted((i for i in range(len(candidate['terms'])) if i != drop_term),key=score)[:count]


def build_local_cnf(candidate, rank=94, active_terms=None, drop_term=None,
                    support_mode='union', active_count=4):
    """Encode every coefficient with exactly ``rank`` retained product slots.

    Input must have rank+1 terms. ``active_terms`` refers to original source
    indices, excluding ``drop_term``. Frozen terms are fixed literal factors.
    In union mode, each mutable factor's coordinates are limited to the union
    of supports in the active terms and deleted term; full mode allows all.
    Returned dictionary contains clauses, nv, metadata and decoding state.
    """
    source = _normalize(candidate)
    n = source['dimension']
    width = n*n
    if type(rank) is not int or rank < 1 or len(source['terms']) != rank+1:
        raise ValueError('source must have exactly rank+1 terms')
    if drop_term is None:
        drop_term = min(range(rank+1),key=lambda i: math.prod(
            sum(source['terms'][i][a]) for a in ('u','v','w')))
    if type(drop_term) is not int or not 0 <= drop_term <= rank:
        raise ValueError('invalid deleted source index')
    if active_terms is None:
        active_terms = choose_active_terms(source,drop_term,active_count)
    active_terms = list(active_terms)
    if (not active_terms or len(set(active_terms)) != len(active_terms) or
            any(type(i) is not int or not 0 <= i <= rank or i == drop_term for i in active_terms)):
        raise ValueError('active terms must be distinct retained source indices')
    if support_mode not in ('union','full'):
        raise ValueError('support mode must be union or full')
    retained = [i for i in range(rank+1) if i != drop_term]
    frozen = [i for i in retained if i not in active_terms]
    residual = multiplication_tensor(n)
    for index in frozen:
        term = source['terms'][index]
        supports = [[i for i,v in enumerate(term[a]) if v] for a in ('u','v','w')]
        for a,b,c in itertools.product(*supports):
            residual[(a*width+b)*width+c] ^= 1
    support = {}
    for axis in ('u','v','w'):
        support[axis] = (list(range(width)) if support_mode == 'full' else
                         [j for j in range(width) if any(source['terms'][i][axis][j]
                          for i in active_terms+[drop_term])])
    cnf = CNF()
    variable_map = []
    factors = {}
    phases = []
    for index in active_terms:
        factors[index] = {}
        for axis in ('u','v','w'):
            factors[index][axis] = [0]*width
            for coordinate in support[axis]:
                var = cnf.variable()
                factors[index][axis][coordinate] = var
                variable_map.append({'variable':var,'source_term':index,
                                     'axis':axis,'coordinate':coordinate})
                phases.append(var if source['terms'][index][axis][coordinate] else -var)
    for a,b,c in itertools.product(range(width),repeat=3):
        monomials = [cnf.conjunction([factors[i]['u'][a],factors[i]['v'][b],factors[i]['w'][c]])
                     for i in active_terms]
        cnf.parity(monomials,residual[(a*width+b)*width+c])
    metadata = {'dimension':n,'field':2,'rank':rank,'source_term_count':rank+1,
                'coefficient_domain':[-1,0,1],'canonical_field_representatives':[0,1],
                'sign_identification':'-1 = 1 in characteristic 2',
                'drop_term':drop_term,'active_terms':active_terms,'frozen_terms':frozen,
                'support_mode':support_mode,'support':support,
                'tensor_equations':width**3,'variables':cnf.nv,
                'factor_variables':len(variable_map),'clauses':len(cnf.clauses),
                'scope':'local frozen-neighborhood; UNSAT does not imply rank94 nonexistence',
                'factor_variable_map':variable_map}
    return {'clauses':cnf.clauses,'nv':cnf.nv,'metadata':metadata,
            'source':source,'retained':retained,'phases':phases}


def decode_model(problem, model):
    true = {x for x in model if x > 0}
    candidate = {'dimension':problem['source']['dimension'],'field':2,
                 'terms':[copy.deepcopy(problem['source']['terms'][i]) for i in problem['retained']],
                 'metadata':{'method':'localized-gf2-sat','source_metadata':problem['source'].get('metadata',{})}}
    positions = {source:i for i,source in enumerate(problem['retained'])}
    # Every active coefficient outside the allowed support is frozen at zero.
    for index in problem['metadata']['active_terms']:
        candidate['terms'][positions[index]] = {a:[0]*(candidate['dimension']**2) for a in ('u','v','w')}
    for entry in problem['metadata']['factor_variable_map']:
        candidate['terms'][positions[entry['source_term']]][entry['axis']][entry['coordinate']] = int(entry['variable'] in true)
    return candidate


def _worker(problem, conflicts, connection):
    try:
        from pysat.solvers import Cadical195
        with Cadical195(bootstrap_with=problem['clauses']) as solver:
            solver.set_phases(problem['phases'])
            solver.conf_budget(conflicts)
            result = solver.solve_limited()
            connection.send({'status':'SAT' if result is True else 'UNSAT' if result is False else 'UNKNOWN',
                             'model':solver.get_model() if result is True else None,
                             'statistics':solver.accum_stats(),'solver':'CaDiCaL195'})
    except Exception as exc:
        connection.send({'status':'ERROR','error':f'{type(exc).__name__}: {exc}'})
    finally:
        connection.close()


def solve_local(problem, seconds=10, conflicts=10000):
    """Hard wall-clock bound includes solver import and initialization."""
    if not math.isfinite(seconds) or seconds <= 0 or type(conflicts) is not int or conflicts <= 0:
        raise ValueError('positive finite seconds and positive integer conflicts required')
    context = mp.get_context('fork')
    receiver,sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker,args=(problem,conflicts,sender))
    started = time.monotonic()
    process.start()
    sender.close()
    try:
        if receiver.poll(seconds):
            try:
                result = receiver.recv()
            except EOFError:
                result = {'status':'ERROR','error':'solver worker exited without a result'}
        else:
            result = {'status':'UNKNOWN','reason':'wall-clock budget reached'}
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join()
        receiver.close()
    result['elapsed_seconds'] = time.monotonic()-started
    result['conflict_budget'] = conflicts
    result['wall_budget_seconds'] = seconds
    if result['status'] == 'SAT':
        candidate = decode_model(problem,result.pop('model'))
        report = verify_candidate(candidate,random_trials=16)
        if not report['valid']:
            raise AssertionError('SAT assignment failed independent exact verification')
        result['candidate'],result['verification'] = candidate,report
    return result


def write_problem(problem,prefix):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True,exist_ok=True)
    with prefix.with_suffix('.cnf').open('w') as handle:
        handle.write(f"p cnf {problem['nv']} {len(problem['clauses'])}\n")
        for clause in problem['clauses']:
            handle.write(' '.join(map(str,clause))+' 0\n')
    prefix.with_suffix('.map.json').write_text(json.dumps(problem['metadata'],indent=2)+'\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output-prefix',default='artifacts/local-sat')
    parser.add_argument('--rank',type=int,default=94)
    parser.add_argument('--drop-term',type=int)
    parser.add_argument('--active-count',type=int,default=4)
    parser.add_argument('--active-terms',help='comma-separated original term indices')
    parser.add_argument('--support',choices=['union','full'],default='union')
    parser.add_argument('--seconds',type=float,default=10)
    parser.add_argument('--conflicts',type=int,default=10000)
    args = parser.parse_args(argv)
    candidate = json.loads(Path(args.input).read_text())
    active = None if args.active_terms is None else [int(x) for x in args.active_terms.split(',')]
    problem = build_local_cnf(candidate,rank=args.rank,active_terms=active,drop_term=args.drop_term,
                              support_mode=args.support,active_count=args.active_count)
    write_problem(problem,args.output_prefix)
    result = solve_local(problem,seconds=args.seconds,conflicts=args.conflicts)
    prefix = Path(args.output_prefix)
    if result['status']=='SAT':
        cert = result.pop('candidate')
        prefix.with_suffix('.candidate.json').write_text(json.dumps(cert,indent=2)+'\n')
        write_standalone_verifier(prefix.with_suffix('.verify.py'))
        prefix.with_suffix('.verification.json').write_text(json.dumps(result['verification'],indent=2)+'\n')
    result['problem'] = {k:v for k,v in problem['metadata'].items() if k!='factor_variable_map'}
    prefix.with_suffix('.result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status'] in ('SAT','UNSAT','UNKNOWN') else 2


if __name__=='__main__':
    raise SystemExit(main())
