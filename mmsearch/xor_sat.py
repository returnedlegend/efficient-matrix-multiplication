"""Optional CryptoMiniSat backend for exact image-projected local GF(2) SAT.

Install pycryptosat==5.17.0 separately. Native XOR equations coexist with CNF
AND gates. UNSAT concerns only this frozen neighborhood, never global rank.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
from pathlib import Path
import signal
import time
import types

from . import compact_sat
from .sat import CNF, decode_model
from .verify import verify_candidate, write_standalone_verifier


class XorCNF(CNF):
    def __init__(self):
        super().__init__()
        self.xors = []

    def parity(self, variables, required):
        odd = set()
        required = bool(required)
        for literal in variables:
            if literal < 0:
                required = not required
            variable = abs(literal)
            if variable:
                if variable in odd:
                    odd.remove(variable)
                else:
                    odd.add(variable)
        values = sorted(odd)
        if values:
            self.xors.append((values, required))
        elif required:
            self.clauses.append([])


def build_xor_cnf(*args, **kwargs):
    instances = []
    def factory():
        cnf = XorCNF()
        instances.append(cnf)
        return cnf
    # A private function namespace avoids mutating the existing encoder module.
    original = compact_sat.build_compact_cnf
    namespace = dict(original.__globals__, CNF=factory)
    encoder = types.FunctionType(original.__code__, namespace, original.__name__,
                                 original.__defaults__, original.__closure__)
    problem = encoder(*args, **kwargs)
    problem['xors'] = instances[0].xors
    problem['metadata'].update(encoding='exact-multilinear-image-native-xor-v1',
        native_xor_equations=len(problem['xors']), solver_threads=1,
        phase_hint_policy='source phases retained for provenance; CryptoMiniSat default phases')
    return problem


def validate_model(problem, model):
    """Check every gate and native parity before trusting model decoding."""
    true = {literal for literal in model if literal > 0}
    if any(not any((abs(literal) in true) == (literal > 0) for literal in clause)
           for clause in problem['clauses']):
        raise AssertionError('CryptoMiniSat model violates a CNF clause')
    if any(bool(sum(variable in true for variable in variables) % 2) != required
           for variables, required in problem['xors']):
        raise AssertionError('CryptoMiniSat model violates a native XOR equation')


def _worker(problem, seconds, conflicts, connection):
    try:
        import pycryptosat
        solver = pycryptosat.Solver(threads=1, verbose=0, time_limit=seconds,
                                    confl_limit=conflicts)
        # Ensure even an unconstrained final variable is represented in models.
        if problem['nv']:
            solver.add_clause([problem['nv'], -problem['nv']])
        for clause in problem['clauses']:
            solver.add_clause(clause)
        for variables, required in problem['xors']:
            solver.add_xor_clause(variables, required)
        result, assignment = solver.solve(time_limit=seconds, confl_limit=conflicts)
        model = ([i if value else -i for i, value in enumerate(assignment[1:], 1)]
                 if result is True else None)
        connection.send(dict(status='SAT' if result is True else 'UNSAT' if result is False else 'UNKNOWN',
            model=model, solver='CryptoMiniSat', pycryptosat_version=pycryptosat.__version__,
            solver_threads=1))
    except Exception as exc:
        connection.send(dict(status='ERROR', error=f'{type(exc).__name__}: {exc}'))
    finally:
        connection.close()


def _worker_entry(*args):
    # Parent campaign stop handlers survive fork but are not worker shutdown
    # handlers. Reset before imports/solver setup, including patched workers.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    _worker(*args)


def solve_local(problem, seconds=10, conflicts=10000):
    """Hard wall bound includes import/load; exact verification follows solving.

    CryptoMiniSat also receives the conflict budget and a solver time limit.
    The parent terminates the child at the hard wall limit, including setup.
    """
    if not math.isfinite(seconds) or seconds <= 0 or type(conflicts) is not int or conflicts <= 0:
        raise ValueError('positive finite seconds and positive integer conflicts required')
    context = mp.get_context('fork')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker_entry, args=(problem, seconds, conflicts, sender))
    started = time.monotonic()
    process.start()
    sender.close()
    try:
        remaining = max(0, seconds-(time.monotonic()-started))
        if receiver.poll(remaining):
            try:
                result = receiver.recv()
            except EOFError:
                result = dict(status='ERROR', error='solver worker exited without a result')
        else:
            result = dict(status='UNKNOWN', reason='wall-clock budget reached')
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=0.1)
        if process.is_alive():
            process.kill()
            process.join()
        receiver.close()
    result.update(elapsed_seconds=time.monotonic()-started,
                  conflict_budget=conflicts, wall_budget_seconds=seconds, solver_threads=1)
    if result['status'] == 'SAT':
        model = result.pop('model')
        validate_model(problem, model)
        candidate = decode_model(problem, model)
        report = verify_candidate(candidate, random_trials=16)
        if not report['valid'] or report['rank'] != problem['metadata']['rank']:
            raise AssertionError('native XOR model failed independent exact tensor verification')
        candidate['metadata']['method'] = 'localized-gf2-native-xor-sat'
        result.update(candidate=candidate, verification=report)
    else:
        result.pop('model', None)
    return result


def write_problem(problem, prefix):
    """Write CryptoMiniSat extended DIMACS, including every native XOR."""
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with prefix.with_suffix('.cnf').open('w') as handle:
        handle.write(f"p cnf {problem['nv']} {len(problem['clauses'])+len(problem['xors'])}\n")
        for clause in problem['clauses']:
            handle.write(' '.join(map(str, clause))+' 0\n')
        for variables, required in problem['xors']:
            literals = list(variables)
            if not required:
                literals[0] *= -1
            handle.write('x'+' '.join(map(str, literals))+' 0\n')
    prefix.with_suffix('.map.json').write_text(json.dumps(problem['metadata'], indent=2)+'\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-prefix', default='artifacts/local-xor-sat')
    parser.add_argument('--rank', type=int, default=92)
    parser.add_argument('--drop-term', type=int, default=0)
    parser.add_argument('--active-count', type=int, default=5)
    parser.add_argument('--active-terms')
    parser.add_argument('--symmetry', choices=['none', 'u-lex'], default='none')
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--conflicts', type=int, default=10000)
    args = parser.parse_args(argv)
    active = None if args.active_terms is None else [int(x) for x in args.active_terms.split(',')]
    problem = build_xor_cnf(json.loads(Path(args.input).read_text()), rank=args.rank,
        drop_term=args.drop_term, active_terms=active, active_count=args.active_count,
        symmetry=args.symmetry)
    write_problem(problem, args.output_prefix)
    result = solve_local(problem, seconds=args.seconds, conflicts=args.conflicts)
    prefix = Path(args.output_prefix)
    if result['status'] == 'SAT':
        prefix.with_suffix('.candidate.json').write_text(json.dumps(result.pop('candidate'), indent=2)+'\n')
        write_standalone_verifier(prefix.with_suffix('.verify.py'))
        prefix.with_suffix('.verification.json').write_text(json.dumps(result['verification'], indent=2)+'\n')
    result['problem'] = {k: v for k, v in problem['metadata'].items() if k != 'factor_variable_map'}
    prefix.with_suffix('.result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, sort_keys=True))
    return 2 if result['status'] == 'ERROR' else 0


if __name__ == '__main__':
    raise SystemExit(main())
