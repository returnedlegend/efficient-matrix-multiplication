#!/usr/bin/env python3
"""One authorized static margin audit, no feasible-state optimization or SAT."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
from mmsearch.kernel_projection_dominance7 import inspect_dominance, HARD_DEADLINE
from mmsearch.marathon7_cached_guard import CampaignGuard, CampaignHold
from mmsearch.tensor_code7 import strict_load
from mmsearch.tensor_code7_extension import plus_atoms

C7 = REPO / "artifacts/marathon7_20261103T122417Z"
CAP = 32 * 1024**2
PINS = {
    "campaign.json": "d71f859137dd407a29751f683afa97a0cbd23a91dbda4b6581bb5c477e671219",
    "tensor-code-prep-001/prepared.json": "cf4644cab66d697f05d6724d919973b9884f17def9586c0e1220b9ea67554e2b",
    "tensor-code-extension-prep-001/prepared.json": "8525c790c7c246e2694716d7500399db676c54b72aad0341bf5145383aa92df3",
    "tensor-code-witnesses-001/witnesses.json": "1e157fd8c7b2838ebb54329633cae812fdfa147ae02dc0f133e6dc0af49fb20f",
    "cyclic-orbit-code7-audit-002/dictionary.json": "23ff2b7ef344b79277712731cdc80ecc4b030a82026ca77d9fec32a02ebd047b",
    "cyclic-orbit-code7-audit-002/manifest.json": "eb6337722adaf26ecc3e11795cc94865c2a556db7af70d4efd83b917bb0a392b",
    "cyclic-polarization7-audit-001/dictionary.json": "4b94540939eaa1f7c06d777729bfb2d2f28312eac81dfb2d7a3beb83098c00fb",
    "cyclic-polarization7-audit-001/manifest.json": "abaf21f4402c02ef0175b98fe90c82dc76c5c7a2b861a291e9c956346eae2dbd",
    "cyclic-polarization7-audit-001/pair-witness.json": "a081ed8355a348891898d0d520a316b644dee44643ad68de85c52174535c1214",
}
ANCHORS = "26d95607f6379c182b96aa9beaf451d419c7abb20b6185ebf0abf3b9f54eabe8"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def xor(columns, mask):
    value = 0
    for i in bits(mask):
        value ^= columns[i]
    return value


def atom_column(atom):
    if len(atom) != 3 or any(type(v) is not int or not 0 < v < 1 << 25 for v in atom):
        raise ValueError("invalid literal n5 atom")
    value = 0
    for a in bits(atom[0]):
        for b in bits(atom[1]):
            for c in bits(atom[2]):
                value ^= 1 << ((a * 25 + b) * 25 + c)
    return value


def exact_target():
    return sum(1 << (((i * 5 + j) * 25 + j * 5 + k) * 25 + k * 5 + i)
               for i in range(5) for j in range(5) for k in range(5))


def permute_mask(mask, physical_order):
    return sum(((mask >> physical) & 1) << aligned for aligned, physical in enumerate(physical_order))


class Audit:
    def __init__(self, dataset, output):
        self.dataset, self.output = dataset, output
        self.started, self.cpu_started = time.monotonic(), time.process_time()
        self.guard = CampaignGuard(30, "2026-11-03T19:24:17Z", guard_state=C7 / "operations-v3/state.json",
                                   campaign_dir=C7)
        self.signal_stop = False
        self.last_hold = None
        self.ticks = 0
        self.input_pins, self.code_pins = {}, {}
        self.output_bytes = 0
        signal.signal(signal.SIGINT, self.signal)
        signal.signal(signal.SIGTERM, self.signal)

    def signal(self, *_):
        self.signal_stop = True
        self.guard.stop()

    def stage(self, label):
        self.guard.check(label)

    def cancelled(self):
        # Inspector checks its own UTC and monotonic budget every state. Signals
        # are checked here every state; canonical file I/O is checked <=256 steps.
        self.ticks += 1
        if self.signal_stop:
            return True
        if self.ticks % 256 == 0:
            self.last_hold = self.guard.reason(force=True)
        return self.last_hold is not None

    def independent_tick(self):
        if self.signal_stop or time.time() >= HARD_DEADLINE or time.monotonic() - self.started >= 30:
            raise CampaignHold("static audit clock/signal cutoff", "independent_margin_scan")
        if self.cancelled():
            raise CampaignHold(self.last_hold or "signal", "independent_margin_scan")

    def save(self, name, raw):
        if self.output_bytes + len(raw) > CAP:
            raise ValueError("audit output cap32MiB exceeded")
        path = self.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
        self.output_bytes += len(raw)

    def read(self, relative):
        self.stage("pre_input:" + relative)
        raw = (C7 / relative).read_bytes()
        if sha(raw) != PINS[relative]:
            raise ValueError("root-pinned input bytes changed: " + relative)
        self.input_pins[relative] = PINS[relative]
        self.save("inputs/" + relative, raw)
        return strict_load(raw)

    def generic(self):
        base = self.read("tensor-code-prep-001/prepared.json")
        extended = self.read("tensor-code-extension-prep-001/prepared.json")
        witnesses = self.read("tensor-code-witnesses-001/witnesses.json")
        if base["source_manifest_sha256"] != ANCHORS or extended["source_manifest_sha256"] != ANCHORS:
            raise ValueError("approved32-source binding changed")
        if extended["base_prepared_sha256"] != PINS["tensor-code-prep-001/prepared.json"] or extended["extension_witnesses_sha256"] != PINS["tensor-code-witnesses-001/witnesses.json"]:
            raise ValueError("base/witness preparation binding changed")
        if witnesses["base_prepared_sha256"] != extended["base_prepared_sha256"]:
            raise ValueError("authenticated witness base changed")
        if (len(base["atoms"]), len(extended["atoms"]), base["rank"], extended["rank"], base["nullity"], extended["nullity"]) != (406, 444, 309, 331, 97, 113):
            raise ValueError("authorized dictionary/rank envelope changed")
        if extended["atoms"][:406] != base["atoms"] or extended["seed_states_hex"] != base["seed_states_hex"] or extended["seed_weights"] != [93] * 32:
            raise ValueError("old atoms or padded source masks changed")
        columns = [int(c, 16) for c in extended["columns_hex"]]
        for atom, column in zip(extended["atoms"], columns):
            if self.cancelled():
                raise CampaignHold(self.last_hold or "signal", "existing_atom_validation")
            if atom_column(atom) != column:
                raise ValueError("existing full atom column mismatch")
        lookup = {tuple(atom): i for i, atom in enumerate(extended["atoms"])}
        lifts = []
        if len(witnesses["relations"]) != 16 or len(extended["odd_relation_certificates"]) != 16:
            raise ValueError("expected16 authenticated short relations")
        for record, certificate in zip(witnesses["relations"], extended["odd_relation_certificates"]):
            self.stage("short_relation_validation")
            parents = [tuple(base["atoms"][i]) for i in record["parent_atom_ids"]]
            derived = plus_atoms(*parents, record["axis_permutation"], 5)
            if [list(a) for a in derived] != record["new_atoms"] or record["id"] != certificate["id"]:
                raise ValueError("short relation differs from pinned witness")
            lift = sum(1 << lookup[a] for a in parents + derived)
            if lift.bit_count() != 5 or lift != int(certificate["cycle_hex"], 16) or xor(columns, lift):
                raise ValueError("short full-column relation invalid")
            lifts.append(lift)
        return (base, extended, [int(c, 16) for c in base["columns_hex"]], columns,
                [1] * 406, [1] * 444, int(base["seed_states_hex"][0], 16),
                [int(c, 16) for c in extended["kernel_hex"]], lifts,
                dict(old_state_policy="only pinned seed0 feasibility; no seed/extension state search",
                     authenticated_short_relations=16, projection_fill_used=False))

    def c3(self):
        base = self.read("cyclic-orbit-code7-audit-002/dictionary.json")
        base_manifest = self.read("cyclic-orbit-code7-audit-002/manifest.json")
        extended = self.read("cyclic-polarization7-audit-001/dictionary.json")
        manifest = self.read("cyclic-polarization7-audit-001/manifest.json")
        witness = self.read("cyclic-polarization7-audit-001/pair-witness.json")
        if manifest["dictionary_sha256"] != PINS["cyclic-polarization7-audit-001/dictionary.json"] or manifest["base_dictionary_sha256"] != PINS["cyclic-orbit-code7-audit-002/dictionary.json"]:
            raise ValueError("cyclic dictionary receipt binding changed")
        if base["source_manifest_sha256"] != ANCHORS or manifest["source_manifest_sha256"] != ANCHORS:
            raise ValueError("cyclic approved-source binding changed")
        if (len(base["representatives"]), len(extended["representatives"]), base["rank"], extended["rank"], base["nullity"], extended["nullity"]) != (275, 278, 201, 203, 74, 75):
            raise ValueError("authorized C3 envelope changed")
        order = manifest["old_to_new_column_map"] + manifest["new_column_indices"]
        if sorted(order) != list(range(278)):
            raise ValueError("physical-to-aligned orbit permutation incomplete")
        physical_columns = [int(c, 16) for c in extended["full_columns_hex"]]
        for representative, column, weight in zip(extended["representatives"], physical_columns, extended["weights"]):
            if self.cancelled():
                raise CampaignHold(self.last_hold or "signal", "existing_orbit_validation")
            a, b, c = representative
            members = {(a, b, c), (b, c, a), (c, a, b)}
            if tuple(representative) != min(members) or weight != len(members):
                raise ValueError("whole-orbit representative/cost mismatch")
            value = 0
            for member in members:
                value ^= atom_column(member)
            if value != column:
                raise ValueError("full whole-orbit column mismatch")
        for old, physical in enumerate(order[:275]):
            if base["representatives"][old] != extended["representatives"][physical]:
                raise ValueError("mapped old physical orbit identity mismatch")
        columns = [physical_columns[i] for i in order]
        weights = [extended["weights"][i] for i in order]
        lift = permute_mask(int(witness["relation_hex"], 16), order)
        seed = int(base["seed_state_hex"], 16)
        if permute_mask(int(extended["seed_state_hex"], 16), order) != seed:
            raise ValueError("cyclic old feasible state changed under mapping")
        proof = dict(physical_order=order, old_state_policy="one pinned C3 seed feasibility only",
                     physical_relation_hex=witness["relation_hex"], aligned_relation_hex=hex(lift),
                     old_relation_cost=sum(weights[i] for i in bits(lift & ((1 << 275) - 1))),
                     new_relation_cost=sum(weights[275 + i] for i in bits(lift >> 275)),
                     new_projection_hex=hex(lift >> 275), projection_fill_used=False)
        if (lift.bit_count(), proof["old_relation_cost"], proof["new_relation_cost"], lift >> 275) != (5, 2, 7, 7) or xor(columns, lift):
            raise ValueError("independent known weighted five-relation check failed")
        return (base, extended, [int(c, 16) for c in base["full_columns_hex"]], columns,
                base["weights"], weights, seed,
                [permute_mask(int(c, 16), order) for c in extended["kernel_hex"]], [lift], proof)

    def run(self):
        self.stage("pre_static_audit")
        self.read("campaign.json")
        base, extended, old, columns, old_weights, weights, seed, kernel, lifts, proof = getattr(self, self.dataset)()
        target = exact_target()
        if int(base["target_hex"], 16) != target or int(extended["target_hex"], 16) != target or xor(old, seed) != target:
            raise ValueError("independent exact target/old seed feasibility check failed")
        if sum(old_weights[i] for i in bits(seed)) != 93:
            raise ValueError("authorized old seed cost is not93")
        self.stage("pre_kernel_projection_inspection")
        result = inspect_dominance(old, columns, target, seed, base_weights=old_weights,
            extended_weights=weights, extended_kernel=kernel, projection_lifts=lifts,
            cancelled=self.cancelled, timeout_seconds=max(0, 30 - (time.monotonic() - self.started)))
        if result["status"] == "UNKNOWN":
            return dict(result=result, proof=proof, status="UNKNOWN", complete=False)
        expected_rank = 16 if self.dataset == "generic" else 1
        if result["projected_kernel_rank"] != expected_rank:
            raise ValueError("complete projected-kernel dimension differs from approved envelope")
        self.stage("pre_independent_margin_enumeration")
        # Independent ordinary binary subset scan, not the inspector's Gray loop.
        # Costs are zero-relation old/new differences; no feasible x is constructed.
        margins = []
        old_mask = (1 << len(old)) - 1
        for alpha in range(1 << len(lifts)):
            self.independent_tick()
            relation = 0
            for i in bits(alpha):
                relation ^= lifts[i]
            old_part, new_part = relation & old_mask, relation >> len(old)
            old_cost = sum(old_weights[i] for i in bits(old_part))
            new_cost = sum(weights[len(old) + i] for i in bits(new_part))
            margins.append(new_cost - old_cost)
        if (min(margins), min(margins[1:])) != (result["minimum_margin"], result["minimum_nonzero_margin"]):
            raise ValueError("independent weighted margin minimum disagrees")
        proof.update(independent_margin_states=len(margins), independent_minimum_margin=min(margins),
                     independent_minimum_nonzero_margin=min(margins[1:]),
                     independent_margin_histogram={str(m): margins.count(m) for m in sorted(set(margins))},
                     full_columns_reconstructed=True, independent_target_and_old_seed_verified=True,
                     no_oldseed_extension_combinations_constructed=True)
        if self.dataset == "c3" and (result["status"], result["minimum_nonzero_margin"]) != ("DOMINATED", 5):
            raise ValueError("C3 known short-lift certificate disagrees with independent cost2/7 check")
        self.stage("post_complete_static_audit")
        for relative, expected in self.input_pins.items():
            if sha((C7 / relative).read_bytes()) != expected:
                raise ValueError("immutable source changed during audit")
        self.stage("pre_static_certificate_publication")
        return dict(status=result["status"], complete=True, result=result, proof=proof)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", choices=("generic", "c3"), required=True)
    p.add_argument("--outdir", type=Path, required=True)
    p.add_argument("--authorize-static-audit", action="store_true")
    args = p.parse_args()
    if not args.authorize_static_audit:
        print(json.dumps(dict(status="DISABLED", production_inputs_read=False)))
        return
    os.sched_setaffinity(0, {1})
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.nice(10 - os.getpriority(os.PRIO_PROCESS, 0))
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (CAP, CAP))
    output = args.outdir.resolve()
    if not output.is_relative_to(C7) or output.exists():
        raise ValueError("fresh C7 output directory required")
    output.mkdir()
    audit = Audit(args.dataset, output)
    try:
        result = audit.run()
    except CampaignHold as exc:
        result = dict(status="UNKNOWN", complete=False, stop_reason=str(exc))
    except Exception as exc:
        result = dict(status="FAILED_CLOSED", complete=False, error_type=type(exc).__name__, error=str(exc))
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(REPO) and path.suffix == ".py":
                relative = str(path.relative_to(REPO))
                if relative not in audit.code_pins:
                    raw = path.read_bytes()
                    audit.code_pins[relative] = sha(raw)
                    audit.save("code/" + relative, raw)
    if "scripts/audit_kernel_projection_dominance7.py" not in audit.code_pins:
        raw = Path(__file__).read_bytes()
        audit.code_pins["scripts/audit_kernel_projection_dominance7.py"] = sha(raw)
        audit.save("code/scripts/audit_kernel_projection_dominance7.py", raw)
    if result.get("complete"):
        try:
            audit.stage("final_certificate_publication")
        except CampaignHold as exc:
            result.update(status="UNKNOWN", complete=False, stop_reason=str(exc))
            if "result" in result:
                result["result"].update(status="UNKNOWN", complete=False, minimum_equality_certified=False)
    result.update(dataset=args.dataset, input_sha256=audit.input_pins, code_sha256=audit.code_pins,
                  elapsed_seconds=time.monotonic() - audit.started,
                  process_cpu_seconds=time.process_time() - audit.cpu_started,
                  cpu_affinity=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
                  address_space_limit_bytes=resource.getrlimit(resource.RLIMIT_AS)[0],
                  max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  signal_stop=audit.signal_stop, canonical_guard_observation=audit.guard.observation(),
                  optimization_called=False, target_sat_called=False, no_record_or_novelty_claim=True)
    audit.save("result.json", (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    audit.save("checksums.json", (json.dumps({str(path.relative_to(output)): sha(path.read_bytes())
        for path in output.rglob("*") if path.is_file()}, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps(dict(status=result["status"], complete=result["complete"], dataset=args.dataset,
        projected_rank=result.get("result", {}).get("projected_kernel_rank"),
        minimum_nonzero_margin=result.get("result", {}).get("minimum_nonzero_margin"),
        output=str(output), output_bytes=audit.output_bytes, elapsed_seconds=result["elapsed_seconds"]), sort_keys=True))


if __name__ == "__main__":
    main()
