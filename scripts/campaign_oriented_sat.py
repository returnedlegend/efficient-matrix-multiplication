"""Orientation-complete p1/p2 filtering; fresh campaign state, frozen imports."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.koszul_orientations import orientation_bounds
from scripts import campaign_koszul_p2_sat as p2


class OrientedCoreCache(p2.HigherCoreCache):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics.update(orientation_evaluations=0, orientation_rejections=0,
                            orientation_skipped_after_original=0, orientation_seconds=0)

    def get(self, source, selected):
        value, report = super().get(source, selected)
        if 'ordered_modes' not in report:
            target = len(selected)-1
            if report['tensor_rank_lower_bound'] > target:
                ordered = dict(status='NOT_NEEDED_ORIGINAL_REJECTED', tensor_rank_lower_bound=0,
                               rejected=False, elapsed_seconds=0)
                self.metrics['orientation_skipped_after_original'] += 1
            else:
                permutations = []
                for mode in self.modes:
                    other = [axis for axis in range(3) if axis != mode]
                    permutations.append((mode, other[1], other[0]))
                ordered = orientation_bounds(value[1], value[2], target=target,
                                               permutations=permutations, **self.caps)
                self.metrics['orientation_evaluations'] += 1
                self.metrics['orientation_rejections'] += int(ordered['rejected'])
                self.metrics['orientation_seconds'] += ordered['elapsed_seconds']
            report = dict(report, original_order_lower_bound=report['tensor_rank_lower_bound'],
                ordered_modes=ordered,
                tensor_rank_lower_bound=max(report['tensor_rank_lower_bound'], ordered['tensor_rank_lower_bound']),
                elapsed_seconds=report['elapsed_seconds']+ordered['elapsed_seconds'])
            self.entries[next(reversed(self.entries))] = (value, report)
        return value, report


class OrientedCampaign(p2.HigherCampaign):
    def __init__(self, args, cache):
        p2.p1.base.Campaign.__init__(self, args)
        identity = dict(backend=args.backend, symmetry=args.compact_symmetry,
            modes=list(cache.modes), version='all-ordered-modes-p1-p2-v1', caps=cache.caps)
        if self.state.get('koszul_identity', identity) != identity or (
                'koszul_identity' not in self.state and self.state['attempts']):
            raise ValueError('ordered modes need a separate directory with matching identity')
        self.state['koszul_identity'] = identity
        self.state['encoding'] = 'oriented-koszul-p1-p2-exact-image-'+args.backend+'-v1'
        self.state['symmetry'] = args.compact_symmetry
        self.cache = cache
        self.prior_metrics = {key: self.state['counters'].get(key, 0) for key in cache.metrics}

    def emit(self, event):
        if event.get('event') == 'koszul_reject':
            report = event['patch']['koszul']
            target = event['patch']['active_count']
            decisive = report.get('ordered_modes', {}).get('decisive')
            if decisive is None:
                higher = report.get('p2', {})
                candidates = higher.get('bounds', []) if higher.get('rejected') else report['bounds']
                decisive = next(item for item in candidates if item.get('tensor_rank_lower_bound', 0) > target)
                axis = decisive['mode']
                decisive = dict(decisive, orientation=[axis]+[i for i in range(3) if i != axis])
            degree = decisive['exterior_degree']
            event = dict(event, orientation=decisive['orientation'], exterior_degree=degree,
                map_rank=decisive['matrix_rank'], rank_threshold=target*decisive['rank_one_contribution'],
                proof=f'rank(Koszul_p{degree}(transpose(T))) <= tensor_rank(T)*binomial(dim(A)-1,{degree})')
            return p2.p1.base.Campaign.emit(self, event)
        return super().emit(event)


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--backend', choices=['cadical', 'xor'], default='cadical')
    parser.add_argument('--symmetry', choices=['none', 'u-lex'], default='u-lex')
    parser.add_argument('--koszul-modes', choices=['all', '0', '1', '2'], default='all')
    parser.add_argument('--p2-max-dimension', type=int, default=14)
    parser.add_argument('--p2-max-rows', type=int, default=5000)
    parser.add_argument('--p2-max-columns', type=int, default=5000)
    options, remaining = parser.parse_known_args(argv)
    args = p2.p1.base.arguments(remaining)
    args.backend, args.compact_symmetry = options.backend, options.symmetry
    if args.output_dir == Path('research/campaign/sat'):
        args.output_dir = Path('research/campaign/oriented-'+options.backend)
    cache = OrientedCoreCache((0, 1, 2) if options.koszul_modes == 'all' else (int(options.koszul_modes),),
        max_dimension=options.p2_max_dimension, max_rows=options.p2_max_rows,
        max_columns=options.p2_max_columns)
    original = p2.p1.cached_encoder(cache, options.backend, options.symmetry)
    def encoder(*args, **kwargs):
        problem = original(*args, **kwargs)
        problem['metadata']['encoding'] = 'oriented-koszul-p1-p2-exact-image-'+options.backend+'-v1'
        return problem
    p2.p1.base.build_local_cnf = encoder
    if options.backend == 'xor':
        from mmsearch.xor_sat import solve_local, write_problem
        from scripts.campaign_xor_sat import xor_digest
        p2.p1.base.solve_local, p2.p1.base.write_problem, p2.p1.base.cnf_digest = solve_local, write_problem, xor_digest
    return OrientedCampaign(args, cache).run()


if __name__ == '__main__':
    main()
