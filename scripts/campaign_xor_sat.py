"""Bounded single-thread native XOR campaign; separate state from CNF runs.

Dependency: pycryptosat==5.17.0. If installed in .xor-deps, launch with
PYTHONPATH=.xor-deps:. taskset -c 2 python scripts/campaign_xor_sat.py ...
"""
from __future__ import annotations

import argparse
import functools
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.xor_sat import build_xor_cnf, solve_local, write_problem
from scripts.campaign_compact_sat import CompactCampaign
from scripts import campaign_sat as base

ENCODING = 'exact-multilinear-image-native-xor-v1'


class XorCampaign(CompactCampaign):
    def __init__(self, args):
        base.Campaign.__init__(self, args)
        encoding = self.state.get('encoding')
        if encoding not in (None, ENCODING) or (encoding is None and self.state['attempts']):
            raise ValueError('native XOR needs a separate output directory')
        self.state['encoding'] = ENCODING
        if self.state.get('symmetry', args.compact_symmetry) != args.compact_symmetry:
            raise ValueError('symmetry differs from existing manifest')
        self.state['symmetry'] = args.compact_symmetry


def xor_digest(problem):
    value = hashlib.sha256()
    value.update(f"{problem['nv']}\n".encode())
    for clause in problem['clauses']:
        value.update((' '.join(map(str, clause))+' 0\n').encode())
    for variables, required in problem['xors']:
        value.update(('x '+str(int(required))+' '+' '.join(map(str, variables))+' 0\n').encode())
    return value.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--symmetry', choices=['none', 'u-lex'], default='none')
    options, remaining = parser.parse_known_args(argv)
    args = base.arguments(remaining)
    args.compact_symmetry = options.symmetry
    if args.output_dir == Path('research/campaign/sat'):
        args.output_dir = Path('research/campaign/xor-sat')
    base.build_local_cnf = functools.partial(build_xor_cnf, symmetry=options.symmetry)
    base.solve_local = solve_local
    base.write_problem = write_problem
    base.cnf_digest = xor_digest
    return XorCampaign(args).run()


if __name__ == '__main__':
    main()
