"""Bounded, reproducible searches for F2 matrix multiplication decompositions.

``flips`` walks exact decompositions using polynomial identities. ``residual``
starts at the requested rank and minimizes the number of incorrect coefficients;
its output is only a research checkpoint unless every coefficient is correct.
Neither engine is a proof of existence or nonexistence at the requested rank.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Iterable

Term = tuple[int, int, int]


def _bits(mask: int):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def _outer(term: Term, width: int) -> int:
    a, b, c = term
    bc = sum(c << (j * width) for j in _bits(b))
    result = 0
    for i in _bits(a):
        result ^= bc << (i * width * width)
    return result


def target_tensor(n: int = 5) -> int:
    """Trace convention: T[(i,j),(j,k),(k,i)] = 1."""
    width = n * n
    return sum(1 << ((i*n+j)*width*width + (j*n+k)*width + k*n+i)
               for i in range(n) for j in range(n) for k in range(n))


def residual(terms: Iterable[Term], n: int = 5) -> int:
    result = target_tensor(n)
    for term in terms:
        result ^= _outer(term, n*n)
    return result


def _rotations(term: Term) -> tuple[Term, ...]:
    a, b, c = term
    return tuple(sorted({(a,b,c), (b,c,a), (c,a,b)}))


def _canonical(term: Term) -> Term:
    return min(_rotations(term))


def _toggle(terms: set[Term], term: Term) -> None:
    if not all(term):
        return
    if term in terms:
        terms.remove(term)
    else:
        terms.add(term)


def _move(terms: set[Term], old: Iterable[Term], new: Iterable[Term], cyclic: bool) -> set[Term]:
    result = terms.copy()
    for term in (*old, *new):
        # A fixed cube occurs three times in the formal C3 sum, hence once in F2.
        for item in (_rotations(term) if cyclic else (term,)):
            _toggle(result, item)
    return result


def is_cyclic(terms: Iterable[Term]) -> bool:
    terms = set(terms)
    return all(set(_rotations(term)) <= terms for term in terms)


def orbit_counts(terms: Iterable[Term]) -> dict[str, int]:
    terms = set(terms)
    fixed = sum(a == b == c for a,b,c in terms)
    return {"fixed_cubes": fixed, "three_cycles": (len(terms)-fixed)//3}


def naive_terms(n: int = 5) -> list[Term]:
    return [(1 << (i*n+j), 1 << (j*n+k), 1 << (k*n+i))
            for i in range(n) for j in range(n) for k in range(n)]


def decode_candidate(candidate: dict, n: int = 5) -> list[Term]:
    """Read the public dense-vector certificate format, also internal bit triples."""
    if candidate.get("field", 2) != 2 or candidate.get("dimension", n) != n:
        raise ValueError("search requires the requested dimension over F2")
    terms = []
    for item in candidate["terms"]:
        if isinstance(item, dict):
            values = []
            for key in ("u", "v", "w"):
                vector = item[key]
                if len(vector) != n*n or any(type(x) is not int or x not in (0,1) for x in vector):
                    raise ValueError("factor vectors must contain n*n binary integers")
                values.append(sum(bit << i for i,bit in enumerate(vector)))
            terms.append(tuple(values))
        else:
            if len(item) != 3 or any(type(x) is not int or not 0 <= x < 1 << (n*n) for x in item):
                raise ValueError("internal factors must be nonnegative n*n-bit integers")
            terms.append(tuple(item))
    return terms


def encode_candidate(terms: Iterable[Term], n: int = 5, **metadata) -> dict:
    ordered = sorted(terms)
    return {"field": 2, "dimension": n,
            "terms": [{key: [(factor >> i) & 1 for i in range(n*n)]
                       for key,factor in zip(("u","v","w"), term)} for term in ordered],
            "metadata": metadata}


def _reduction(terms: set[Term], cyclic: bool) -> set[Term] | None:
    """Merge two terms sharing two factors, preserving full cyclic orbits."""
    for differing in range(3):
        seen = {}
        for term in sorted(terms):
            key = tuple(term[j] for j in range(3) if j != differing)
            other = seen.get(key)
            if other is not None and (not cyclic or _canonical(term) != _canonical(other)):
                merged = list(term)
                merged[differing] ^= other[differing]
                proposed = _move(terms, (term,other), (tuple(merged),), cyclic)
                if len(proposed) < len(terms):
                    return proposed
            seen[key] = term
    return None


def _flip(terms: set[Term], rng: random.Random, cyclic: bool) -> set[Term] | None:
    buckets = {}
    for term in sorted(terms):
        for axis,value in enumerate(term):
            buckets.setdefault((axis,value), []).append(term)
    eligible = [(key,group) for key,group in buckets.items() if len(group) >= 2]
    for _ in range(30):
        if not eligible:
            return None
        (axis,_), group = rng.choice(eligible)
        x,y = rng.sample(group,2)
        if cyclic and _canonical(x) == _canonical(y):
            continue
        p,q = [j for j in range(3) if j != axis]
        if rng.getrandbits(1):
            p,q = q,p
        first,second = list(x),list(y)
        first[p] ^= y[p]
        second[q] ^= x[q]
        return _move(terms,(x,y),(tuple(first),tuple(second)),cyclic)
    return None


def _plus(terms: set[Term], rng: random.Random, cyclic: bool) -> set[Term] | None:
    if len(terms) < 2:
        return None
    ordered = sorted(terms)
    for _ in range(30):
        x,y = rng.sample(ordered,2)
        if cyclic and _canonical(x) == _canonical(y):
            continue
        axes = rng.sample(range(3),3)
        p,q,r = axes
        # (a,b,c)+(d,e,f) = (a+d,b,c)+(d,b,c+f)+(d,b+e,f).
        first,second,third = list(x),list(x),list(y)
        first[p] ^= y[p]
        second[p] = y[p]
        second[r] ^= y[r]
        third[q] ^= x[q]
        return _move(terms,(x,y),(tuple(first),tuple(second),tuple(third)),cyclic)
    return None


def flip_search(initial_terms: Iterable[Term], *, n: int = 5, rank: int = 94,
                steps: int = 100_000, seconds: float = 60, seed: int = 0,
                cyclic: bool = False, max_extra: int = 6, plus_every: int = 250,
                restart_every: int = 5_000, progress=None) -> tuple[list[Term], dict]:
    """Exact flip/plus walk. Every returned state represents the input tensor."""
    initial = set()
    for term in initial_terms:
        _toggle(initial,term)
    if residual(initial,n):
        raise ValueError("flip search requires an exact starting decomposition")
    if cyclic and not is_cyclic(initial):
        raise ValueError("cyclic search requires complete cyclic orbits in its seed")
    if steps < 0 or seconds < 0 or max_extra < 0 or plus_every < 1 or restart_every < 1:
        raise ValueError("invalid search budget")
    rng = random.Random(seed)
    current,best = initial.copy(),initial.copy()
    archive = [best.copy()]
    started = time.monotonic()
    accepted = pluses = restarts = completed = 0
    history = [{"step": 0,"rank": len(best)}]
    for iteration in range(1,steps+1):
        if len(best) <= rank or time.monotonic()-started >= seconds:
            break
        completed = iteration
        proposed = _reduction(current,cyclic)
        if proposed is None:
            if iteration % plus_every == 0:
                proposed = _plus(current,rng,cyclic)
                pluses += 1
            else:
                proposed = _flip(current,rng,cyclic)
                if proposed is None:
                    proposed = _plus(current,rng,cyclic)
                    pluses += 1
        if proposed is not None and len(proposed) <= len(best)+max_extra:
            current = proposed
            accepted += 1
            if len(current) < len(best):
                # An independent full coefficient check guards move bugs.
                if residual(current,n):
                    raise AssertionError("an exact flip move changed the tensor")
                best = current.copy()
                archive = [best.copy()]
                history.append({"step":iteration,"rank":len(best)})
                if progress:
                    progress({"step":iteration,"rank":len(best),"elapsed":time.monotonic()-started})
            elif len(current) == len(best) and iteration % 100 == 0:
                archive.append(current.copy())
                if len(archive) > 16:
                    archive.pop(rng.randrange(len(archive)))
        if iteration % restart_every == 0:
            current = rng.choice(archive).copy()
            restarts += 1
    if residual(best,n):
        raise AssertionError("final exact coefficient verification failed")
    return sorted(best), {"engine":"flips","steps":completed,"accepted_moves":accepted,
                         "plus_attempts":pluses,"restarts":restarts,"history":history,
                         "elapsed_seconds":time.monotonic()-started,"residual_weight":0}


def residual_search(initial_terms: Iterable[Term], *, n: int = 5, rank: int = 94,
                    steps: int = 100, seconds: float = 60, seed: int = 0,
                    progress=None) -> tuple[list[Term], dict]:
    """Coordinate descent on all n^6 coefficients at exactly ``rank`` slots.

    A step is one complete sweep through the three binary factors of every
    summand. Zero-cost flips and sparse perturbations escape shallow plateaus.
    This unconstrained engine does not preserve cyclic symmetry.
    """
    if rank < 1 or steps < 0 or seconds < 0:
        raise ValueError("invalid residual search budget")
    width = n*n
    rng = random.Random(seed)
    terms = list(initial_terms)
    rng.shuffle(terms)
    # Select deletions by their actual coefficient residual. In particular,
    # rank96 -> rank94 examines every pair, rather than dropping arbitrary
    # dense summands and spending the budget repairing avoidable errors.
    error = residual(terms,n)
    contributions = [_outer(term,width) for term in terms]
    if len(terms)-rank == 2:
        _,first,second = min(((error ^ contributions[i] ^ contributions[j]).bit_count(),i,j)
                             for i in range(len(terms)) for j in range(i+1,len(terms)))
        terms = [term for index,term in enumerate(terms) if index not in (first,second)]
    else:
        while len(terms) > rank:
            index = min(range(len(terms)),key=lambda j:(error ^ contributions[j]).bit_count())
            error ^= contributions.pop(index)
            terms.pop(index)
    while len(terms) < rank:
        terms.append((1 << rng.randrange(width),1 << rng.randrange(width),0))
    error = residual(terms,n)
    best, best_error = terms.copy(),error.bit_count()
    started = time.monotonic()
    completed = stalls = 0
    history = [{"step":0,"residual_weight":best_error}]
    stop = False
    for sweep in range(1,steps+1):
        if best_error == 0 or time.monotonic()-started >= seconds:
            break
        completed = sweep
        before = error.bit_count()
        order = list(range(rank))
        rng.shuffle(order)
        for index in order:
            if time.monotonic()-started >= seconds:
                stop = True
                break
            term = list(terms[index])
            for axis in rng.sample(range(3),3):
                basis = term.copy()
                basis[axis] = 1
                delta_base = _outer(tuple(basis),width)
                size = delta_base.bit_count()
                stride = (width*width,width,1)[axis]
                for bit in rng.sample(range(width),width):
                    delta = delta_base << (bit*stride)
                    gain = 2*(error & delta).bit_count()-size
                    if gain > 0 or (gain == 0 and rng.random() < 0.02):
                        error ^= delta
                        term[axis] ^= 1 << bit
            terms[index] = tuple(term)
            weight = error.bit_count()
            if weight < best_error:
                best,best_error = terms.copy(),weight
                history.append({"step":sweep,"residual_weight":weight})
                if progress:
                    progress({"step":sweep,"rank":rank,"residual_weight":weight,
                              "elapsed":time.monotonic()-started})
                if weight == 0:
                    stop = True
                    break
        if stop:
            break
        stalls = stalls+1 if error.bit_count() >= before else 0
        if stalls >= 3:
            terms = best.copy()
            for _ in range(max(1,rank//20)):
                index = rng.randrange(rank)
                term = list(terms[index])
                term[rng.randrange(3)] ^= 1 << rng.randrange(width)
                terms[index] = tuple(term)
            error = residual(terms,n)
            stalls = 0
    actual = residual(best,n).bit_count()
    if actual != best_error:
        raise AssertionError("incremental residual disagrees with coefficient check")
    return best, {"engine":"residual","steps":completed,"elapsed_seconds":time.monotonic()-started,
                  "residual_weight":best_error,"history":history}


def search(*, rank: int = 94, seed: int = 0, steps: int = 100_000,
           seconds: float = 60, initial_terms=None, n: int = 5, cyclic: bool = False,
           engine: str = "flips", max_extra: int = 6, plus_every: int = 250,
           restart_every: int = 5_000, progress=None) -> dict:
    if rank < 1 or n < 1:
        raise ValueError("rank and dimension must be positive")
    initial_terms = naive_terms(n) if initial_terms is None else list(initial_terms)
    if engine == "flips":
        terms,metadata = flip_search(initial_terms,n=n,rank=rank,steps=steps,seconds=seconds,
                                    seed=seed,cyclic=cyclic,max_extra=max_extra,plus_every=plus_every,
                                    restart_every=restart_every,progress=progress)
    elif engine == "residual":
        if cyclic:
            raise ValueError("the residual engine does not implement cyclic constraints; use flips")
        terms,metadata = residual_search(initial_terms,n=n,rank=rank,steps=steps,seconds=seconds,
                                        seed=seed,progress=progress)
    else:
        raise ValueError("unknown search engine")
    metadata.update(seed=seed,target_rank=rank,rank=len(terms),cyclic=is_cyclic(terms),
                    orbit_counts=orbit_counts(terms) if is_cyclic(terms) else None,
                    exact=metadata["residual_weight"] == 0)
    metadata["target_reached"] = metadata["exact"] and len(terms) <= rank
    metadata["status"] = "verified_target" if metadata["target_reached"] else "research_checkpoint"
    return encode_candidate(terms,n,**metadata)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2)+"\n")
    temporary.replace(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rank",type=int,default=94)
    parser.add_argument("--dimension",type=int,default=5)
    parser.add_argument("--seed",type=int,default=0)
    parser.add_argument("--steps",type=int,default=100_000)
    parser.add_argument("--seconds",type=float,default=60)
    parser.add_argument("--engine",choices=("flips","residual"),default="flips")
    parser.add_argument("--initial",type=Path)
    parser.add_argument("--cyclic",action="store_true")
    parser.add_argument("--max-extra",type=int,default=6)
    parser.add_argument("--plus-every",type=int,default=250)
    parser.add_argument("--restart-every",type=int,default=5_000)
    parser.add_argument("--output",type=Path,default=Path("artifacts/search-checkpoint.json"))
    parser.add_argument("--quiet",action="store_true")
    args = parser.parse_args(argv)
    initial = decode_candidate(json.loads(args.initial.read_text()),args.dimension) if args.initial else None
    candidate = search(rank=args.rank,n=args.dimension,seed=args.seed,steps=args.steps,seconds=args.seconds,
                       initial_terms=initial,cyclic=args.cyclic,engine=args.engine,max_extra=args.max_extra,
                       plus_every=args.plus_every,restart_every=args.restart_every,
                       progress=None if args.quiet else lambda item: print(json.dumps(item),flush=True))
    # Independent certificate verification accompanies every emitted checkpoint.
    from mmsearch.verify import verify_candidate, write_standalone_verifier
    report = verify_candidate(candidate,random_trials=8,seed=args.seed)
    if candidate["metadata"]["exact"] and not report["valid"]:
        raise AssertionError("independent verifier rejected an exact search result")
    _write(args.output,candidate)
    report_path = args.output.with_suffix(".verification.json")
    _write(report_path,report)
    standalone_path = args.output.with_suffix(".verify.py")
    write_standalone_verifier(standalone_path)
    print(json.dumps({"candidate":str(args.output),"verification":str(report_path),
                      "standalone_verifier":str(standalone_path),**candidate["metadata"]}),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
