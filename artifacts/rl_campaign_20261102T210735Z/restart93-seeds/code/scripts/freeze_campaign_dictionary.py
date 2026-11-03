"""Freeze a deterministic F2 term dictionary from exact 5x5 certificates.

The dictionary is a finite set of admissible columns, not itself an algorithm.
Only explicitly selected certificates and immediate *.json directory entries
are read. Every selected certificate must pass independent exact verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.search import decode_candidate,encode_candidate
from mmsearch.verify import verify_candidate


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def value_digest(value):
    return digest_bytes(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key]=value
    return result


def read_json(raw):
    def invalid_constant(value):
        raise ValueError(f'nonfinite JSON constant: {value}')
    return json.loads(raw,object_pairs_hook=unique_object,parse_constant=invalid_constant)


def freeze(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(0o444)


def selected_paths(candidates,candidate_dirs):
    paths=set()
    for path in candidates:
        path=Path(path).resolve()
        if not path.is_file():
            raise ValueError(f'candidate is not a file: {path}')
        paths.add(path)
    for directory in candidate_dirs:
        directory=Path(directory).resolve()
        if not directory.is_dir():
            raise ValueError(f'candidate directory is not a directory: {directory}')
        paths.update(path.resolve() for path in directory.glob('*.json') if path.is_file())
    if not paths:
        raise ValueError('at least one independently verified baseline certificate is required')
    return sorted(paths)


def canonical_certificate(raw,path):
    value=read_json(raw)
    if (not isinstance(value,dict) or type(value.get('dimension')) is not int
            or value['dimension']!=5 or type(value.get('field')) is not int or value['field']!=2):
        raise ValueError(f'certificate must declare dimension 5 over F2: {path}')
    # The independent verifier validates the original dense certificate schema
    # and every coefficient, rather than trusting its supplied metadata.
    report=verify_candidate(value,random_trials=0)
    if not report['valid'] or report['exact_entries_checked']!=15625:
        raise ValueError(f'certificate failed exhaustive F2 verification: {path}')
    terms=set()
    for triple in decode_candidate(value,5):
        if not all(triple):
            continue
        if triple in terms:
            terms.remove(triple)
        else:
            terms.add(triple)
    terms=tuple(sorted(terms))
    canonical=encode_candidate(terms,5)
    canonical_report=verify_candidate(canonical,random_trials=0)
    if not canonical_report['valid'] or canonical_report['exact_entries_checked']!=15625:
        raise ValueError(f'canonical certificate failed exhaustive F2 verification: {path}')
    return terms,report,canonical_report


def dictionary_columns(raw,path):
    value=read_json(raw)
    if not isinstance(value,list):
        raise ValueError(f'extra dictionary must be a JSON list of mask triples: {path}')
    terms=[]
    for triple in value:
        if (not isinstance(triple,list) or len(triple)!=3
                or any(type(mask) is not int or not 0 < mask < (1<<25) for mask in triple)):
            raise ValueError(f'extra dictionary columns must be nonzero 25-bit integer triples: {path}')
        terms.append(tuple(triple))
    return tuple(sorted(set(terms)))


def freeze_dictionary(*,candidates=(),candidate_dirs=(),extra_dictionary=None,output_dir):
    output=Path(output_dir).resolve()
    if output.exists():
        raise ValueError('output directory must be new; frozen artifacts are never overwritten')
    paths=selected_paths(candidates,candidate_dirs)
    sources=[];raw_inputs=[];union=set();algorithms={}
    for index,path in enumerate(paths):
        raw=path.read_bytes()
        terms,report,canonical_report=canonical_certificate(raw,path)
        canonical_sha=value_digest(encode_candidate(terms,5))
        source=dict(path=str(path),raw_sha256=digest_bytes(raw),
                    snapshot=f'inputs/{index:05d}-{digest_bytes(raw)}.json',
                    canonical_sha256=canonical_sha,supplied_rank=report['rank'],
                    essential_rank=len(terms),exact_entries_checked=report['exact_entries_checked'],
                    valid=True,verification=f'verification/{index:05d}.json')
        sources.append(source);raw_inputs.append((source['snapshot'],raw))
        raw_inputs.append((source['verification'],json_bytes(dict(original=report,canonical=canonical_report))))
        union.update(terms)
        algorithms.setdefault(canonical_sha,dict(terms=terms,source=source))
    extra=None
    if extra_dictionary is not None:
        path=Path(extra_dictionary).resolve();raw=path.read_bytes()
        columns=dictionary_columns(raw,path)
        extra=dict(path=str(path),raw_sha256=digest_bytes(raw),snapshot='inputs/extra-dictionary.json',
                   validated_distinct_columns=len(columns),
                   policy='Nonzero rank-one columns only; no complete-algorithm exactness is asserted.')
        raw_inputs.append((extra['snapshot'],raw));union.update(columns)
    dictionary=tuple(sorted(union))
    dictionary_sha=value_digest(dictionary)
    baseline_sha,baseline=min(algorithms.items(),key=lambda item:(len(item[1]['terms']),item[0]))
    baseline_candidate=encode_candidate(baseline['terms'],5,method='frozen-dictionary-baseline',
                                        source_path=baseline['source']['path'],
                                        source_raw_sha256=baseline['source']['raw_sha256'],
                                        canonical_sha256=baseline_sha)
    baseline_report=verify_candidate(baseline_candidate,random_trials=0)
    assert baseline_report['valid'] and baseline_report['exact_entries_checked']==15625
    code_paths=[Path(__file__).resolve(),Path(__file__).resolve().parents[1]/'mmsearch/search.py',
                Path(__file__).resolve().parents[1]/'mmsearch/verify.py']
    code_data={str(path.relative_to(Path(__file__).resolve().parents[1])):path.read_bytes()
               for path in code_paths}
    code_hashes={name:digest_bytes(raw) for name,raw in code_data.items()}
    pool=dict(dimension=5,field=2,dictionary_size=len(dictionary),dictionary_sha256=dictionary_sha,
              sources=sources,distinct_algorithms=len(algorithms),extra_dictionary=extra,
              code_sha256=code_hashes,
              baseline=dict(path='baseline.json',rank=len(baseline['terms']),canonical_sha256=baseline_sha,
                            source_path=baseline['source']['path'],source_raw_sha256=baseline['source']['raw_sha256']),
              scope='Frozen finite dictionary only; no global existence or nonexistence claim. '
                    'Dictionary SAT may choose any subset, independently of the source-algorithm span.')
    pool['pool_sha256']=value_digest(pool)
    output.mkdir(parents=True,exist_ok=False)
    artifacts={name:raw for name,raw in raw_inputs}
    artifacts.update({'dictionary.json':json_bytes(dictionary),'pool.json':json_bytes(pool),
                      'baseline.json':json_bytes(baseline_candidate),
                      'baseline.verification.json':json_bytes(baseline_report),
                      'verify.py':code_paths[-1].read_bytes()})
    artifacts.update({'code/'+name:raw for name,raw in code_data.items()})
    for name,raw in artifacts.items():
        freeze(output/name,raw)
    checksums={name:digest_bytes(raw) for name,raw in sorted(artifacts.items())}
    freeze(output/'checksums.json',json_bytes(checksums))
    return dict(output_dir=str(output),dictionary_size=len(dictionary),dictionary_sha256=dictionary_sha,
                certificates=len(sources),distinct_algorithms=len(algorithms),baseline_rank=len(baseline['terms']),
                pool_sha256=pool['pool_sha256'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,action='append',default=[])
    parser.add_argument('--candidate-dir',type=Path,action='append',default=[])
    parser.add_argument('--extra-dictionary',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    result=freeze_dictionary(candidates=args.candidate,candidate_dirs=args.candidate_dir,
                             extra_dictionary=args.extra_dictionary,output_dir=args.output_dir)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()
