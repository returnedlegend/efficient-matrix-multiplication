import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from mmsearch.free_factor_kernel_wide import native_input
from mmsearch.free_factor_sat import build_system
from mmsearch.kernel_triple_catalog import ordinal, parse_catalog, stream_bytes, stream_cursor, unrank
from mmsearch.search import encode_candidate, naive_terms

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT/'native/free_factor_triple_block_worker_wide_v2'


class TripleCatalogTests(unittest.TestCase):
    def test_all_small_rank_unrank_and_excluded_cursors(self):
        rng = random.Random(423)
        for count in range(3, 15):
            all_rows = list(itertools.combinations(range(count), 3))
            for begin in range(count-1):
                for end in range(begin, count-1):
                    rows = [t for t in all_rows if begin <= t[0] < end]
                    excluded = rng.sample(rows, min(len(rows), 4))
                    raw, info = stream_bytes(count, begin, end, excluded)
                    self.assertEqual(parse_catalog(raw, count), info)
                    kept = [t for t in rows if t not in excluded]
                    self.assertEqual(info['selected'], len(kept))
                    for position, triple in enumerate(rows):
                        self.assertEqual(ordinal(count, begin, triple), position)
                        self.assertEqual(unrank(count, begin, end, position), triple)
                    for row in sorted(set((0, len(kept)//2, len(kept)))):
                        expected = kept[row] if row < len(kept) else (-1, -1, -1)
                        base, actual = stream_cursor(count, begin, end, excluded, row)
                        self.assertEqual(actual, expected)
                        self.assertEqual(base, rows.index(expected) if row < len(kept) else len(rows))

    @unittest.skipUnless(BINARY.exists(), 'stream worker not built')
    def test_native_stream_cursor_equivalence_and_resume(self):
        system = build_system(list(naive_terms(2))+[(3, b, 0) for b in range(1, 16)],
                              2, 'uv', encode_candidate(naive_terms(2), 2))
        ids = {tuple(pair): g for g, pair in enumerate(system['pairs'])}
        lines = [(a, b, a ^ b) for a in range(1, 16) for b in range(a+1, 16) if a ^ b > b][:20]
        circuits = [dict(class_id=0, support=[ids[3, b] for b in line]) for line in lines]
        base = [t for t in itertools.combinations(range(20), 3) if 1 <= t[0] < 8]
        excluded = sorted(set(base[:5]+base[-5:]+base[::17]))
        kept = [t for t in base if t not in excluded]
        raw, info = stream_bytes(20, 1, 8, excluded)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'input'; source.write_bytes(native_input(system, circuits))
            catalog = root/'catalog'; catalog.write_bytes(raw)
            prefix = root/'out'
            def run(start=0, max_rows=0, seconds='2'):
                done = subprocess.run([str(BINARY), '--input', str(source), '--catalog', str(catalog),
                    '--output', str(prefix), '--target', '0', '--seconds', seconds,
                    '--start-row', str(start), '--max-triples', str(max_rows)],
                    capture_output=True, text=True, timeout=4)
                self.assertEqual(done.returncode, 0, done.stderr)
                return json.loads(prefix.with_suffix('.stats.json').read_text())
            rng = random.Random(42)
            for start in [0, 1, 2, len(kept)-1, len(kept)] + rng.sample(range(len(kept)), 30):
                stats = run(start, seconds='0')
                cursor, triple = stream_cursor(20, 1, 8, excluded, start)
                self.assertEqual(stats['next_base_ordinal'], cursor)
                self.assertEqual(tuple(stats[k] for k in ('next_i', 'next_j', 'next_k')), triple)
                self.assertEqual(stats['triples_total'], len(kept))
            first = run(max_rows=7)
            self.assertEqual((first['status'], first['next_row']), ('UNKNOWN', 7))
            resumed = run(start=7)
            self.assertEqual((resumed['status'], resumed['next_row']), ('NO_TARGET', len(kept)))
            self.assertEqual(resumed['triples_considered']+7, len(kept))
            streamed = run()
            catalog.write_text(f'MMKTRIPLES1 {len(kept)}\n'+''.join(' '.join(map(str,t))+'\n' for t in kept))
            explicit = run()
            for key in ('triples_total', 'triples_considered', 'bound_pruned', 'exact_evaluated', 'candidate_assignments'):
                self.assertEqual(streamed[key], explicit[key])


if __name__ == '__main__':
    unittest.main()
