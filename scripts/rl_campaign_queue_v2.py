#!/usr/bin/env python3
"""Queue adapter adding nested candidate reports to the frozen supervisor.

Only scheduling is stopped; exact verification and novelty review belong to the
campaign owner. The base CLI retains its lock, restart state, and worker policy.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


_BASE_PATH = Path(__file__).with_name('rl_campaign_queue.py')
_SPEC = importlib.util.spec_from_file_location('_rl_campaign_queue_v2_base', _BASE_PATH)
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)


def essential_rank(value):
    """Validate an explicit 5x5 F2 report and count canonical essential terms.

    Accept the public binary dense vectors and internal 25-bit triples. This
    checks representation only, without asserting exact multiplication.
    """
    if (type(value.get('dimension')) is not int or value['dimension'] != 5
            or type(value.get('field')) is not int or value['field'] != 2
            or not isinstance(value.get('terms'), list)):
        raise ValueError('expected explicit dimension 5 field 2 terms')
    terms = set()
    for item in value['terms']:
        if isinstance(item, dict):
            if set(item) != {'u', 'v', 'w'}:
                raise ValueError('expected exactly u, v, w')
            factors = []
            for axis in ('u', 'v', 'w'):
                vector = item[axis]
                if (not isinstance(vector, list) or len(vector) != 25
                        or any(type(x) is not int or x not in (0, 1) for x in vector)):
                    raise ValueError('expected 25 binary integer entries')
                factors.append(sum(x << i for i, x in enumerate(vector)))
        elif isinstance(item, list) and len(item) == 3:
            if any(type(x) is not int or not 0 <= x < (1 << 25) for x in item):
                raise ValueError('expected three 25-bit integer masks')
            factors = item
        else:
            raise ValueError('invalid term')
        term = tuple(factors)
        if not all(term):
            continue
        if term in terms:
            terms.remove(term)
        else:
            terms.add(term)
    return len(terms)


class Supervisor(base.Supervisor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_dependency_sha256 = self.code_hash
        self.code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.state['base_dependency_sha256'] = self.base_dependency_sha256

    def record(self, event, **values):
        values['base_dependency_sha256'] = self.base_dependency_sha256
        super().record(event, **values)

    def reported_target(self, target):
        report = super().reported_target(target)
        if report:
            return report
        paths = set(self.directory.rglob('FOUND.json'))
        paths.update(self.directory.glob('**/records/*.json'))
        for path in sorted(paths):
            try:
                value, _ = base.load_json(path)
                rank = essential_rank(value)
                if 0 < rank <= target:
                    return (f'target reported: {path.relative_to(self.directory)}; '
                            f'essential canonical terms={rank}; unverified by supervisor')
            except (OSError, ValueError, TypeError, AttributeError, RecursionError):
                continue
        return None


def main():
    base.Supervisor = Supervisor
    base.main()


if __name__ == '__main__':
    main()
