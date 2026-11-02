"""Bounded SAT campaign using exact multilinear-image preprocessing.

Uses the frozen campaign scheduler with a separate encoder and output directory.
All ambient tensor coefficients are implied by the transformed constraints and
are checked independently after decoding. CLI flags match campaign_sat.py.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import functools
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.compact_sat import build_compact_cnf
from scripts import campaign_sat as base


class CompactCampaign(base.Campaign):
    def __init__(self, args):
        super().__init__(args)
        encoding = self.state.get('encoding')
        if encoding not in (None, 'exact-multilinear-image-v1') or (encoding is None and self.state['attempts']):
            raise ValueError('compact encoder needs a separate output directory from baseline')
        self.state['encoding'] = 'exact-multilinear-image-v1'
        prior = self.state.get('symmetry', args.compact_symmetry)
        if prior != args.compact_symmetry:
            raise ValueError('symmetry setting differs from the existing manifest')
        self.state['symmetry'] = args.compact_symmetry

    def next_patch(self):
        # Full and support-union branches have the same image-projected core.
        # Collapse them before encoding, preserving unknown escalation records.
        for _ in range(20):
            patch = super().next_patch()
            if patch is None or patch['support_mode'] == 'image':
                return patch
            self.state['patches'].pop(patch['patch_id'])
            patch['support_mode'] = 'image'
            key = base.digest(dict(source=patch['source_sha256'],
                selected=sorted(patch['active_terms']+[patch['drop_term']]), support='image'))
            if key in self.state['patches']:
                self.increment('duplicate_patches')
                continue
            patch['patch_id'] = key
            self.state['patches'][key] = patch
            return patch
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--symmetry', choices=['none', 'u-lex'], default='none')
    compact, remaining = parser.parse_known_args(argv)
    args = base.arguments(remaining)
    args.compact_symmetry = compact.symmetry
    if args.output_dir == Path('research/campaign/sat'):
        args.output_dir = Path('research/campaign/compact-sat')
    # Injection affects only this interpreter; baseline files/process are frozen.
    base.build_local_cnf = functools.partial(build_compact_cnf, symmetry=compact.symmetry)
    return CompactCampaign(args).run()


if __name__ == '__main__':
    main()
