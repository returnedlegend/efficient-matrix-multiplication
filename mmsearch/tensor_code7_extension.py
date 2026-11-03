"""Version 2: authenticated whole-atom extensions by exact odd five-term cycles.

This module does not select production parent pairs or run a heuristic/SAT solver.
The v1 dictionary and strict approved-source loader remain unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from mmsearch.tensor_code7 import (atom_column, digest, fundamental_kernel, strict_load,
    target_tensor, term_from_atom, validate_prepared, xor_columns)

WITNESS_SCHEMA = "tensor_code7.extension_witnesses.v2"
PREPARED_SCHEMA = "tensor_code7.extension_prepared.v2"
MAX_RELATIONS = 16
MAX_NEW_ATOMS = 100
MAX_TOTAL_ATOMS = 5000


def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def integer(value, name, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError("invalid literal integer "+name)
    return value


def plus_atoms(left, right, permutation, n):
    """x+y=(a+d,b,c)+(d,b,c+f)+(d,b+e,f), then undo axis order."""
    term_from_atom(left, n)
    term_from_atom(right, n)
    if type(permutation) is not list or len(permutation) != 3 or any(type(i) is not int for i in permutation) or sorted(permutation) != [0, 1, 2]:
        raise ValueError("axis_permutation must contain literal integers0,1,2")
    a, b, c = [left[i] for i in permutation]
    d, e, f = [right[i] for i in permutation]
    ordered = ((a^d, b, c), (d, b, c^f), (d, b^e, f))
    answer = []
    for atom in ordered:
        original = [0, 0, 0]
        for coordinate, axis in enumerate(permutation):
            original[axis] = atom[coordinate]
        # Zero factors and duplicate terms would invalidate the odd-cycle proof.
        term_from_atom(original, n)
        answer.append(tuple(original))
    if len(set((tuple(left), tuple(right), *answer))) != 5:
        raise ValueError("five-term relation requires five distinct nonzero atoms")
    return answer


def scalar_zero_check(atoms,n,guard=None):
    """Independent literal scalar products over every coefficient, zeros included."""
    width=n*n
    mismatches=0
    for a in range(width):
        if guard:
            guard()
        for b in range(width):
            for c in range(width):
                coefficient=0
                for u,v,w in atoms:
                    coefficient ^= ((u>>a)&1) & ((v>>b)&1) & ((w>>c)&1)
                mismatches += coefficient != 0
    return dict(valid=mismatches==0,exact_entries_checked=n**6,mismatch_count=mismatches)


@dataclass(frozen=True)
class BaseReceipt:
    base_prepared_sha256: str
    base_dictionary_sha256: str
    source_manifest_sha256: str
    approved_source_count: int
    approved_root: str


def authenticate_base(base_path, base_sha256, source_manifest, source_manifest_sha256,
                      approved_root, scratch, guard):
    """Reuse the frozen v1 strict source reconstruction, with independent pins."""
    base_path = Path(base_path).resolve(strict=True)
    raw = base_path.read_bytes()
    if raw_sha(raw) != base_sha256:
        raise ValueError("base prepared raw hash differs from root-approved pin")
    base = strict_load(raw)
    import mmsearch.tensor_code7 as core
    if raw_sha(Path(core.__file__).read_bytes()) != base["code_sha256"]["mmsearch/tensor_code7.py"]:
        raise ValueError("loaded v1 exact-math implementation differs from frozen approved base")
    # Before import, check every frozen v1 local code file against its receipt.
    code_root = base_path.parent/"code"
    for name, expected in base["code_sha256"].items():
        if raw_sha((code_root/name).read_bytes()) != expected:
            raise ValueError("frozen v1 code closure hash mismatch")
    spec = importlib.util.spec_from_file_location("tensor_code7_extension_v1_trust", code_root/"scripts/tensor_code7.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = SimpleNamespace(prepared=base_path,manifest=Path(source_manifest),
        manifest_sha256=source_manifest_sha256,approved_root=Path(approved_root),outdir=Path(scratch))
    module.verify_source_binding(args,base,guard)
    validate_prepared(base,guard)
    if any(weight != 93 for weight in base["seed_weights"]):
        raise ValueError("approved v1 source states must remain weight93")
    return base,BaseReceipt(base_sha256,base["dictionary_sha256"],source_manifest_sha256,
                            len(base["sources"]),str(Path(approved_root).resolve()))


def validate_witnesses(base, manifest, base_sha256, guard=None):
    atoms,columns,seeds,cycles = validate_prepared(base,guard)
    n = base["dimension"]
    if type(manifest) is not dict or set(manifest) != {"schema","base_prepared_sha256","base_dictionary_sha256","max_new_atoms","relations"}:
        raise ValueError("unexpected or missing top-level witness fields")
    if manifest.get("schema") != WITNESS_SCHEMA:
        raise ValueError("wrong extension witness schema")
    if manifest.get("base_prepared_sha256") != base_sha256 or manifest.get("base_dictionary_sha256") != base["dictionary_sha256"]:
        raise ValueError("witnesses refer to a different approved base")
    maximum = integer(manifest.get("max_new_atoms"),"max_new_atoms",1,MAX_NEW_ATOMS)
    records = manifest.get("relations")
    if type(records) is not list or not 1 <= len(records) <= MAX_RELATIONS:
        raise ValueError("initial extension requires1..16 explicit relations")
    atom_ids = {atom:i for i,atom in enumerate(atoms)}
    base_set = set(atoms)
    relations = []
    seen_ids = set()
    seen_relations = set()
    for record in records:
        if guard:
            guard()
        if type(record) is not dict or set(record) != {"id","parent_atom_ids","axis_permutation","new_atoms"}:
            raise ValueError("unexpected or missing relation witness fields")
        name = record["id"]
        if type(name) is not str or not name or name in seen_ids:
            raise ValueError("relation IDs must be nonempty and unique")
        seen_ids.add(name)
        parent_ids = record["parent_atom_ids"]
        if type(parent_ids) is not list or len(parent_ids) != 2:
            raise ValueError("exactly two explicit base parent IDs required")
        for index in parent_ids:
            integer(index,"parent_atom_id",0,len(base_set)-1)
        if parent_ids[0] == parent_ids[1]:
            raise ValueError("distinct base parents required")
        parents = [atoms[i] for i in parent_ids]
        proposed = plus_atoms(*parents,record["axis_permutation"],n)
        if record["new_atoms"] != [list(atom) for atom in proposed]:
            raise ValueError("provided atom witness differs from exact plus derivation")
        # Reject numeric aliases even if Python compares e.g. 1.0 == 1.
        for atom in record["new_atoms"]:
            term_from_atom(atom,n)
        if all(atom in base_set for atom in proposed):
            raise ValueError("relation does not extend the old dictionary")
        all_five = parents+proposed
        relation_key = tuple(sorted(all_five))
        if relation_key in seen_relations:
            raise ValueError("duplicate five-term cycle witness")
        seen_relations.add(relation_key)
        relation_tensor = 0
        for atom in all_five:
            relation_tensor ^= atom_column(atom,n)
        if relation_tensor:
            raise ValueError("five-term witness is nonzero in full tensor")
        independent = scalar_zero_check(all_five,n,guard)
        if not independent["valid"]:
            raise ValueError("independent scalar five-term tensor check failed")
        for atom in proposed:
            if atom not in atom_ids:
                if len(atoms)-len(base_set) >= maximum or len(atoms) >= MAX_TOTAL_ATOMS:
                    raise ValueError("authenticated new atom cap exceeded")
                atom_ids[atom] = len(atoms)
                atoms.append(atom)
                columns.append(atom_column(atom,n))
        mask = sum(1 << atom_ids[atom] for atom in all_five)
        if mask.bit_count() != 5 or xor_columns(columns,mask):
            raise AssertionError("odd-cycle certificate failed")
        relations.append(dict(id=name,parent_atom_ids=parent_ids,axis_permutation=record["axis_permutation"],
            new_atoms=[list(a) for a in proposed],cycle_hex=hex(mask),cycle_weight=5,
            full_tensor_xor_hex="0x0",exact_entries_covered=n**6,independent_zero_check=independent,
            inherited_eligibility="derived only from authenticated approved base atoms; no new data source"))
    return atoms,columns,seeds,cycles,relations


def build_extension(base, manifest, base_sha256, witness_sha256, guard=None, production_receipt=None):
    if base.get("dimension") == 5:
        if not isinstance(production_receipt,BaseReceipt) or production_receipt.base_prepared_sha256 != base_sha256 or production_receipt.base_dictionary_sha256 != base.get("dictionary_sha256"):
            raise ValueError("n5 extension preparation requires independently authenticated v1 base receipt")
        if production_receipt.source_manifest_sha256 != base.get("source_manifest_sha256") or production_receipt.approved_source_count != len(base.get("sources", [])):
            raise ValueError("production receipt does not match approved source manifest/count")
    for value in (base_sha256,witness_sha256):
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("independent raw SHA256 pins required")
    old_count = len(base["atoms"])
    atoms,columns,seeds,old_cycles,relations = validate_witnesses(base,manifest,base_sha256,guard)
    cycles,rank = fundamental_kernel(columns,guard=guard)
    target = target_tensor(base["dimension"])
    if any(xor_columns(columns,state) != target for state in seeds):
        raise AssertionError("padded source state changed full tensor")
    if not any(cycle.bit_count() & 1 for cycle in cycles):
        raise AssertionError("odd certified cycle missing from complete new kernel")
    return dict(schema=PREPARED_SCHEMA,dimension=base["dimension"],field=2,tensor_entries=base["dimension"]**6,
        base_prepared_sha256=base_sha256,base_dictionary_sha256=base["dictionary_sha256"],
        extension_witnesses_sha256=witness_sha256,source_manifest_sha256=base.get("source_manifest_sha256"),
        atoms=[list(a) for a in atoms],columns_hex=[hex(c) for c in columns],target_hex=hex(target),
        seed_states_hex=[hex(state) for state in seeds],seed_weights=[state.bit_count() for state in seeds],
        source_state_policy="original approved v1 states padded with zero selections; no94state required",
        base_atom_count=old_count,new_atom_count=len(atoms)-old_count,dictionary_size=len(atoms),
        rank=rank,nullity=len(cycles),kernel_hex=[hex(c) for c in cycles],
        dictionary_sha256=digest(atoms),columns_sha256=digest([hex(c) for c in columns]),
        base_kernel_all_even=all(not(c.bit_count()&1) for c in old_cycles),
        parity_broken=True,odd_kernel_basis_count=sum(c.bit_count()&1 for c in cycles),
        odd_relation_certificates=relations,
        production_receipt=production_receipt.__dict__ if production_receipt else None,
        scope="exact finite dictionary extension only; parity broken is not a lower-rank solution or novelty claim")


def validate_extension_prepared(document,base,manifest,base_sha256,witness_sha256,guard=None,production_receipt=None):
    """Rebuild every derived atom, full column, state, rank, and odd witness."""
    expected = build_extension(base,manifest,base_sha256,witness_sha256,guard,production_receipt)
    if digest(document) != digest(expected):
        raise ValueError("v2 prepared data differs from authenticated exact reconstruction")
    return ([tuple(a) for a in document["atoms"]],[int(c,16) for c in document["columns_hex"]],
            [int(x,16) for x in document["seed_states_hex"]],[int(z,16) for z in document["kernel_hex"]],
            dict(schema=PREPARED_SCHEMA,parity_broken=True,relations=len(document["odd_relation_certificates"]),
                 base_prepared_sha256=base_sha256,witnesses_sha256=witness_sha256,
                 source_manifest_sha256=base.get("source_manifest_sha256"),
                 base_dictionary_sha256=base["dictionary_sha256"],
                 extended_dictionary_sha256=document["dictionary_sha256"],
                 original_seed_masks_unchanged=document["seed_states_hex"]==base["seed_states_hex"]))


def load_root_pinned_extension(path,prepared_sha256,base_path,base_sha256,witness_path,witness_sha256,
                               source_manifest,source_manifest_sha256,approved_root,scratch,guard):
    raw = Path(path).read_bytes()
    witness_raw = Path(witness_path).read_bytes()
    if raw_sha(raw) != prepared_sha256 or raw_sha(witness_raw) != witness_sha256:
        raise ValueError("v2 prepared/witness raw hash differs from root-reviewed pins")
    base,receipt = authenticate_base(base_path,base_sha256,source_manifest,source_manifest_sha256,
                                     approved_root,scratch,guard)
    return validate_extension_prepared(strict_load(raw),base,strict_load(witness_raw),base_sha256,
                                       witness_sha256,guard,receipt)


def retain_raw_candidate(root,candidate,reason,evidence=None):
    """Quarantine late data from operations-v3's recursive candidate ingestion.

    Two barriers are deliberate: hidden storage is pruned by walk_files, and the
    top-level UNKNOWN envelope cannot satisfy canonical_candidate even if copied.
    This function grants no verification or publication eligibility.
    """
    import json
    import os
    import time
    directory=Path(root)/'.raw-candidates'
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/f'after-cutoff-{os.getpid()}-{time.monotonic_ns()}.json'
    value=dict(status='UNKNOWN',complete=False,after_cutoff=True,no_within_budget_claim=True,
               stop_reason=str(reason),raw=dict(candidate=candidate,evidence=evidence))
    payload=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(payload);stream.flush();os.fsync(stream.fileno())
    path.chmod(0o444)
    return path
