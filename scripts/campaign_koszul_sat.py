"""Exact Koszul-filtered compact SAT campaign, with CNF or native XOR backend.

Flags match campaign_sat.py, plus --backend cadical|xor, --symmetry none|u-lex,
and --koszul-modes all|0|1|2. Use a separate output directory for each branch.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path
import sys
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch import compact_sat
from mmsearch.koszul import koszul_bounds
from scripts.campaign_compact_sat import CompactCampaign
from scripts import campaign_sat as base


class CoreCache:
    def __init__(self, modes=(0, 1, 2), capacity=8):
        self.entries = OrderedDict()
        self.capacity = capacity
        self.modes = modes
        self.hits = self.misses = 0

    def get(self, source, selected):
        key = (base.digest(dict(dimension=source['dimension'], field=source['field'], terms=source['terms'])),
               tuple(sorted(selected)))
        if key in self.entries:
            self.hits += 1
            self.entries.move_to_end(key)
        else:
            self.misses += 1
            value = compact_sat.compress_residual(source, selected)
            report = koszul_bounds(value[1], value[2], modes=self.modes)
            self.entries[key] = (value, report)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
        return self.entries[key]

    def compression(self, source, selected):
        return self.get(source, selected)[0]


class KoszulCampaign(CompactCampaign):
    def __init__(self, args, cache):
        base.Campaign.__init__(self, args)
        identity = dict(backend=args.backend, symmetry=args.compact_symmetry,
                        modes=list(cache.modes), version='koszul-p1-exact-v1')
        if self.state.get('koszul_identity', identity) != identity or (
                'koszul_identity' not in self.state and self.state['attempts']):
            raise ValueError('Koszul branch needs a separate output directory with matching backend/symmetry/modes')
        self.state['koszul_identity'] = identity
        self.state['encoding'] = 'koszul-filtered-exact-image-'+args.backend+'-v1'
        self.state['symmetry'] = args.compact_symmetry
        self.cache = cache

    def next_patch(self):
        started = time.monotonic()
        for _ in range(100):
            patch = super().next_patch()
            if patch is None:
                return None
            source = self.stream(patch['source_sha256']).source
            prepared_at = time.monotonic()
            misses = self.cache.misses
            _, raw = self.cache.get(source, patch['active_terms']+[patch['drop_term']])
            report = dict(raw, target=patch['active_count'],
                          rejected=raw['tensor_rank_lower_bound'] > patch['active_count'],
                          preprocessing_seconds=time.monotonic()-prepared_at,
                          core_cache_hit=self.cache.misses == misses)
            patch['koszul'] = report
            self.increment('koszul_checked')
            self.increment('koszul_preprocessing_seconds', report['preprocessing_seconds'])
            if not report['rejected']:
                self.increment('koszul_passed')
                return patch
            patch['status'] = 'KOSZUL_REJECTED'
            self.increment('koszul_rejected')
            self.emit(dict(event='koszul_reject', status='LOCAL_UNSAT_BOUND', patch=dict(patch),
                source_file_sha256=self.state['sources'][patch['source_sha256']]['file_sha256'],
                proof='rank(Koszul_p1(T)) <= tensor_rank(T)*(dim(A)-1)', scope=report['scope']))
            if time.monotonic()-started > 1:
                return None
        return None


def cached_encoder(cache, backend, symmetry):
    original = compact_sat.build_compact_cnf
    def encode(*args, **kwargs):
        instances = []
        namespace = dict(original.__globals__, compress_residual=cache.compression)
        if backend == 'xor':
            from mmsearch.xor_sat import XorCNF
            def factory():
                cnf = XorCNF()
                instances.append(cnf)
                return cnf
            namespace['CNF'] = factory
        encoder = types.FunctionType(original.__code__, namespace, original.__name__,
                                     original.__defaults__, original.__closure__)
        problem = encoder(*args, symmetry=symmetry, **kwargs)
        if backend == 'xor':
            problem['xors'] = instances[0].xors
            problem['metadata'].update(native_xor_equations=len(problem['xors']), solver_threads=1,
                phase_hint_policy='source phases retained for provenance; CryptoMiniSat default phases')
        source = problem['source']
        _, report = cache.get(source, problem['metadata']['active_terms']+[problem['metadata']['drop_term']])
        target = len(problem['metadata']['active_terms'])
        problem['metadata']['koszul'] = dict(report, target=target,
            rejected=report['tensor_rank_lower_bound'] > target)
        problem['metadata']['encoding'] = 'koszul-filtered-exact-image-'+backend+'-v1'
        problem['metadata']['core_cache_hits'] = cache.hits
        return problem
    return encode


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--backend', choices=['cadical', 'xor'], default='cadical')
    parser.add_argument('--symmetry', choices=['none', 'u-lex'], default='u-lex')
    parser.add_argument('--koszul-modes', choices=['all', '0', '1', '2'], default='all')
    options, remaining = parser.parse_known_args(argv)
    args = base.arguments(remaining)
    args.compact_symmetry, args.backend = options.symmetry, options.backend
    if args.output_dir == Path('research/campaign/sat'):
        args.output_dir = Path('research/campaign/koszul-'+options.backend)
    cache = CoreCache((0, 1, 2) if options.koszul_modes == 'all' else (int(options.koszul_modes),))
    base.build_local_cnf = cached_encoder(cache, options.backend, options.symmetry)
    if options.backend == 'xor':
        from mmsearch.xor_sat import solve_local, write_problem
        from scripts.campaign_xor_sat import xor_digest
        base.solve_local, base.write_problem, base.cnf_digest = solve_local, write_problem, xor_digest
    return KoszulCampaign(args, cache).run()


if __name__ == '__main__':
    main()
