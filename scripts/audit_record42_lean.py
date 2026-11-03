#!/usr/bin/env python3
"""Preserve, independently verify, export, and compile a record's explicit proof.

This script does not stop or signal searches. The operations guardian owns that
step. Normal invocation requires its stop marker and proof of no pending stops.
--published-baseline-control is explicitly limited to valid canonical R=93.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "scripts/verify_record42_independent.py"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def preserve(path, raw):
    """Exclusive creation and read-only permissions; never overwrites evidence."""
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def load_verifier(path):
    spec = importlib.util.spec_from_file_location("frozen_independent42", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stripped_lean(source):
    """Strip nested block and line comments before checking proof placeholders."""
    result, i, depth = [], 0, 0
    while i < len(source):
        if source.startswith("/-", i):
            depth += 1
            i += 2
        elif depth and source.startswith("-/", i):
            depth -= 1
            i += 2
        elif depth:
            i += 1
        elif source.startswith("--", i):
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
        else:
            result.append(source[i])
            i += 1
    if depth:
        raise ValueError("unclosed Lean comment")
    return "".join(result)


def source_audit(path):
    source = stripped_lean(path.read_text())
    forbidden = re.findall(r"\b(?:sorry|sorryAx|admit|axiom|constant|unsafe)\b", source)
    if forbidden:
        raise ValueError(f"unapproved Lean declarations/placeholders in {path.name}: {forbidden}")
    return {"no_sorry_or_custom_axioms": True, "sha256": sha(path.read_bytes())}


def run_bounded(command, log_path, cpus, env=None):
    def limits():
        os.nice(10)
        os.sched_setaffinity(0, cpus)
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_AS, (4*1024**3, 4*1024**3))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True,
                            preexec_fn=limits)
    timed_out = False
    try:
        output, _ = proc.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        output, _ = proc.communicate()
    preserve(log_path, output)
    return {"command": list(map(str, command)), "returncode": proc.returncode,
            "wall_seconds": time.monotonic()-started, "wall_timeout": timed_out,
            "cpu_limit_seconds_per_process": 30, "affinity": sorted(cpus),
            "address_space_limit_bytes": 4*1024**3, "nice_increment": 10,
            "log_sha256": sha(output)}


def check_axioms(log):
    allowed = {"propext", "Quot.sound", "Lean.ofReduceBool"}
    result = {}
    for theorem in ("coefficient_certificate", "multiplication_correct"):
        match = re.search(r"'ExplicitCertificate\." + theorem +
                          r"' depends on axioms: \[([^\]]*)\]", log)
        if not match:
            raise ValueError(f"missing #print axioms output for {theorem}")
        axioms = {part.strip() for part in match.group(1).split(",") if part.strip()}
        if not axioms <= allowed:
            raise ValueError(f"unapproved axioms for {theorem}: {sorted(axioms-allowed)}")
        result[theorem] = sorted(axioms)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--audit-root", required=True, type=Path)
    parser.add_argument("--campaign", type=Path,
                        help="campaign directory with guardian stop marker and operations-v3 state")
    parser.add_argument("--published-baseline-control", action="store_true")
    parser.add_argument("--cpus", help="one or two allowed CPU numbers, e.g. 2,3")
    args = parser.parse_args()
    available = os.sched_getaffinity(0)
    cpus = ({int(x) for x in args.cpus.split(",")} if args.cpus else set(sorted(available)[:2]))
    if not cpus <= available or not 1 <= len(cpus) <= 2:
        parser.error("--cpus must select one or two CPUs within current affinity")
    raw = args.certificate.read_bytes()
    args.audit_root.mkdir(parents=True, exist_ok=True)
    dest = (args.audit_root / (sha(raw) + "-" + str(time.time_ns()))).resolve()
    dest.mkdir()
    # The raw certificate and checksum are the very first persisted evidence.
    preserve(dest / "candidate.raw.json", raw)
    preserve(dest / "candidate.raw.sha256", (sha(raw)+"  candidate.raw.json\n").encode())
    report = {"format": "record42-lean-audit-v1", "audit_directory": str(dest.resolve()),
              "source_path": str(args.certificate.resolve()), "source_sha256": sha(raw),
              "published_baseline_control": args.published_baseline_control,
              "valid_explicit_lean_proof": False, "new_record_claim": False,
              "integer_lift_claim": False, "global_rank_lower_bound_claim": False,
              "native_evaluator_trust": "native_decide trusts Lean.ofReduceBool; not kernel-only evaluation",
              "evidence_immutability": "exclusive-created read-only copies; owner can still alter filesystem permissions",
              "steps": [], "errors": []}
    try:
        frozen = {}
        for name, source in (("verify_record42_independent.py", VERIFIER_PATH),
                             ("export_lean.py", ROOT / "scripts/export_lean.py"),
                             ("Certificate.lean", ROOT / "lean/Certificate.lean"),
                             ("audit_record42_lean.py", Path(__file__))):
            evidence = source.read_bytes()
            preserve(dest / name, evidence)
            frozen[name] = sha(evidence)
        preserve(dest / "source-checksums.json", json_bytes(frozen))
        verifier = load_verifier(dest / "verify_record42_independent.py")
        verification = verifier.verify_bytes(raw)
        preserve(dest / "independent.verification.json", json_bytes(verification))
        report["independent_verification"] = verification
        if not verification["valid"]:
            raise ValueError("independent full basis/output verification rejected the certificate")
        rank = verification["canonical_essential_products"]
        if args.published_baseline_control:
            if rank != 93:
                raise ValueError("published baseline control requires canonical R exactly 93")
        else:
            if not verification["record_eligible"]:
                raise ValueError("record proof requires independently valid canonical R<=92")
            if not args.campaign:
                raise ValueError("record proof requires --campaign stop evidence; guardian must finish stops first")
            marker = args.campaign / "guard_stopped.json"
            state = args.campaign / "operations-v3/state.json"
            # The guardian has a dispatch barrier before TERM/KILL completion.
            # Require both barrier and completed identity-safe process-group reaping.
            marker_raw, state_raw = marker.read_bytes(), state.read_bytes()
            marker_value = json.loads(marker_raw, object_pairs_hook=verifier._unique_object)
            state_value = json.loads(state_raw, object_pairs_hook=verifier._unique_object)
            preserve(dest / "guardian-stop-marker.json", marker_raw)
            preserve(dest / "guardian-state.json", state_raw)
            if (marker_value.get("operations_version") != 3 or
                    not state_value.get("stop_reason") or state_value.get("pending_stops") != []):
                raise ValueError("guardian stop evidence does not establish completed campaign stop")
        canonical, _ = verifier.canonical_terms(verifier.parse_certificate(raw))
        preserve(dest / "candidate.canonical.json",
                 (json.dumps(verifier.canonical_certificate(canonical), sort_keys=True,
                             separators=(",", ":"))+"\n").encode())
        lean = ROOT / "lean/.toolchain/lean-4.19.0-linux/bin/lean"
        report["lean_launcher_sha256"] = sha(lean.read_bytes())
        for command, name in (([str(lean), "--version"], "lean-version.log"),
                              ([sys.executable, str(dest / "export_lean.py"), "--native",
                                str(dest / "candidate.canonical.json"), str(dest / "ExplicitCandidate.lean")], "export.log")):
            step = run_bounded(command, dest / name, cpus)
            report["steps"].append(step)
            if step["returncode"] != 0:
                raise ValueError(f"{name} failed")
        (dest / "ExplicitCandidate.lean").chmod(0o444)
        report["source_audits"] = {name: source_audit(dest / name)
                                   for name in ("Certificate.lean", "ExplicitCandidate.lean")}
        if "version 4.19.0" not in (dest / "lean-version.log").read_text():
            raise ValueError("expected Lean 4.19.0")
        for command, name, env in (([str(lean), "-j2", "--root=" + str(dest), "-o", str(dest / "Certificate.olean"),
                                     str(dest / "Certificate.lean")], "core-compile.log", None),
                                   ([str(lean), "-j2", "--root=" + str(dest), str(dest / "ExplicitCandidate.lean")], "explicit-compile.log",
                                    dict(os.environ, LEAN_PATH=str(dest)))):
            step = run_bounded(command, dest / name, cpus, env)
            report["steps"].append(step)
            if step["returncode"] != 0:
                raise ValueError(f"{name} failed; no explicit Lean proof is claimed")
        log = (dest / "explicit-compile.log").read_text()
        if re.search(r"\b(?:error|sorryAx)\b", log):
            raise ValueError("explicit compilation output contains an error or sorryAx")
        report["axiom_audit"] = check_axioms(log)
        report["valid_explicit_lean_proof"] = True
        report["proof_scope"] = "all 5x5 input matrices over F2; canonical R=" + str(rank)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report["errors"].append(str(exc))
    preserve(dest / "audit-report.json", json_bytes(report))
    checksums = {p.name: sha(p.read_bytes()) for p in dest.iterdir() if p.is_file()}
    preserve(dest / "all-checksums.json", json_bytes(checksums))
    print(json.dumps({"audit_directory": str(dest), "valid_explicit_lean_proof": report["valid_explicit_lean_proof"],
                      "errors": report["errors"]}, indent=2))
    return 0 if report["valid_explicit_lean_proof"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
