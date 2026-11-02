"""Generate verified, known-equivalent GL(n,F2)^3 transvection seeds.

These transformations preserve rank and the matrix multiplication tensor; they
are diversity witnesses, never new rank records. All arithmetic is integer F2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.search import decode_candidate, encode_candidate
from mmsearch.verify import verify_candidate


def row_xor(mask, n, destination, source):
    return mask ^ (((mask >> (source*n)) & ((1 << n)-1)) << (destination*n))


def column_xor(mask, n, destination, source):
    column = sum(((mask >> (r*n+source)) & 1) << (r*n+destination) for r in range(n))
    return mask ^ column


def transvection(terms, n, group, i, j):
    """P,Q,R = I+E_ij; transpose action on coefficient matrices."""
    if group not in ('P', 'Q', 'R') or not 0 <= i < n or not 0 <= j < n or i == j:
        raise ValueError('invalid elementary transvection')
    result = []
    for u, v, w in terms:
        if group == 'P':
            u, w = row_xor(u,n,j,i), column_xor(w,n,i,j)
        elif group == 'Q':
            u, v = column_xor(u,n,i,j), row_xor(v,n,j,i)
        else:
            v, w = column_xor(v,n,i,j), row_xor(w,n,j,i)
        result.append((u,v,w))
    return sorted(result)


def forced_one_terms(audit):
    """Full exact augmented RREF; retain unit equations x_i = 1."""
    terms = [tuple(t) for t in audit['dictionary']]
    count = len(terms)
    coefficient_mask = (1 << count)-1
    basis = {}
    for raw in audit['independent_augmented_rows_hex']:
        row = int(raw, 16)
        while row & coefficient_mask:
            pivot = (row & -row).bit_length()-1
            if pivot in basis:
                row ^= basis[pivot]
            else:
                basis[pivot] = row
                break
        else:
            if row >> count:
                raise ValueError('inconsistent audited system')
    for pivot in sorted(basis, reverse=True):
        row = basis[pivot]
        for other in basis:
            if other < pivot and (basis[other] >> pivot & 1):
                basis[other] ^= row
    forced = {terms[pivot] for pivot, row in basis.items()
              if (row & coefficient_mask).bit_count() == 1 and row >> count & 1}
    return forced, len(basis)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(source, audit_path, output, max_variants=8, max_new_terms=999):
    source, audit_path, output = Path(source), Path(audit_path), Path(output)
    if (output/'manifest.json').exists():
        raise ValueError('output already has a frozen manifest')
    candidate = json.loads(source.read_text())
    n = candidate['dimension']
    original = decode_candidate(candidate, n)
    if not verify_candidate(candidate, random_trials=0)['valid']:
        raise ValueError('source certificate is inexact')
    audit = json.loads(audit_path.read_text())
    dictionary = {tuple(t) for t in audit['dictionary']}
    forced, system_rank = forced_one_terms(audit)
    variants = []
    for group in 'PQR':
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                terms = transvection(original,n,group,i,j)
                encoded = encode_candidate(terms,n,engine='group_transvection',
                    known_equivalent=True,novel=False,source=str(source),
                    source_sha256=sha(source),group=group,i=i,j=j)
                report = verify_candidate(encoded,random_trials=0)
                if not report['valid'] or len(terms) != len(original):
                    raise AssertionError('transvection failed independent exact verification')
                variants.append(dict(id=f'{group}-{i}-{j}', group=group, i=i, j=j,
                    terms=set(terms), candidate=encoded, verification=report,
                    omits=forced-set(terms)))
    selected, released, union = [], set(), set()
    remaining = variants.copy()
    while remaining and len(selected) < max_variants:
        eligible = [v for v in remaining if len((union | v['terms'])-dictionary) <= max_new_terms]
        if not eligible:
            break
        winner = max(eligible,key=lambda v:(len(v['omits']-released),
                     -len(v['terms']-(dictionary|union)),v['id']))
        if not (winner['omits']-released):
            break
        selected.append(winner)
        remaining.remove(winner)
        released |= winner['omits']
        union |= winner['terms']
    output.mkdir(parents=True,exist_ok=True)
    for variant in selected:
        (output/f"{variant['id']}.json").write_text(json.dumps(variant['candidate'],sort_keys=True)+'\n')
        (output/f"{variant['id']}.verification.json").write_text(json.dumps(variant['verification'],sort_keys=True)+'\n')
    text = output/'group_terms.txt'
    text.write_text(''.join(' '.join(map(str,t))+'\n' for t in sorted(union)))
    coverage = []
    cumulative = set()
    for v in selected:
        additional = v['omits']-cumulative
        cumulative |= v['omits']
        coverage.append(dict(id=v['id'],newly_released=len(additional),
            total_released=len(cumulative),omitted_forced_terms=sorted(v['omits'])))
    manifest = dict(engine='exact_GL_transvection_seed_generation',dimension=n,
        rank=len(original),known_equivalent=True,novel=False,
        source=str(source),source_sha256=sha(source),script_sha256=sha(__file__),
        audit=str(audit_path),audit_sha256=sha(audit_path),dictionary_size=len(dictionary),
        audited_system_rank=system_rank,forced_one_count=len(forced),
        forced_one_terms=sorted(forced),variants_generated=len(variants),
        all_variants_independently_verified=True,exact_entries_checked_per_variant=n**6,
        selected=coverage,selected_count=len(selected),released_count=len(released),
        remaining_forced_terms=sorted(forced-released),union_terms=len(union),
        new_terms=len(union-dictionary),max_new_terms=max_new_terms,
        group_terms=str(text),group_terms_sha256=sha(text),
        formulas={
            'P':'U row j ^= row i; W column i ^= column j',
            'Q':'U column i ^= column j; V row j ^= row i',
            'R':'V column i ^= column j; W row j ^= row i'},
        proof='For S=I+E_ij over F2 with i!=j, S^-1=S. '
              'The input substitution (A,B,C)->(PAQ^-1,QBR^-1,RCP^-1) '
              'preserves tr(ABC); the displayed actions are its coefficient transpose. '
              'For each omitted forced term, a selected independently verified rank-93 '
              'scheme is a feasible union-dictionary witness with that variable zero. '
              'Thus every released variable ceases to be forced one in that union.')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('artifacts/km93_f2.json'))
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-variants',type=int,default=8)
    parser.add_argument('--max-new-terms',type=int,default=999)
    args = parser.parse_args(argv)
    report = generate(args.source,args.audit,args.output,args.max_variants,args.max_new_terms)
    print(json.dumps({key:report[key] for key in ('group_terms','variants_generated',
        'selected_count','forced_one_count','released_count','union_terms','new_terms')}))


if __name__ == '__main__':
    main()
