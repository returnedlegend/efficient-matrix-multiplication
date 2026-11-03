"""Bounded native macro actions for an external learning controller.

The bridge does not choose or learn a policy. Each call starts one native walk,
then drains and independently verifies its final best, current, and archive.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

from .search import decode_candidate, encode_candidate, is_cyclic
from .verify import verify_candidate

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ActionProfile:
    plus_every: int
    restart_every: int
    rank_headroom: int
    cyclic: bool = False
    description: str = ""


ACTION_PROFILES = {
    "exploit": ActionProfile(2000, 50000, 2, description="Few plus moves and a narrow rank cap"),
    "explore": ActionProfile(100, 200000, 8, description="More plus moves and rank headroom"),
    "long_walk": ActionProfile(500, 10000000, 5, description="Long excursions between archive restarts"),
    "cyclic": ActionProfile(250, 200000, 6, True, "C3 orbit moves; requires a cyclic seed"),
}


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _freeze(path, data, executable=False):
    """Exclusive content write; existing immutable objects must match exactly."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise RuntimeError(f"immutable artifact collision: {path}")
    path.chmod(0o555 if executable else 0o444)
    return path


def canonical_terms(candidate):
    """Strict F2 input, with zero terms removed and duplicate terms cancelled."""
    if not isinstance(candidate, dict) or type(candidate.get("dimension")) is not int:
        raise ValueError("candidate must declare an integer dimension")
    n = candidate["dimension"]
    if not 2 <= n <= 5 or type(candidate.get("field")) is not int or candidate["field"] != 2:
        raise ValueError("native bridge requires dimension 2..5 over F2")
    terms = set()
    for triple in decode_candidate(candidate, n):
        if not all(triple):
            continue
        if triple in terms:
            terms.remove(triple)
        else:
            terms.add(triple)
    return tuple(sorted(terms))


def term_set_sha256(terms):
    return _sha("".join(f"{a} {b} {c}\n" for a, b, c in sorted(terms)).encode())


def xor_addition_estimate(terms, n):
    """Unshared input linear forms plus output accumulation additions over F2."""
    terms = tuple(terms)
    inputs = sum(max(0, a.bit_count()-1)+max(0, b.bit_count()-1) for a,b,_ in terms)
    outputs = sum(max(0, sum((c >> i) & 1 for _,_,c in terms)-1) for i in range(n*n))
    return inputs+outputs


def _read_terms(path, n):
    result = []
    for line in Path(path).read_text().splitlines():
        fields = line.split()
        if len(fields) != 3 or any(not field.isdecimal() for field in fields):
            raise ValueError(f"malformed native terms: {path}")
        triple = tuple(map(int, fields))
        if any(not 0 < x < 1 << (n*n) for x in triple):
            raise ValueError(f"native factor outside nonzero bit width: {path}")
        result.append(triple)
    if not result or len(set(result)) != len(result):
        raise ValueError(f"empty or noncanonical native terms: {path}")
    return tuple(sorted(result))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate native metadata key: {key}")
        result[key] = value
    return result


def _wait_with_usage(process, timeout):
    """Reap this exact child with wait4, retaining actual user+system CPU time."""
    deadline = time.monotonic()+timeout
    terminated = killed = False
    while True:
        pid, status, usage = os.wait4(process.pid, os.WNOHANG)
        if pid:
            process.returncode = os.waitstatus_to_exitcode(status)
            return usage.ru_utime+usage.ru_stime, terminated
        now = time.monotonic()
        if now >= deadline:
            if not terminated:
                process.terminate()
                terminated = True
                deadline = now+0.5
            elif not killed:
                process.kill()
                killed = True
        time.sleep(0.005)


class NativeBridge:
    """One short process per macro action; no subprocess for individual moves.

    ``deadline`` is an optional absolute time.monotonic() deadline. Instances
    retain novelty sets across actions. Use separate instances for concurrent
    actors; on-disk run identifiers are collision resistant.
    """
    def __init__(self, output_dir, binary=None, source=None, cpu_affinity=None,
                 deadline=None, max_seconds=5.0, archive_size=64, archive_every=1000):
        if not math.isfinite(max_seconds) or not 0 < max_seconds <= 5:
            raise ValueError("max_seconds must be in (0, 5]")
        if type(archive_size) is not int or not 1 <= archive_size <= 256:
            raise ValueError("archive_size must be an integer in 1..256")
        if type(archive_every) is not int or archive_every < 1:
            raise ValueError("archive_every must be positive")
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_seconds, self.archive_size, self.archive_every = max_seconds, archive_size, archive_every
        self.deadline, self.cpu_affinity = deadline, cpu_affinity
        self.seen_candidates, self.seen_terms = set(), set()
        self.source = Path(source or ROOT/"native/flip_worker_v2.cpp").resolve()
        original = Path(binary or ROOT/"native/flip_worker_cyclic").resolve()
        if not original.exists():
            # Build only the preserved source, into a unique bridge-owned path.
            compiler = shutil.which(os.environ.get("CXX", "g++"))
            if not compiler:
                raise RuntimeError("native binary absent and C++ compiler unavailable")
            original = self.output_dir/("build-"+uuid.uuid4().hex)
            subprocess.run([compiler, "-std=c++17", "-O3", "-DNDEBUG", str(self.source), "-o", str(original)],
                           check=True, capture_output=True, timeout=60)
        binary_data, source_data = original.read_bytes(), self.source.read_bytes()
        self.binary_sha256, self.source_sha256 = _sha(binary_data), _sha(source_data)
        self.binary = _freeze(self.output_dir/"frozen"/(self.binary_sha256+".worker"), binary_data, True)
        _freeze(self.output_dir/"frozen"/(self.source_sha256+".cpp"), source_data)
        self.code_hashes = {path.name: _sha(path.read_bytes()) for path in
                            (Path(__file__), Path(__file__).with_name("verify.py"))}

    def run(self, candidate, action="exploit", *, seconds=2.0, seed=0,
            target_rank=92, step_limit=10**12):
        action_started = time.monotonic()
        if action not in ACTION_PROFILES:
            raise ValueError(f"unknown native action: {action}")
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= self.max_seconds:
            raise ValueError("seconds exceeds the bounded macro-action limit")
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError("seed must be an unsigned 64-bit integer")
        if type(step_limit) is not int or not 0 <= step_limit < 2**64:
            raise ValueError("step_limit must be an unsigned 64-bit integer")
        if type(target_rank) is not int or not 0 <= target_rank <= 1000:
            raise ValueError("target_rank must be in 0..1000")
        profile = ACTION_PROFILES[action]
        terms = canonical_terms(candidate)
        n = candidate["dimension"]
        normalized = encode_candidate(terms, n)
        input_report = verify_candidate(normalized, random_trials=0)
        if not input_report["valid"]:
            raise ValueError("native macro action requires an independently exact input")
        if profile.cyclic and not is_cyclic(terms):
            return dict(status="skipped", reason="cyclic action requires complete C3 orbits", action=action)
        if self.deadline is not None:
            seconds = min(seconds, self.deadline-time.monotonic()-0.1)
            if seconds <= 0:
                return dict(status="skipped", reason="global deadline exhausted", action=action)
        maximum_rank = len(terms)+profile.rank_headroom
        if maximum_rank > 1000:
            raise ValueError("initial rank plus headroom exceeds native rank limit")
        run_dir = self.output_dir/"runs"/(time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())+"-"+uuid.uuid4().hex)
        run_dir.mkdir(parents=True, exist_ok=False)
        source = _freeze(run_dir/"input.json", _json_bytes(candidate))
        masks = _freeze(run_dir/"input.txt", "".join(f"{a} {b} {c}\n" for a,b,c in terms).encode())
        prefix = run_dir/"walk"
        command = [str(self.binary), "--input", str(masks), "--output", str(prefix),
                   "--n", str(n), "--target", str(target_rank), "--max-rank", str(maximum_rank),
                   "--steps", str(step_limit), "--seconds", repr(float(seconds)), "--seed", str(seed),
                   "--checkpoint-seconds", str(max(0.01, seconds+1)), "--archive-size", str(self.archive_size),
                   "--archive-every", str(self.archive_every), "--plus-every", str(profile.plus_every),
                   "--restart-every", str(profile.restart_every)]
        if profile.cyclic:
            command.append("--cyclic")
        if self.cpu_affinity is not None:
            cpus = str(self.cpu_affinity) if isinstance(self.cpu_affinity, (str,int)) else ",".join(map(str,self.cpu_affinity))
            command = ["taskset", "-c", cpus, *command]
        meta = dict(action=action, action_parameters=asdict(profile), seed=seed, dimension=n,
                    input_sha256=_sha(source.read_bytes()), input_term_set_sha256=term_set_sha256(terms),
                    binary_sha256=self.binary_sha256, source_sha256=self.source_sha256,
                    code_sha256=self.code_hashes, command=command, seconds_budget=seconds,
                    step_budget=step_limit, target_rank=target_rank, max_rank=maximum_rank)
        _freeze(run_dir/"manifest.json", _json_bytes(meta))
        started = time.monotonic()
        with (run_dir/"worker.log").open("xb") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                cpu_seconds, timed_out = _wait_with_usage(process, seconds+1.0)
            except BaseException:
                process.terminate()
                _wait_with_usage(process, 0.5)
                raise
        wall_seconds = time.monotonic()-started
        if process.returncode != 0:
            raise RuntimeError(f"native macro action failed ({process.returncode}); inspect {run_dir}")
        # Always drain after wait: a target can be found before the first poll.
        stats = json.loads(prefix.with_suffix(".stats.json").read_text(), object_pairs_hook=_unique_object)
        self._validate_stats(stats, meta)
        paths = [prefix.with_suffix(".best.txt"), prefix.with_suffix(".current.txt")]
        archives = sorted(prefix.with_suffix(".archive").glob("*.txt"))
        if len(archives) < stats["archive_size"]:
            raise ValueError("native final archive is incomplete")
        verified, records = {}, []
        before_candidates, before_terms = set(self.seen_candidates), set(self.seen_terms)
        best_candidate = current_candidate = None
        for path in [*paths, *archives]:
            triples = _read_terms(path, n)
            if len(triples) > maximum_rank:
                raise ValueError("native final candidate exceeds rank cap")
            if path == paths[0] and len(triples) != stats["best_rank"]:
                raise ValueError("native best rank disagrees with final metadata")
            if path == paths[1] and len(triples) != stats["current_rank"]:
                raise ValueError("native current rank disagrees with final metadata")
            h = term_set_sha256(triples)
            if h not in verified:
                value = encode_candidate(triples, n, method="native-macro-action", parent=meta,
                                         term_set_sha256=h, essential_bilinear_count=len(triples))
                report = verify_candidate(value, random_trials=0)
                if not report["valid"] or (profile.cyclic and not is_cyclic(triples)):
                    raise RuntimeError(f"independent native final verification failed: {path}")
                payload = _json_bytes(value)
                frozen = _freeze(run_dir/"verified"/(h+".json"), payload)
                verification = _freeze(run_dir/"verified"/(h+".verification.json"), _json_bytes(report))
                _freeze(run_dir/"verified"/(h+".sha256"), (_sha(payload)+"  "+frozen.name+"\n").encode())
                record = dict(path=str(frozen), sha256=_sha(payload), verification_path=str(verification),
                              term_set_sha256=h, rank=len(triples), essential_bilinear_count=len(triples),
                              xor_addition_estimate=xor_addition_estimate(triples,n),
                              novel=h not in before_candidates)
                verified[h] = (value, triples, record)
                records.append(record)
                # Winner is frozen by checksum before it can reach the controller.
                if len(triples) <= target_rank:
                    _freeze(run_dir/"winners"/(h+".json"), payload)
                    _freeze(run_dir/"winners"/(h+".verification.json"), _json_bytes(report))
            if path == paths[0]:
                best_candidate = verified[h][0]
            if path == paths[1]:
                current_candidate = verified[h][0]
        current_terms = set(canonical_terms(current_candidate))
        all_terms = set().union(*(set(item[1]) for item in verified.values()))
        hashes = set(verified)
        result = dict(status="ok", action=action, action_parameters=asdict(profile), run_dir=str(run_dir),
                      best_candidate=best_candidate, current_candidate=current_candidate,
                      best_rank=stats["best_rank"], best_essential_rank=stats["best_rank"],
                      current_rank=stats["current_rank"], attempted_moves=stats["steps"],
                      cpu_seconds=cpu_seconds, wall_seconds=wall_seconds, timed_out=timed_out,
                      stats=stats, candidates=records,
                      best_xor_addition_estimate=xor_addition_estimate(canonical_terms(best_candidate),n),
                      novelty=dict(new_candidates=len(hashes-before_candidates), new_terms=len(all_terms-before_terms),
                                   current_term_jaccard_distance=1-len(current_terms & set(terms))/len(current_terms | set(terms))))
        result["total_wall_seconds"] = time.monotonic()-action_started
        _freeze(run_dir/"result.json", _json_bytes(result))
        self.seen_candidates.update(hashes)
        self.seen_terms.update(all_terms)
        return result

    @staticmethod
    def _validate_stats(stats, meta):
        if not isinstance(stats, dict):
            raise ValueError("native final metadata must be an object")
        expected = dict(dimension=meta["dimension"], seed=meta["seed"], step_budget=meta["step_budget"],
                        target_rank=meta["target_rank"], max_rank=meta["max_rank"],
                        plus_every=meta["action_parameters"]["plus_every"],
                        restart_every=meta["action_parameters"]["restart_every"])
        for key, value in expected.items():
            if type(stats.get(key)) is not int or stats[key] != value:
                raise ValueError(f"native final metadata mismatch: {key}")
        for key in ("steps", "best_rank", "current_rank", "accepted_moves", "rejected_moves", "archive_size"):
            if type(stats.get(key)) is not int or stats[key] < 0:
                raise ValueError(f"invalid native final counter: {key}")
        if stats.get("exact") is not True or stats.get("tensor_invariant_checked") is not True:
            raise ValueError("native final metadata does not report exact invariant checks")
        if type(stats.get("cyclic")) is not bool or stats["cyclic"] != meta["action_parameters"]["cyclic"]:
            raise ValueError("native final cyclic metadata mismatch")
        if (stats["steps"] > meta["step_budget"] or stats["best_rank"] > stats["current_rank"]
                or stats["current_rank"] > meta["max_rank"] or stats["archive_size"] < 1
                or stats["accepted_moves"]+stats["rejected_moves"] != stats["steps"]):
            raise ValueError("inconsistent native final counters")
        if type(stats.get("target_reached")) is not bool or stats["target_reached"] != (stats["best_rank"] <= meta["target_rank"]):
            raise ValueError("native final target status mismatch")
        elapsed = stats.get("elapsed_seconds")
        if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("invalid native elapsed time")
        seconds = stats.get("seconds_budget")
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not math.isclose(seconds,meta["seconds_budget"],rel_tol=1e-5,abs_tol=1e-6):
            raise ValueError("native final seconds budget mismatch")
