"""Freeze independently verified cyclic seeds with changed fixed-cube profiles."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.cube_polarization import orbit_inventory, polarized_seeds
from mmsearch.native_bridge import _freeze, _json_bytes, canonical_terms, term_set_sha256
from mmsearch.search import encode_candidate, is_cyclic, orbit_counts
from mmsearch.verify import verify_candidate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,default=Path("artifacts/km93_f2.json"))
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--conjugates",type=int,default=0)
    p.add_argument("--seed",type=int,default=0)
    args = p.parse_args()
    raw = args.input.read_bytes()
    source = json.loads(raw)
    terms = canonical_terms(source)
    n = source["dimension"]
    if not verify_candidate(encode_candidate(terms,n),random_trials=0)["valid"]:
        raise ValueError("input must be an independently exact F2 certificate")
    folder = args.output_dir.resolve()
    folder.mkdir(parents=True,exist_ok=False)
    records = []
    hashes = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in
              (Path(__file__),Path(__file__).resolve().parents[1]/"mmsearch/cube_polarization.py")}
    for transformed,parameters in polarized_seeds(terms,n,conjugates=args.conjugates,seed=args.seed):
        if not is_cyclic(transformed):
            raise RuntimeError("cyclic closure lost")
        h = term_set_sha256(transformed)
        value = encode_candidate(transformed,n,method="exact-cube-polarization",parameters=parameters,
                                 source_sha256=hashlib.sha256(raw).hexdigest(),code_sha256=hashes,
                                 fixed_cube_profile=orbit_counts(transformed),orbit_inventory=orbit_inventory(transformed),
                                 rank_increase=len(transformed)-len(terms),term_set_sha256=h)
        report = verify_candidate(value,random_trials=0)
        if not report["valid"]:
            raise RuntimeError("independent exhaustive verification rejected polarized seed")
        payload = _json_bytes(value)
        path = _freeze(folder/"seeds"/(h+".json"),payload)
        _freeze(folder/"verification"/(h+".verification.json"),_json_bytes(report))
        digest = hashlib.sha256(payload).hexdigest()
        _freeze(folder/"verification"/(h+".sha256"),(digest+"  "+path.name+"\n").encode())
        records.append(dict(path=str(path),sha256=digest,rank=len(transformed),
                            profile=orbit_counts(transformed),parameters=parameters))
    manifest = dict(input=str(args.input),input_sha256=hashlib.sha256(raw).hexdigest(),
                    input_rank=len(terms),input_profile=orbit_counts(terms),input_orbit_inventory=orbit_inventory(terms),seed=args.seed,
                    code_sha256=hashes,candidates=records)
    _freeze(folder/"manifest.json",_json_bytes(manifest))
    _freeze(folder/"verify.py",(Path(__file__).resolve().parents[1]/"mmsearch/verify.py").read_bytes())
    print(json.dumps(dict(output_dir=str(folder),seeds=len(records),
                         profiles=sorted({(r["rank"],r["profile"]["fixed_cubes"],r["profile"]["three_cycles"]) for r in records}))))


if __name__ == "__main__":
    main()
