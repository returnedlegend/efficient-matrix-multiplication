"""Tiny independent stdlib oracle: exhaustive support spans, no production imports.

Brute rank-one endpoint enumeration is intentional here and restricted to tiny
controls; it is not the proposed production low-dimensional factorization code.
"""
import collections
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import time


def points(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length()-1
        mask ^= bit


def span(values):
    out = {0}
    for v in values:
        out |= {x ^ v for x in out}
    return frozenset(out)


def independent(values):
    basis, seen = [], {0}
    for x in values:
        if x not in seen:
            basis.append(x)
            seen |= {y ^ x for y in seen}
    return basis


def matrix_rank(x, rows, cols):
    pivots = {}
    for i in range(rows):
        r = (x >> (i*cols)) & ((1 << cols)-1)
        while r:
            p = r.bit_length()-1
            if p in pivots: r ^= pivots[p]
            else: pivots[p] = r; break
    return len(pivots)


def rankone_points(rows, cols):
    return sorted({sum(((u >> i)&1)*v << (i*cols) for i in range(rows))
                   for u in range(1,1 << rows) for v in range(1,1 << cols)})


@lru_cache(None)
def splits(d, rows, cols):
    assert matrix_rank(d, rows, cols) == 2
    one = set(rankone_points(rows, cols))
    answer = tuple((p, p ^ d) for p in sorted(one) if p < p ^ d and p ^ d in one)
    assert len(answer) == 3
    return answer


def edge_decision(S, rows, cols):
    S = span(S)
    d = len(S).bit_length()-1
    inside = sorted(x for x in S if matrix_rank(x, rows, cols) == 1)
    B0 = span(inside)
    buckets = collections.defaultdict(dict)
    for x in sorted(S):
        if matrix_rank(x, rows, cols) != 2: continue
        for p, q in splits(x, rows, cols):
            coset = min(p ^ s for s in S)
            assert min(q ^ s for s in S) == coset
            if coset == 0: continue  # Both endpoints already belong to B0.
            buckets[coset].setdefault(x, []).append((p,q))
    hit = B0 == S
    winner = None
    for q, entries in sorted(buckets.items()):
        if span([*inside, *entries]) == S:
            hit = True; winner = q; break
    if hit:
        candidates = list(inside)
        if winner is not None:
            candidates += [p for pairs in buckets[winner].values() for pair in pairs for p in pair]
        original_rankone_basis = independent(sorted(set(candidates)))
        assert all(matrix_rank(x, rows, cols) == 1 for x in original_rankone_basis)
        assert len(original_rankone_basis) <= d+1 and S <= span(original_rankone_basis)
        # Independently solve and restore dependent raw free slices, including zero.
        coeff = {0:0}
        for i, v in enumerate(original_rankone_basis):
            coeff.update({x ^ v:c ^ (1 << i) for x,c in list(coeff.items())})
        sbasis = independent(sorted(S))
        raw = [0,*sbasis]
        if sbasis: raw += [sbasis[0], __import__('functools').reduce(int.__xor__, sbasis,0)]
        for x in raw:
            rebuilt = 0
            for i,v in enumerate(original_rankone_basis):
                if coeff[x] >> i & 1: rebuilt ^= v
            assert rebuilt == x
    return dict(hit=hit,inside_rank=len(B0).bit_length()-1,
        bucket_ranks={q:len(span(entries)).bit_length()-1 for q,entries in buckets.items()},
        union_edge_rank=len(span(x for entries in buckets.values() for x in entries)).bit_length()-1,
        original_basis=original_rankone_basis if hit else [], selected_coset=winner)


def all_subspaces(width):
    # Store a subspace as a bit set of its *vectors*, independent of RREF code.
    seen = {1}
    todo = [1]
    for old in todo:
        members = list(points(old))
        for v in range(1,1 << width):
            if old >> v & 1: continue
            new = old | sum(1 << (x ^ v) for x in members)
            if new not in seen: seen.add(new); todo.append(new)
    return sorted(seen,key=lambda x:(x.bit_count(),x))


def exhaustive(rows, cols):
    spaces = all_subspaces(rows*cols)
    rankone = rankone_points(rows,cols)
    # Every independent rank-one support spans one of these spaces; conversely
    # rank-one points spanning L contain a rank-one basis of size dim L.
    attainable = [L for L in spaces if span(p for p in rankone if L >> p & 1) == frozenset(points(L))]
    hist = collections.Counter(); positive_nonzero_inside = 0
    for encoded in spaces:
        S = frozenset(points(encoded)); d = len(S).bit_length()-1
        exact = min(L.bit_count().bit_length()-1 for L in attainable if encoded & ~L == 0)
        result = edge_decision(S,rows,cols)
        assert result['hit'] == (exact <= d+1), (rows,cols,sorted(S),exact,result)
        hist[(d,exact)] += 1
        positive_nonzero_inside += bool(result['hit'] and result['inside_rank'] > 0 and result['inside_rank'] < d)
    return dict(shape=[rows,cols],all_target_subspaces=len(spaces),
        all_rankone_spanned_support_spaces=len(attainable),
        minimum_support_histogram={f'd{d}/rank{r}':n for (d,r),n in sorted(hist.items())},
        positive_nonzero_proper_inside_cases=positive_nonzero_inside)


def main():
    started = time.process_time()
    checks = [exhaustive(2,2), exhaustive(2,3)]
    # B0 is essential: rank-one R is physically disjoint from rank-two D.
    R,D = 256,10
    nonzero_inside = edge_decision([R,D],3,3)
    assert nonzero_inside['hit'] and nonzero_inside['inside_rank'] == 1 and nonzero_inside['union_edge_rank'] == 1
    assert len(nonzero_inside['original_basis']) == 3
    # Different cosets cannot be united. Two disjoint rank-two diagonal blocks
    # need four CP points, certified also by another mode's flattening rank4.
    A,B = (1 << 0) ^ (1 << 5), (1 << 10) ^ (1 << 15)
    cross = edge_decision([A,B],4,4)
    assert not cross['hit'] and cross['inside_rank'] == 0 and cross['union_edge_rank'] == 2
    assert max(cross['bucket_ranks'].values()) == 1
    # A one-dimensional rank-three matrix image is not two CP points.
    rank3_negative = edge_decision([1 | (1 << 4) | (1 << 8)],3,3)
    assert not rank3_negative['hit']
    out = Path(__file__).resolve().parent
    result = dict(status='PASS_INDEPENDENT_TINY_EXHAUSTIVE_MATH_CONTROLS',
        oracle_imports_production=False,exhaustive=checks,
        controls={'nonzero_B0_essential':{'S_basis':[R,D],'shape':[3,3],**nonzero_inside},
                  'cannot_combine_cosets':{'S_basis':[A,B],'shape':[4,4],**cross},
                  'rank3_image_dim1_negative':{'S_basis':[273],'shape':[3,3],**rank3_negative}},
        zero_and_dependent_raw_slices_reconstructed_for_every_positive=True,
        cpu_seconds=time.process_time()-started,n5_queries=0,solver_calls=0)
    p = out/'oracle-report.json'
    with p.open('x') as f: json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
    p.chmod(0o444)
    print(json.dumps({k:result[k] for k in ['status','cpu_seconds','n5_queries']}))
    print('subspaces',sum(x['all_target_subspaces'] for x in checks),'report_sha256',hashlib.sha256(p.read_bytes()).hexdigest())


if __name__ == '__main__': main()
