"""Pinned nine-case mixed15/d11 binary-block adapter; publication is separate.

No production query is performed by importing, selecting metadata or rebuilding
a compact packet. Only a guarded caller may dispatch a controller.
"""
import gzip
import hashlib
import json
from pathlib import Path

from . import binary_block_descent7 as block
from .compact_sat import BinaryBasis
from .compact_eight43 import expand_core, packed_tensor
from .compact_coset43 import mode_slices
from .sat_neighborhoods import gf2_rank
from .tensor_code7 import atom_from_term
from .tensor_code7_extension import retain_raw_candidate
from .verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes
from scripts.tensor_code7 import save_candidate, Stop

ROOT = Path(__file__).resolve().parents[1]
C7 = ROOT / "artifacts/marathon7_20261103T122417Z"
PREP = "c3-mixed15-packets7-prep-001"
SOURCE = "tensor-code-source-anchors-v1/nodes/56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b.json"
SOURCE_SHA = "56e2dc2a4ce5e8082c35c9f45543b8325bbf99f68a5a72d935138afab4cdc78b"
ANCHORS = "26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8"
ELIGIBILITY = "7354183ab6e9c89f76110e1c916738ced4856499632a2f317508b1d6bea7bb55"
PINS = {
    PREP + "/catalog.json.gz": "b6df6ab005954168bf9a656d5f0c7e4d78fd3c5029a32dfb74f281ea836dc7c5",
    PREP + "/manifest.json": "9257959660cc1ec2ebaed56fc73cf9810d274fcfe15eb7293ef1a7b074eff2bc",
    PREP + "/COMPLETE.json": "c054a84e9f8ff55c82857e98b9b807595cb79840ba0f58cbfb066a21f41750a1",
    "tensor-code-source-anchors-v1/manifest.json": ANCHORS,
    "tensor-code-first120-proposal-v1/source-eligibility-root-approval.json": ELIGIBILITY,
    SOURCE: SOURCE_SHA,
    "campaign.json": "d71f859137dd407a29751f683afa97a0cbd23a91dbda4b6581bb5c477e671219",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def pinned(relative, root=C7):
    data = (Path(root) / relative).read_bytes()
    if sha(data) != PINS[relative]:
        raise ValueError("pinned pilot input changed: " + relative)
    return data


def select_plan(root=C7, core_pin_path=None, core_pin_sha256=None):
    """Metadata only: exactly the nine existing d11 deferred packets."""
    manifest = json.loads(pinned(PREP + "/manifest.json", root))
    seal = json.loads(pinned(PREP + "/COMPLETE.json", root))
    compressed = pinned(PREP + "/catalog.json.gz", root)
    if seal["manifest_sha256"] != PINS[PREP + "/manifest.json"] or manifest["catalog_sha256"] != sha(compressed):
        raise ValueError("native preparation seal/catalog binding changed")
    catalog = json.loads(gzip.decompress(compressed))
    anchors = json.loads(pinned("tensor-code-source-anchors-v1/manifest.json", root))
    approval = json.loads(pinned("tensor-code-first120-proposal-v1/source-eligibility-root-approval.json", root))
    if (approval.get("owner") != "root" or approval.get("approved_manifest_sha256") != ANCHORS
            or set(approval.get("approved_groups", [])) != {"anchors", "known_input_train_states"}):
        raise ValueError("independent root source-eligibility approval changed")
    eligible = [entry for group in ("anchors", "known_input_train_states") for entry in anchors[group]
                if entry["sha256"] == SOURCE_SHA]
    if not eligible or any(entry.get("heldout_excluded") is not True or entry.get("evaluation_excluded") is not True
                           or entry.get("root_approved_train") is not True for entry in eligible):
        raise ValueError("pilot source is absent from approved source/ancestry package")
    source = manifest["source"]
    if (source["raw_sha256"] != SOURCE_SHA or source["source_manifest_sha256"] != ANCHORS
            or source["root_eligibility_sha256"] != ELIGIBILITY or source["essential_products"] != 93):
        raise ValueError("native source provenance binding changed")
    rows = [row for row in catalog["packets"] if row["branch_metadata"]["d"] == 11]
    if len(rows) != 9 or len({row["id"] for row in rows}) != 9:
        raise ValueError("the authorized d11 scope must contain exactly nine distinct cases")
    for row in rows:
        b = row["branch_metadata"]
        if any(type(b.get(key)) is not int for key in ("d", "local_products", "target_local_products", "outside_products", "target_global_products")):
            raise ValueError("literal integer packet metadata required")
        if (b["local_products"], b["target_local_products"], b["outside_products"], b["target_global_products"]) != (15, 14, 78, 92):
            raise ValueError("authorized packet/rank envelope changed")
        if (b["mode_shape"] != [11] * 3 or b["actual_unfolding_ranks_by_independent_pair_columns"] != [11] * 3
                or b["branch"] != "RETAIN_DEFER_HIGHER_SURPLUS"):
            raise ValueError("only source-bound deferred d11 cases may be selected")
        ids = row["source_indices"]
        if len(ids) != 15 or ids != sorted(set(ids)) or any(type(i) is not int or not 0 <= i < 93 for i in ids):
            raise ValueError("invalid frozen source support")
    input_pins = dict(PINS)
    complete_core_pins = False
    if core_pin_path is not None:
        path = Path(core_pin_path).resolve(strict=True)
        if not path.is_relative_to(Path(root).resolve()) or not core_pin_sha256:
            raise ValueError("independent C7 nine-core raw pin required")
        data = path.read_bytes()
        if sha(data) != core_pin_sha256:raise ValueError("nine-core preparation bytes changed")
        prepared = json.loads(data)
        if (prepared.get("status") != "PREPARED_NINE_CORES_NO_QUERY" or prepared.get("source_sha256") != SOURCE_SHA
                or prepared.get("native_catalog_sha256") != PINS[PREP + "/catalog.json.gz"]):
            raise ValueError("nine-core source/catalog binding changed")
        records = prepared["cases"]
        if [entry["case"] for entry in records] != [row["id"] for row in rows]:
            raise ValueError("nine-core preparation changed selected case order")
        for row, entry in zip(rows, records):
            if entry["native_row_sha256"] != sha(raw(row)) or entry["actual_mode_ranks"] != [11] * 3:
                raise ValueError("nine-core row/rank binding changed")
            row["branch_metadata"].update(actual_core_checked=True,
                actual_core_sha256=entry["core_sha256"], ambient_sha256=entry["ambient_sha256"],
                actual_core_mode_ranks=entry["actual_mode_ranks"], core_input_sha256=entry["core_input_sha256"])
        input_pins[str(path.relative_to(Path(root).resolve()))] = core_pin_sha256
        complete_core_pins = True
    return dict(format="binary-block-nine-d11-plan.v1", cases=rows, source=SOURCE,
                source_sha256=SOURCE_SHA, input_sha256=input_pins, source_products=93,
                local_products=15, target_local_products=14, target_global_products=92,
                selected_cases_sha256=sha(raw(rows)), policy="fixed", case_seconds=12,
                invocation_seconds=120, memory_mib=1024, cpu=1, nice=10,
                core_pins_complete=complete_core_pins,
                scope="one heuristic attempt per selected case; UNKNOWN never closes a case")


def literal_terms(source):
    n = source.get("dimension")
    if type(n) is not int or not 1 <= n <= 5 or type(source.get("field")) is not int or source["field"] != 2:
        raise ValueError("literal F2 source dimension required")
    return [atom_from_term(term, n) for term in source["terms"]]


def build_packet_data(source, row, *, production=True, allow_unpinned_preparation=False):
    """Rebuild the FULL packet target in its frozen shared mode basis."""
    terms = literal_terms(source)
    n, width = source["dimension"], source["dimension"]**2
    ids = row["source_indices"]
    d = row["branch_metadata"]["d"]
    if type(d) is not int or not 0 < d <= 15:
        raise ValueError("literal compact dimension required")
    if production and (n, len(terms), len(ids), d) != (5, 93, 15, 11):
        raise ValueError("only approved n5/93/15/d11 source packets may run")
    if len(ids) != len(set(ids)) or any(type(i) is not int or not 0 <= i < len(terms) for i in ids):
        raise ValueError("invalid packet source indices")
    basis = BinaryBasis(row["shared_mode_basis"])
    if basis.vectors != row["shared_mode_basis"] or len(basis.vectors) != d:
        raise ValueError("frozen shared mode basis changed or is dependent")
    products = []
    ambient = 0
    for i in ids:
        coordinates = tuple(basis.coordinates(factor, require_member=True) for factor in terms[i])
        if tuple(basis.expand(v) for v in coordinates) != terms[i]:
            raise AssertionError("source factor did not lift from declared mode basis")
        products.append(coordinates)
        ambient ^= packed_tensor(terms[i], width)
    shape = [d] * 3
    compact_mask = block._tensor(products, shape)
    core = [(compact_mask >> i) & 1 for i in range(d**3)]
    expected_core = row["branch_metadata"].get("actual_core_sha256")
    if expected_core is None and not allow_unpinned_preparation:
        raise ValueError("an independently prepared exact core pin is required")
    if expected_core is not None and sha(bytes(core)) != expected_core:
        raise ValueError("full compact target differs from native frozen core hash")
    ambient_sha = sha(ambient.to_bytes((width**3 + 7) // 8, "little"))
    expected_ambient = row["branch_metadata"].get("ambient_sha256")
    if expected_ambient is None and not allow_unpinned_preparation:
        raise ValueError("an independently prepared exact ambient pin is required")
    if expected_ambient is not None and ambient_sha != expected_ambient:
        raise ValueError("selected original source packet differs from native ambient hash")
    bases = [list(basis.vectors) for _ in range(3)]
    if expand_core(core, shape, bases, width) != ambient:
        raise AssertionError("compact target failed exact full ambient expansion")
    if [gf2_rank(mode_slices(core, shape, axis)[0]) for axis in range(3)] != shape:
        raise ValueError("actual compact mode images differ from native dimensions")
    volumes = [a.bit_count() * b.bit_count() * c.bit_count() for a, b, c in products]
    removed = min(range(len(products)), key=lambda i: (volumes[i], ids[i]))
    initial = products[:removed] + products[removed + 1:]
    initial_loss = block.residual_loss(core, shape, initial)
    if initial_loss != volumes[removed]:
        raise AssertionError("drop-one initialization changed target or loss accounting")
    data = dict(core=core, shape=shape, image_bases=bases, source_indices=list(ids),
        outside_indices=[i for i in range(len(terms)) if i not in set(ids)],
        original_compact_products=[list(t) for t in products], initial_factors=[list(t) for t in initial],
        removed_local_index=removed, removed_source_index=ids[removed], removed_compact_volume=volumes[removed],
        initial_loss=initial_loss, target_core_sha256=sha(bytes(core)), target_ambient_sha256=ambient_sha,
        full_target_unchanged=True)
    expected_input = row["branch_metadata"].get("core_input_sha256")
    if expected_input is not None and sha(raw(data)) != expected_input:
        raise ValueError("lazy core/bases/initialization bytes differ from independently frozen core input")
    return data


def lift_candidate(source, data, products):
    core, shape, products = block._validate(data["core"], data["shape"], products)
    if block.residual_loss(core, shape, products) or block.scalar_loss(core, shape, products):
        raise ValueError("nonzero compact residual cannot be lifted as a solution")
    terms = literal_terms(source)
    lifted = []
    for product in products:
        point = []
        for mask, basis in zip(product, data["image_bases"]):
            value = 0
            for i in block._bits(mask):
                value ^= basis[i]
            point.append(value)
        lifted.append(tuple(point))
    parity = set()
    for point in [terms[i] for i in data["outside_indices"]] + lifted:
        if all(point):
            if point in parity:parity.remove(point)
            else:parity.add(point)
    n = source["dimension"]
    candidate = dict(dimension=n, field=2, terms=[
        {axis: [(value >> i) & 1 for i in range(n*n)] for axis, value in zip(("u", "v", "w"), point)}
        for point in sorted(parity)], metadata=dict(method="binary-block exact compact replacement",
            source_indices=data["source_indices"], source_core_sha256=data["target_core_sha256"],
            third_factor="trace: w[k*n+i] contributes to output[i][k]", novelty_claim=False))
    if len(candidate["terms"]) > len(terms) - len(data["source_indices"]) + len(products):
        raise AssertionError("outside78 plus local14 product-count bound failed")
    return candidate


def verify_raw_and_publish(source, data, observation, out, check, evidence=None,
                           *, production=True, independent_checker=None):
    """Hidden raw envelopes -> compact check -> full15625x2 -> guarded publish.

    The optional n2 path/independent checker exists only for protocol controls;
    the production CLI exposes neither override.
    """
    out = Path(out)
    raw_path = retain_raw_candidate(out, observation, "raw_compact_pending", evidence)
    result = dict(status="UNKNOWN", complete=False, raw_observation=str(raw_path.relative_to(out)))
    try:
        check("post_solve")
        if observation.get("status") != "RAW_EXACT_COMPACT":
            return result
        products = observation["raw_compact"]["products"]
        if production and (source["dimension"] != 5 or len(products) > 14):
            raise ValueError("global record requires n5 and at most14 packet products")
        candidate = lift_candidate(source, data, products)
        retain_raw_candidate(out, candidate, "pending_full_global_verification", evidence)
        check("post_compact_lift")
        full = verify_candidate(candidate, random_trials=0)
        check("post_full_ambient")
        n = source["dimension"]
        if not full["valid"] or full["exact_entries_checked"] != n**6 or (production and full["rank"] > 92):
            raise ValueError("full ambient replacement verification failed")
        independent = (independent_checker or verify_bytes)(raw(candidate))
        check("post_independent_ambient")
        if (independent.get("valid") is not True or independent.get("exact_entries_checked") != n**6
                or independent.get("essential_rank") != len(candidate["terms"])
                or (production and independent.get("record_eligible") is not True)):
            raise ValueError("independent full ambient replacement verification failed")
        atoms = [atom_from_term(t, n) for t in candidate["terms"]]
        saved = save_candidate(out, "first-record-evidence", atoms, (1 << len(atoms)) - 1, n,
            dict(evidence=evidence, full=full, independent=independent,
                 compact_target_sha256=data["target_core_sha256"]), guard=check)
        return dict(status="VERIFIED_TARGET" if production else "SMALL_CONTROL_PASSED", complete=True,
            candidate_sha256=saved["candidate_sha256"], candidate_path="first-record-evidence/candidate.json",
            full=full, independent=independent, saved=saved, raw_observation=str(raw_path.relative_to(out)))
    except Stop as exc:
        result.update(reason=str(exc), after_cutoff=True)
        return result
