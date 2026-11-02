"""Read saved campaign evidence into a small, explicitly whitelisted report.

Never executes search commands or copies nested solver/preprocessing metadata.
Live snapshots are interim until campaign.json says state=completed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "artifacts/campaign_20261102T164324Z"
OUTCOMES = ("SAT", "UNSAT", "UNKNOWN", "ERROR")
COUNTERS = OUTCOMES + ("proposals", "flattening_rejected", "koszul_rejected",
                       "duplicate_cnfs", "orientation_rejections", "p2_rejections")
AUDIT_KEYS = ("neighborhoods", "exact_bound_rejected", "solver_unsat",
              "bound_and_solver_unsat", "negative_union", "sat", "unknown_only",
              "unresolved", "error_present", "contradictions")


def read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def scalars(value, keys):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in keys if key in value and
            (value[key] is None or type(value[key]) in (str, int, float, bool))}


def sha(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def relative(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def command(value):
    return value if isinstance(value, list) and all(type(x) is str for x in value) else []


def collect(directory, audit_path=None):
    cfg = read(directory / "campaign.json")
    status = read(directory / "status.json")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    result = {"generated_utc": now, "campaign_directory": relative(directory),
              "campaign": scalars(cfg, ("started_utc", "deadline_utc", "state", "field",
                   "target_rank", "max_cpu_cores", "max_ram_gib", "seed")),
              "interim": cfg.get("state") != "completed", "status_saved_utc": status.get("utc"),
              "best_accessible_reference_rank": 93, "scope": "exact bilinear 5x5 over F2 only",
              "warnings": []}
    jobs = []
    for path in sorted(directory.glob("*job.result.json")):
        data = read(path)
        item = {"file": relative(path), **scalars(data, ("started_utc", "cpu", "memory_mb",
                  "wall_seconds", "exit_code", "timed_out", "interrupted", "elapsed_seconds",
                  "cpu_seconds", "max_rss_kib")), "command": command(data.get("command"))}
        jobs.append(item)
    active = [{"file": relative(p), **scalars(read(p), ("started_utc", "cpu", "memory_mb",
               "wall_seconds", "pid")), "command": command(read(p).get("command"))}
              for p in sorted(directory.glob("*job.running.json"))]
    resource = read(directory / "resource_status.json")
    result["resources"] = {
        "completed_tracked_jobs": len(jobs), "recorded_running_jobs": len(active),
        "completed_job_cpu_seconds": sum(j.get("cpu_seconds", 0) for j in jobs),
        "maximum_observed_worker_rss_kib": max([0] + [j.get("max_rss_kib", 0) for j in jobs]),
        **scalars(resource, ("utc", "rss_bytes", "maximum_observed_rss_bytes", "measurement")),
        "accounting_scope": "CPU sums completed limited-worker jobs only; active/unwrapped work excluded. RSS is sampled, not a certified peak."}
    result["completed_jobs"], result["recorded_running_jobs"] = jobs, active
    native, by_branch = [], defaultdict(lambda: {"phases": 0, "steps": 0, "best_rank": 93})
    for path in sorted((directory / "native").glob("*/phase-*/walk.stats.json")):
        data = read(path)
        item = {"branch": path.parts[-3], "phase": path.parts[-2],
                **scalars(data, ("steps", "best_rank", "current_rank", "elapsed_seconds",
                      "target_rank", "target_reached", "tensor_invariant_checked", "stopped_by_signal"))}
        native.append(item)
        group = by_branch[item["branch"]]
        group["phases"] += 1
        group["steps"] += item.get("steps", 0)
        group["best_rank"] = min(group["best_rank"], item.get("best_rank", 93))
    result["native"] = {"steps": sum(x["steps"] for x in by_branch.values()),
                        "best_rank": min([93] + [x["best_rank"] for x in by_branch.values()]),
                        "branches": dict(by_branch), "phases": native,
                        "checkpoint_note": "Final checkpoint drain bug was fixed; earlier saved runs reported best93. Frozen versions/hashes retained."}
    sat, total = [], Counter()
    for path in sorted(directory.glob("*/manifest.json")):
        name = path.parent.name
        if name != "sat" and not name.startswith(("compact-", "xor-lex", "koszul-", "oriented-")):
            continue
        if "smoke" in name or "control" in name:
            continue
        data = read(path)
        counts = scalars(data.get("counters", {}), COUNTERS)
        total.update({k: v for k, v in counts.items() if type(v) is int})
        sat.append({"branch": name, "manifest_sha256": sha(path),
                    **scalars(data, ("attempts", "encoding", "symmetry", "scope")),
                    "identity": scalars(data.get("identity", {}),
                        ("dimension", "target_rank", "k_min", "k_max", "seed")), "counters": counts})
    result["local_sat"] = {"branches": sat, "raw_manifest_totals": dict(total),
                           "scope": "Raw attempts/counters can overlap; controls, smoke tests and dictionary models excluded."}
    dictionaries = []
    for path in sorted(directory.rglob("manifest.json")):
        if any("smoke" in part or "control" in part for part in path.relative_to(directory).parts):
            continue
        data = read(path)
        if data.get("dimension") != 5 or data.get("rank_bound") != 92 or not data.get("dictionary_size"):
            continue
        outcome = read(path.parent / "result.json")
        control = read(path.parent / "control.result.json")
        dictionaries.append({"branch": str(path.parent.relative_to(directory)),
             "manifest_sha256": sha(path), **scalars(data, ("dictionary_size", "rank_bound",
              "dictionary_sha256", "formula_sha256", "cardinality_encoding", "independent_equations",
              "linear_nullity", "scope")), "solver_budget": scalars(data.get("solver_budget", {}),
              ("conflicts", "memory_mb", "threads", "total_wall_seconds")),
             "status": outcome.get("status", "NO_SAVED_RESULT"),
             "control_status": outcome.get("control_status", control.get("status")),
             "elapsed_seconds": outcome.get("total_elapsed_seconds"),
             "preprocessing": scalars(data.get("preprocessing", {}), ("forced_ones", "forced_zeros",
                         "cardinality_constant", "residual_cardinality_bound", "weighted_literal_count"))})
    result["dictionaries"] = dictionaries
    result["heuristics"] = {
        "als_rank92": scalars(read(directory / "als-r92-s0.verification.json"),
                             ("valid", "rank", "mismatch_count", "exact_entries_checked")),
        "targeted_repair": scalars(read(directory / "targeted-repair/manifest.json"),
                                   ("attempts", "best_residual", "scope")),
        "finite_pool_recombination": scalars(read(directory / "recombine-full/summary.json"),
                 ("sources", "dictionary_size", "evaluations", "best_rank", "local_cycle_minimum", "scope"))}
    group_path = directory / "native/group93/manifest.json"
    group = read(group_path)
    result["heuristics"]["group_equivalent_seeds"] = {
        "manifest": relative(group_path), "manifest_sha256": sha(group_path),
        **scalars(group, ("engine", "dimension", "rank", "variants_generated", "selected_count",
              "all_variants_independently_verified", "exact_entries_checked_per_variant",
              "known_equivalent", "novel", "forced_one_count", "released_count", "new_terms",
              "dictionary_size", "source_sha256", "group_terms_sha256")),
        "selected": [scalars(item, ("id", "newly_released", "total_released"))
                     for item in group.get("selected", []) if isinstance(item, dict)],
        "remaining_forced_count": len(group.get("remaining_forced_terms", [])),
        "scope": "Known-equivalent basis transforms broaden term dictionaries; no new algorithm or inequivalence claim."}
    public = ROOT / "artifacts/campaign/public-seeds/fastmatrix-f2/manifest.json"
    result["public_seeds"] = {"manifest": relative(public), "sha256": sha(public),
             **scalars(read(public), ("repository", "commit", "source_files", "distinct_term_sets", "rank")),
             "verification": "307 imported term sets independently checked on all15625 F2 coefficients; no inequivalence claim."}
    portfolio = read(directory / "satseed_portfolio.json")
    result["sampled_rank93_portfolio"] = {**scalars(portfolio, ("new_term_sets", "scope")),
             "source_count": len(portfolio.get("sources", [])), "rank_improvement": False}
    tests = directory / "test_suite_final.log"
    text = tests.read_text(errors="replace") if tests.exists() else ""
    matches = re.findall(r"Ran (\d+) tests in ([\d.]+)s\s+OK", text)
    result["tests"] = {"log": relative(tests), "sha256": sha(tests),
             "passed": int(matches[-1][0]) if matches else None,
             "seconds": float(matches[-1][1]) if matches else None,
             **scalars(read(directory / "test_suite_final.result.json"), ("exit_code", "utc"))}
    result["lean"] = {**scalars(read(directory / "lean_baseline93.result.json"),
                ("exit_code", "utc", "scope", "source_sha256", "certificate_sha256")),
             "axioms": ["propext", "Lean.ofReduceBool", "Quot.sound"],
             "scope_note": "Published rank93 baseline only; native_decide evaluation trust remains."}
    result["verified_target_candidates"] = []
    for path in sorted(set(directory.rglob("FOUND.json")) | set(directory.rglob("WINNER.json"))):
        data = read(path)
        if data.get("field") == 2 and data.get("dimension") == 5 and 0 < len(data.get("terms", [])) <= 92:
            sys.path.insert(0, str(ROOT))
            from mmsearch.verify import verify_candidate
            check = verify_candidate(data)
            if check["valid"]:
                result["verified_target_candidates"].append({"file": relative(path), "sha256": sha(path),
                           "rank": check["rank"], "exact_entries_checked": check["exact_entries_checked"]})
    if audit_path is None:
        candidates = sorted((ROOT / "research/campaign").glob("sat_audit_*.json"), key=lambda p: p.stat().st_mtime)
        audit_path = candidates[-1] if candidates else None
    if audit_path:
        audit = read(audit_path)
        result["sat_audit"] = {"file": relative(audit_path), "sha256": sha(audit_path),
               **scalars(audit, ("audit_valid", "recorded_utc")),
               "raw_record_counts": scalars(audit.get("raw_record_counts", {}), OUTCOMES + ("BOUND",)),
               "uniform_summary": scalars(audit.get("uniform_summary", {}), AUDIT_KEYS),
               "conditional_summary": scalars(audit.get("conditional_summary", {}), AUDIT_KEYS)}
    else:
        result["sat_audit"] = {"available": False}
    result["limitations"] = ["UNSAT is local to frozen neighborhoods or dictionaries, never a global rank lower bound.",
          "Dictionary UNSAT has no independently checked UNSAT trace; rank93 SAT controls are separate.",
          "UNKNOWN, interruptions and heuristic exhaustion are not UNSAT.",
          "arXiv access was denied; global literature novelty is unconfirmed (RECORD_CHECK.md).",
          "F2 results do not establish a literal integer identity or measured matrix-runtime speedup."]
    result["evidence"] = {"frozen_directory": relative(directory / "frozen"),
           "final_code_hash_manifest": relative(directory / "final_search_code_hashes.json"),
           "final_code_hash_manifest_sha256": sha(directory / "final_search_code_hashes.json"),
           "adaptation_history": "research/campaign/RUNNING_HANDOFF.md",
           "interventions": relative(directory / "interventions.jsonl")}
    return result


def markdown(data):
    cfg, resources = data["campaign"], data["resources"]
    label = "INTERIM" if data["interim"] else "COMPLETED"
    candidates = data["verified_target_candidates"]
    outcome = ("Verified target candidate found; inspect the exact certificate before any novelty claim."
               if candidates else "No independently verified candidate of rank 92 or lower is recorded; best accessible verified reference remains 93.")
    lines = [f"# Two-hour F2 matrix multiplication search — {label}", "",
        outcome, "", f"Generated {data['generated_utc']}; campaign state `{cfg.get('state', 'unknown')}`.",
        f"Window: {cfg.get('started_utc')} to {cfg.get('deadline_utc')}; target ≤{cfg.get('target_rank')} products.",
        "The experiment concerns exact bilinear 5×5 multiplication over F2.", "",
        "## Resources and search", "",
        f"Caps: {cfg.get('max_cpu_cores')} CPU cores, {cfg.get('max_ram_gib')} GiB RAM; worker affinity CPUs 0–3 and inherited address-space limits.",
        f"Completed tracked worker CPU: {resources['completed_job_cpu_seconds']:.1f}s across {resources['completed_tracked_jobs']} jobs; {resources['recorded_running_jobs']} saved running records.",
        f"Largest completed-worker reported RSS: {resources['maximum_observed_worker_rss_kib']/1024:.1f}MiB; guard maximum observed aggregate RSS: {resources.get('maximum_observed_rss_bytes', 0)/1024**2:.1f}MiB.",
        "CPU excludes active and unwrapped work. RSS samples can miss peaks; aggregate ps measurements count shared pages repeatedly.",
        "No paid external compute or publication was used.", "", "| Native branch | Saved phases | Steps | Best rank |", "|---|---:|---:|---:|"]
    for name, item in data["native"]["branches"].items():
        lines.append(f"| {name} | {item['phases']} | {item['steps']:,} | {item['best_rank']} |")
    heur = data["heuristics"]
    recomb = heur["finite_pool_recombination"]
    lines += ["", f"Finite-pool recombination: {recomb.get('sources')} source algorithms, {recomb.get('dictionary_size')} columns, {recomb.get('evaluations')} evaluations, best rank {recomb.get('best_rank')}; local minimum only.",
              f"ALS rank-92 certificate remained invalid ({heur['als_rank92'].get('mismatch_count')} coefficient mismatch); targeted repair completed {heur['targeted_repair'].get('attempts')} slices without an accepted target certificate.",
              "", "| Local SAT branch | Attempts | SAT | UNSAT | UNKNOWN | ERROR |", "|---|---:|---:|---:|---:|---:|"]
    for item in data["local_sat"]["branches"]:
        lines.append(f"| {item['branch']} | {item.get('attempts', 0)} | " + " | ".join(str(item["counters"].get(k, 0)) for k in OUTCOMES) + " |")
    lines += ["", "These are raw manifest counts; retries/overlaps are not distinct negative neighborhoods. Controls and smoke directories are excluded."]
    audit = data["sat_audit"]
    if audit.get("audit_valid"):
        a = audit["uniform_summary"]
        lines += [f"Deduplicated audit `{audit['file']}` ({audit.get('recorded_utc')}): {a.get('neighborhoods')} uniform neighborhoods; {a.get('exact_bound_rejected')} exact-bound rejected, {a.get('solver_unsat')} solver UNSAT, {a.get('bound_and_solver_unsat')} overlap, {a.get('negative_union')} negative union; {a.get('unknown_only')} UNKNOWN-only.",
                  "Conditional models are reported separately in the JSON audit. Audit timestamp can lag this live report."]
    else:
        lines += ["Deduplicated model-aware audit is pending or not valid; no derived negative total is asserted."]
    lines += ["", "| Frozen dictionary | Columns | ≤rank | Solver status | Rank 93 control | Forced ones / cardinality constant | Elapsed s |", "|---|---:|---:|---|---|---|---:|"]
    for item in data["dictionaries"]:
        elapsed = item.get("elapsed_seconds")
        prep = item.get("preprocessing", {})
        prep_text = f"{prep.get('forced_ones')} / {prep.get('cardinality_constant')}" if prep else "—"
        lines.append(f"| {item['branch']} | {item['dictionary_size']} | {item['rank_bound']} | {item['status']} | {item.get('control_status')} | {prep_text} | {f'{elapsed:.1f}' if isinstance(elapsed, (int, float)) else '—'} |")
    group = data["heuristics"]["group_equivalent_seeds"]
    if group.get("variants_generated"):
        ids = ", ".join(x.get("id", "unknown") for x in group["selected"])
        lines += ["", f"Basis diversification generated {group['variants_generated']} known-equivalent rank-{group['rank']} transvection variants, independently checking all {group.get('exact_entries_checked_per_variant'):,} coefficients each. Selected {ids} release all {group.get('released_count')} formerly forced choices using {group.get('new_terms')} new triples relative to the {group.get('dictionary_size')}-column dictionary.",
                  "These are known-equivalent term forms used to broaden the search model; no algorithm novelty or inequivalence is claimed."]
    lines += ["", "Dictionary UNSAT concerns subsets of that frozen column set; no independently checked UNSAT trace or global rank bound is claimed. A stopped dictionary-loop query with no saved solver result is not UNSAT; interventions.jsonl records the interruption.",
        "", "## Certificates, checks and limits", "",
        f"Imported public reference portfolio: {data['public_seeds'].get('distinct_term_sets')} distinct rank-93 term sets, independently checked on all 15,625 coefficients each.",
        f"Rank-93 SAT diversification contributed {data['sampled_rank93_portfolio'].get('new_term_sets')} term sets absent from the earlier pool; this is neither a rank improvement nor an inequivalence claim.",
        f"Latest saved full-suite log: {data['tests'].get('passed')} tests passed; saved exit {data['tests'].get('exit_code')}. Rerun after any subsequent code changes.",
        f"Lean published rank-93 baseline: exit {data['lean'].get('exit_code')}; axioms propext, Lean.ofReduceBool and Quot.sound. Native evaluation trust remains; this does not formalize a new record.",
        "Native final-checkpoint draining was corrected; previous saved runs reported best 93. Code versions, hashes and adaptation history remain under frozen/ and RUNNING_HANDOFF.md."]
    lines += ["", *[f"* {x}" for x in data["limitations"]], "", "## Reproduce and resume", "",
        "Run from the repository root; these commands preserve search evidence:", "", "```sh",
        "taskset -c 0 python3 scripts/campaign_report.py --markdown research/campaign/REPORT.md --json research/campaign/report.json",
        "taskset -c 0 python3 -m mmsearch.verify artifacts/km93_f2.json --random-trials 64",
        "taskset -c 0 python3 -c \"import json,shlex; d=json.load(open('artifacts/campaign_20261102T164324Z/oriented-cadical-job.result.json')); print(shlex.join(d['command']))\"",
        "```", "",
        "The last command only inspects completed-job command provenance; it does not execute a search. Completed jobs retain .result.json, while their .running.json records are removed. If that job is still active, wait for its completed record before using this inspection example.",
        "The original deadline is fixed. Future search requires a separately authorized budget and a new campaign folder; these recorded arguments do not authorize another run or extend this campaign.",
        "SAT restart restores experiment cursors and identity, not solver learned clauses. Native restart from a saved best/current state requires a newly recorded seed; exact replay instead requires the original seed and step schedule. Preserve all original evidence and record new provenance.",
        f"Artifacts: `{data['campaign_directory']}`. Per-job commands, budgets, caps, source hashes and compact metadata are retained in the companion JSON; large witness arrays are deliberately omitted."]
    return "\n".join(lines) + "\n"


def print_resume(path, seconds, directory):
    cfg, record = read(directory / "campaign.json"), read(path)
    end = dt.datetime.fromisoformat(cfg["deadline_utc"].replace("Z", "+00:00"))
    remaining = int((end - dt.datetime.now(dt.timezone.utc)).total_seconds()) - 10
    budget = min(seconds, remaining)
    if budget < 1 or cfg.get("state") == "completed":
        raise SystemExit("Campaign completed/deadline reached; no resume command generated.")
    cmd = command(record.get("command"))[:]
    if not cmd or record.get("cpu") not in range(4) or not 64 <= record.get("memory_mb", 0) <= 2048:
        raise SystemExit("Missing or unsupported saved command/caps.")
    if "--seconds" not in cmd:
        raise SystemExit("Saved command has no explicit wall budget.")
    cmd[cmd.index("--seconds") + 1] = str(budget)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%H%M%S")
    if any("campaign_native.py" in x or "dictionary" in x for x in cmd):
        if "--output-dir" in cmd:
            idx = cmd.index("--output-dir") + 1
            cmd[idx] += f"-resume-{stamp}"
    prefix = directory / f"resume-{path.name.split('-job')[0]}-{stamp}-job"
    wrapped = ["python3", "scripts/limited_worker.py", "--cpu", str(record["cpu"]),
        "--memory-mb", str(record["memory_mb"]), "--seconds", str(min(budget + 5, remaining)),
        "--prefix", relative(prefix), "--", *cmd]
    print(shlex.join(wrapped))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=DEFAULT)
    parser.add_argument("--markdown", type=Path, default=ROOT / "research/campaign/REPORT_DRAFT.md")
    parser.add_argument("--json", type=Path, default=ROOT / "research/campaign/report_draft.json")
    parser.add_argument("--sat-audit", type=Path)
    parser.add_argument("--resume-job", type=Path)
    parser.add_argument("--resume-seconds", type=int, default=300)
    args = parser.parse_args()
    if args.resume_job:
        print_resume(args.resume_job, args.resume_seconds, args.campaign.resolve())
        return
    data = collect(args.campaign.resolve(), args.sat_audit)
    for path, text in ((args.markdown, markdown(data)), (args.json, json.dumps(data, indent=2) + "\n")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    print(json.dumps({"interim": data["interim"], "markdown": relative(args.markdown),
                      "json": relative(args.json), "native_steps": data["native"]["steps"],
                      "target_candidates": len(data["verified_target_candidates"])}))


if __name__ == "__main__":
    main()
