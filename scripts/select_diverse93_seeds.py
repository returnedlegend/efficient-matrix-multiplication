"""Select rank-93 restart states using factor-matrix rank profiles and terms.

These metrics distinguish certificate states; they do not prove algorithm
inequivalence, novelty, or a lower multiplication rank.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import combinations_with_replacement
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.search import decode_candidate,encode_candidate
from mmsearch.verify import _schema_error,verify_candidate
from scripts.freeze_campaign_dictionary import freeze,json_bytes,read_json

BINS=tuple(combinations_with_replacement(range(1,6),3))


def gf2_matrix_rank(mask,n=5):
    if type(mask) is not int or type(n) is not int or n<1 or not 0<=mask<1<<(n*n):
        raise ValueError('matrix mask must fit the declared square dimension')
    basis={}
    for row in range(n):
        value=(mask>>(row*n))&((1<<n)-1)
        while value:
            pivot=value.bit_length()-1
            if pivot in basis:
                value^=basis[pivot]
            else:
                basis[pivot]=value
                break
    return len(basis)


def rank_histogram(terms):
    cache={}
    def rank(mask):
        if mask not in cache:
            cache[mask]=gf2_matrix_rank(mask,5)
        return cache[mask]
    counts=Counter(tuple(sorted(rank(mask) for mask in term)) for term in terms)
    return tuple(counts[key] for key in BINS)


def record(path):
    path=Path(path).resolve();raw=path.read_bytes();value=read_json(raw)
    if (not isinstance(value,dict) or type(value.get('field')) is not int or value['field']!=2
            or type(value.get('dimension')) is not int or value['dimension']!=5):
        raise ValueError(f'5x5 F2 certificate required: {path}')
    error=_schema_error(value)
    if error:
        raise ValueError(f'invalid certificate schema: {path}: {error}')
    terms=set()
    for term in decode_candidate(value,5):
        if not all(term):
            continue
        if term in terms:
            terms.remove(term)
        else:
            terms.add(term)
    if len(terms)!=93:
        raise ValueError(f'canonical essential rank must be 93: {path}')
    canonical=''.join(f'{a} {b} {c}\n' for a,b,c in sorted(terms)).encode()
    return dict(path=str(path),raw=raw,raw_sha256=hashlib.sha256(raw).hexdigest(),terms=frozenset(terms),
                canonical_sha256=hashlib.sha256(canonical).hexdigest(),histogram=rank_histogram(terms),
                supplied_rank=len(value['terms']),essential_rank=93)


def distance(left,right):
    histogram_l1=sum(abs(a-b) for a,b in zip(left['histogram'],right['histogram']))
    union=left['terms']|right['terms']
    jaccard=Fraction(len(union)-len(left['terms']&right['terms']),len(union)) if union else Fraction(0)
    return histogram_l1,jaccard


def greedy_select(mandatory,candidates,count):
    if type(count) is not int or count<1 or len(mandatory)>count or not mandatory:
        raise ValueError('at least one mandatory seed and a sufficient count are required')
    selected=list(mandatory);seen={item['canonical_sha256'] for item in selected}
    remaining={}
    for item in sorted(candidates,key=lambda item:(item['path'],item['raw_sha256'])):
        if item['canonical_sha256'] not in seen:
            remaining.setdefault(item['canonical_sha256'],item)
    decisions=[]
    while len(selected)<count:
        if not remaining:
            raise ValueError('insufficient distinct canonical rank93 states')
        scored=[]
        for key,item in remaining.items():
            distances=[distance(item,old) for old in selected]
            score=(min(d[0] for d in distances),min(d[1] for d in distances))
            scored.append((score,item['path'],item['raw_sha256'],key,item))
        # Lexical path/hash breaks metric ties without depending on enumeration order.
        score,_,_,key,item=min(scored,key=lambda row:(-row[0][0],-row[0][1],row[1],row[2]))
        decisions.append(dict(index=len(selected),source_path=item['path'],
                              min_histogram_l1=score[0],min_histogram_total_variation=score[0]/186,
                              min_term_jaccard_distance=float(score[1])))
        selected.append(item);del remaining[key]
    return selected,decisions


def public_record(item):
    return {key:item[key] for key in ('path','raw_sha256','canonical_sha256','histogram',
                                     'supplied_rank','essential_rank')}


def select_and_freeze(*,mandatory,pool,count=4,output_dir):
    output=Path(output_dir).resolve()
    if output.exists():
        raise ValueError('output directory must be new')
    pool=Path(pool).resolve()
    if not pool.is_dir():
        raise ValueError('pool must be a certificate directory')
    mandatory_records=[record(path) for path in mandatory]
    candidates=[record(path) for path in sorted(pool.glob('*.json')) if path.is_file()]
    selected,decisions=greedy_select(mandatory_records,candidates,count)
    reports=[]
    for item in selected:
        original=verify_candidate(read_json(item['raw']),random_trials=0)
        canonical=verify_candidate(encode_candidate(item['terms'],5),random_trials=0)
        if any(not report['valid'] or report['exact_entries_checked']!=15625 for report in (original,canonical)):
            raise ValueError(f'selected certificate failed independent exact verification: {item["path"]}')
        reports.append(dict(original=original,canonical=canonical))
    # All selected algorithms are independently exact before any output is created.
    output.mkdir(parents=True,exist_ok=False)
    frozen=[];checksums={}
    for index,(item,report) in enumerate(zip(selected,reports)):
        name=f'seed{index:02d}-{item["raw_sha256"][:16]}.json'
        relative='seeds/'+name
        freeze(output/relative,item['raw']);checksums[relative]=item['raw_sha256']
        verification=f'verification/seed{index:02d}.json'
        raw=json_bytes(report);freeze(output/verification,raw);checksums[verification]=hashlib.sha256(raw).hexdigest()
        frozen.append(dict(public_record(item),index=index,mandatory=index<len(mandatory_records),
                           copied_path=str(output/relative),verification_path=str(output/verification)))
    code_paths=[Path(__file__).resolve(),Path(__file__).resolve().parents[1]/'mmsearch/search.py',
                Path(__file__).resolve().parents[1]/'mmsearch/verify.py',
                Path(__file__).resolve().parents[1]/'scripts/freeze_campaign_dictionary.py']
    code={str(path.relative_to(Path(__file__).resolve().parents[1])):path.read_bytes() for path in code_paths}
    code_hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in code.items()}
    for name,raw in code.items():
        freeze(output/'code'/name,raw);checksums['code/'+name]=hashlib.sha256(raw).hexdigest()
    manifest=dict(dimension=5,field=2,count=count,pool=str(pool),scanned_pool_count=len(candidates),
                  histogram_bins=BINS,selection_rule='Greedy maximum minimum histogram L1; then maximum minimum term-set Jaccard distance; lexical source path/hash tie break.',
                  metrics_scope='Structural state features only; no algorithm inequivalence or novelty claim.',
                  code_sha256=code_hashes,selected=frozen,greedy_decisions=decisions,
                  scanned=[public_record(item) for item in candidates],
                  pairwise=[dict(i=i,j=j,histogram_l1=distance(left,right)[0],
                                 term_jaccard_distance=float(distance(left,right)[1]))
                            for i,left in enumerate(selected) for j,right in enumerate(selected) if i<j])
    raw=json_bytes(manifest);freeze(output/'manifest.json',raw);checksums['manifest.json']=hashlib.sha256(raw).hexdigest()
    freeze(output/'checksums.json',json_bytes(checksums))
    return dict(output_dir=str(output),selected=[item['copied_path'] for item in frozen],
                manifest_sha256=checksums['manifest.json'],scanned_pool_count=len(candidates))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mandatory',type=Path,action='append',required=True)
    parser.add_argument('--pool',type=Path,required=True)
    parser.add_argument('--count',type=int,default=4)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(select_and_freeze(mandatory=args.mandatory,pool=args.pool,count=args.count,
                                      output_dir=args.output_dir),sort_keys=True))


if __name__=='__main__':
    main()
