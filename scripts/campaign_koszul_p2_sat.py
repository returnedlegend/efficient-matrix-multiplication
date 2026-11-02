"""Optional p2 filtering after p1, using separate frozen-source campaign state."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.koszul_p2 import koszul_p2_bounds
from scripts import campaign_koszul_sat as p1


class HigherCoreCache(p1.CoreCache):
    def __init__(self, modes=(0, 1, 2), capacity=8, max_dimension=14, max_rows=5000, max_columns=5000):
        super().__init__(modes, capacity)
        self.caps = dict(max_dimension=max_dimension, max_rows=max_rows, max_columns=max_columns)
        if any(type(value) is not int or value < 0 for value in self.caps.values()):
            raise ValueError('p2 cost caps must be nonnegative integers')
        self.metrics = dict(p2_evaluations=0, p2_rejections=0, p2_skipped_after_p1=0,
                            p2_all_modes_skipped=0, p2_seconds=0)

    def get(self, source, selected):
        value, report = super().get(source, selected)
        if 'p2' not in report:
            target = len(selected)-1
            if report['tensor_rank_lower_bound'] > target:
                higher = dict(status='NOT_NEEDED_P1_REJECTED', tensor_rank_lower_bound=0,
                              rejected=False, elapsed_seconds=0)
                self.metrics['p2_skipped_after_p1'] += 1
            else:
                higher = koszul_p2_bounds(value[1], value[2], target=target, modes=self.modes, **self.caps)
                self.metrics['p2_evaluations'] += 1
                self.metrics['p2_rejections'] += int(higher['rejected'])
                self.metrics['p2_all_modes_skipped'] += int(higher['computed_modes'] == 0)
                self.metrics['p2_seconds'] += higher['elapsed_seconds']
            report = dict(report, p1_tensor_rank_lower_bound=report['tensor_rank_lower_bound'],
                p2=higher, exterior_degrees=[1, 2],
                tensor_rank_lower_bound=max(report['tensor_rank_lower_bound'], higher['tensor_rank_lower_bound']),
                elapsed_seconds=report['elapsed_seconds']+higher['elapsed_seconds'])
            # Parent get() has just moved this exact core entry to the end.
            key = next(reversed(self.entries))
            self.entries[key] = (value, report)
        return value, report


class HigherCampaign(p1.KoszulCampaign):
    def __init__(self, args, cache):
        p1.base.Campaign.__init__(self, args)
        identity = dict(backend=args.backend, symmetry=args.compact_symmetry,
                        modes=list(cache.modes), version='koszul-p1-p2-exact-v1', caps=cache.caps)
        if self.state.get('koszul_identity', identity) != identity or (
                'koszul_identity' not in self.state and self.state['attempts']):
            raise ValueError('p1+p2 branch needs its own output directory with matching identity')
        self.state['koszul_identity'] = identity
        self.state['encoding'] = 'koszul-p1-p2-filtered-exact-image-'+args.backend+'-v1'
        self.state['symmetry'] = args.compact_symmetry
        self.cache = cache
        self.prior_metrics = {key: self.state['counters'].get(key, 0) for key in cache.metrics}

    def emit(self, event):
        if event.get('event') == 'koszul_reject':
            degree = 2 if event['patch']['koszul'].get('p2', {}).get('rejected') else 1
            event = dict(event, exterior_degree=degree,
                proof=('rank(Koszul_p2(T)) <= tensor_rank(T)*binomial(dim(A)-1,2)' if degree == 2
                       else 'rank(Koszul_p1(T)) <= tensor_rank(T)*(dim(A)-1)'))
        return super().emit(event)

    def next_patch(self):
        try:
            return super().next_patch()
        finally:
            for key, value in self.cache.metrics.items():
                self.state['counters'][key] = self.prior_metrics[key]+value


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--backend', choices=['cadical', 'xor'], default='cadical')
    parser.add_argument('--symmetry', choices=['none', 'u-lex'], default='u-lex')
    parser.add_argument('--koszul-modes', choices=['all', '0', '1', '2'], default='all')
    parser.add_argument('--p2-max-dimension', type=int, default=14)
    parser.add_argument('--p2-max-rows', type=int, default=5000)
    parser.add_argument('--p2-max-columns', type=int, default=5000)
    options, remaining = parser.parse_known_args(argv)
    args = p1.base.arguments(remaining)
    args.backend, args.compact_symmetry = options.backend, options.symmetry
    if args.output_dir == Path('research/campaign/sat'):
        args.output_dir = Path('research/campaign/koszul-p2-'+options.backend)
    cache = HigherCoreCache((0, 1, 2) if options.koszul_modes == 'all' else (int(options.koszul_modes),),
        max_dimension=options.p2_max_dimension, max_rows=options.p2_max_rows,
        max_columns=options.p2_max_columns)
    original = p1.cached_encoder(cache, options.backend, options.symmetry)
    def encoder(*args, **kwargs):
        problem = original(*args, **kwargs)
        problem['metadata']['encoding'] = 'koszul-p1-p2-filtered-exact-image-'+options.backend+'-v1'
        return problem
    p1.base.build_local_cnf = encoder
    if options.backend == 'xor':
        from mmsearch.xor_sat import solve_local, write_problem
        from scripts.campaign_xor_sat import xor_digest
        p1.base.solve_local, p1.base.write_problem, p1.base.cnf_digest = solve_local, write_problem, xor_digest
    return HigherCampaign(args, cache).run()


if __name__ == '__main__':
    main()
