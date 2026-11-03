"""Losslessly archive completed known-recovery runs and optionally remove them.

Only explicit known-recovery/runs directories are accepted. Genuine record
claims, active runs, symlinks, stale hashes, and unsafe archive paths fail closed.
Selection stops as soon as the batch is full. Remaining directory entries are
counted without opening their run artifacts; they are not classified as skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import time
import uuid


BASE_SOURCE_SHA256 = 'a50c930208a1b3d9fc83ef6adc34cb43146d0074e59e07a57a34d52177763d4b'


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runs_root(path):
    original = Path(path).absolute()
    if original.is_symlink() or original.parent.is_symlink():
        raise ValueError("symlink recovery directory is not accepted")
    path = original.resolve()
    if path.name != "runs" or path.parent.name != "known-recovery":
        raise ValueError("explicit directory must end in known-recovery/runs")
    return path


def safe_relative(name):
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or any(x in ("", ".", "..") for x in path.parts):
        raise ValueError("unsafe archive member path")
    if str(path) != name:
        raise ValueError("noncanonical archive member path")
    return path


def claims_record(value, record_rank):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("rank", "best_rank", "current_rank", "essential_bilinear_count", "best_essential_rank"):
                if type(item) is int and item <= record_rank:
                    return True
            if key == "terms" and isinstance(item, list) and len(item) <= record_rank:
                return True
            if claims_record(item, record_rank):
                return True
    elif isinstance(value, list):
        return any(claims_record(item, record_rank) for item in value)
    return False


def checked_child(path, run):
    path = Path(path)
    path = (run/path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(run.resolve()) or not path.is_file() or path.is_symlink():
        raise ValueError("native artifact path escapes completed run")
    return path


def completed_run(run, *, minimum_age, record_rank, now=None):
    """Return skip reason or validated frozen-result metadata."""
    now = time.time() if now is None else now
    if run.is_symlink() or not run.is_dir() or run.name.startswith("."):
        return "not_run_directory", None
    result_path, manifest_path = run/"result.json", run/"manifest.json"
    if not result_path.is_file() or not manifest_path.is_file():
        return "active_or_incomplete", None
    files = []
    for path in run.rglob("*"):
        if path.is_symlink():
            return "symlink_artifact", None
        if path.is_file():
            files.append(path)
    if any(now-path.stat().st_mtime < minimum_age for path in files):
        return "too_recent", None
    if result_path.stat().st_mode & 0o222:
        return "result_not_frozen", None
    result, manifest = json.loads(result_path.read_text()), json.loads(manifest_path.read_text())
    if result.get("status") != "ok":
        return "result_not_complete", None
    if Path(result.get("run_dir", "")).resolve() != run.resolve():
        return "result_directory_mismatch", None
    if claims_record(result, record_rank) or claims_record(manifest, record_rank):
        return "genuine_record_claim", None
    if manifest.get("target_rank", record_rank) <= record_rank:
        return "record_search_target", None
    if sha256_file(run/"input.json") != manifest.get("input_sha256"):
        raise ValueError("completed input hash mismatch")
    if not result.get("candidates"):
        return "missing_verified_candidates", None
    for item in result.get("candidates", []):
        candidate = checked_child(item["path"], run)
        report_path = checked_child(item["verification_path"], run)
        if sha256_file(candidate) != item["sha256"]:
            raise ValueError("completed candidate hash mismatch")
        value, report = json.loads(candidate.read_text()), json.loads(report_path.read_text())
        if claims_record(value, record_rank) or claims_record(report, record_rank):
            return "genuine_record_claim", None
        if not report.get("valid") or report.get("rank") != item["rank"]:
            raise ValueError("completed candidate lacks consistent independent report")
    return None, {"run": run.name, "file_count": len(files), "result_sha256": sha256_file(result_path)}


def file_table(root, run_names):
    entries = []
    for name in run_names:
        for path in sorted((root/name).rglob("*")):
            if path.is_symlink():
                raise ValueError("symlink artifact cannot be archived")
            if path.is_file():
                info = path.stat()
                relative = path.relative_to(root).as_posix()
                safe_relative(relative)
                entries.append({"path": relative, "size": info.st_size, "sha256": sha256_file(path),
                                "mode": stat.S_IMODE(info.st_mode), "mtime_ns": info.st_mtime_ns})
    return entries


def verify_bundle(archive, manifest):
    if sha256_file(archive) != manifest["archive_sha256"]:
        raise ValueError("archive checksum mismatch")
    expected = {}
    for item in manifest["files"]:
        safe_relative(item["path"])
        if item["path"] in expected:
            raise ValueError("duplicate manifest path")
        expected[item["path"]] = item
    seen = set()
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            safe_relative(member.name)
            if not member.isfile() or member.name in seen or member.name not in expected:
                raise ValueError("unexpected, duplicate, or nonregular archive member")
            item = expected[member.name]
            if member.size != item["size"]:
                raise ValueError("archive member size mismatch")
            digest = hashlib.sha256()
            with stream.extractfile(member) as content:
                for chunk in iter(lambda: content.read(1024*1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != item["sha256"]:
                raise ValueError("archive member checksum mismatch")
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("archive has missing members")
    return True


def archive_runs(directory, output_dir, *, minimum_age=30, max_runs=1000,
                 remove_after_verify=False, record_rank=92):
    root, output = runs_root(directory), Path(output_dir).resolve()
    if not root.is_dir() or output.is_relative_to(root):
        raise ValueError("runs must exist and archives must be outside the run tree")
    if minimum_age < 0 or not 1 <= max_runs <= 1000:
        raise ValueError("invalid minimum age or batch bound")
    selected, skipped = [], {}
    run_entries = sorted(root.iterdir())
    scanned_entries = 0
    for run in run_entries:
        scanned_entries += 1
        reason, metadata = completed_run(run, minimum_age=minimum_age, record_rank=record_rank)
        if reason:
            skipped[reason] = skipped.get(reason, 0)+1
        else:
            selected.append(metadata)
            if len(selected) == max_runs:
                break
    selection = {"selection_truncated": scanned_entries < len(run_entries),
                 "scanned_entries": scanned_entries,
                 "unscanned_entries": len(run_entries)-scanned_entries,
                 "directory_entries": len(run_entries)}
    if not selected:
        return {"runs": 0, "skipped": skipped, "removed_runs": 0, **selection}
    output.mkdir(parents=True, exist_ok=True)
    basename = "known-recovery-"+time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())+"-"+uuid.uuid4().hex
    archive = output/(basename+".tar.gz")
    temporary = output/(basename+".tar.gz.tmp")
    table = file_table(root, [x["run"] for x in selected])
    try:
        with tarfile.open(temporary, "w:gz", compresslevel=1) as stream:
            for item in table:
                stream.add(root/item["path"], arcname=item["path"], recursive=False)
        manifest = {"format": "lossless-known-recovery-archive-v1", "runs_directory": str(root),
                    "archive": archive.name, "archive_sha256": sha256_file(temporary),
                    "runs": selected, "files": table, "record_rank_excluded": record_rank,
                    "remove_requested": remove_after_verify,
                    "utility_source_sha256": sha256_file(Path(__file__)),
                    "base_source_sha256": BASE_SOURCE_SHA256,
                    "selection": selection, "skipped": skipped}
        verify_bundle(temporary, manifest)
        temporary.replace(archive)
        manifest_path = output/(basename+".manifest.json")
        manifest_tmp = output/(basename+".manifest.json.tmp")
        manifest_tmp.write_text(json.dumps(manifest, sort_keys=True)+"\n")
        manifest_tmp.replace(manifest_path)
        archive.chmod(0o444)
        manifest_path.chmod(0o444)
        removed = 0
        if remove_after_verify:
            # Verify the persisted immutable pair before touching original files.
            persisted = json.loads(manifest_path.read_text())
            verify_bundle(archive, persisted)
            for entry in selected:
                run = root/entry["run"]
                reason, _ = completed_run(run, minimum_age=minimum_age, record_rank=record_rank)
                current = file_table(root, [entry["run"]])
                original = [item for item in table if PurePosixPath(item["path"]).parts[0] == entry["run"]]
                if reason or current != original:
                    raise ValueError("completed run changed after archive verification; originals retained")
                quarantine = root/(".archived-"+entry["run"]+"-"+uuid.uuid4().hex)
                run.rename(quarantine)
                # The final rename isolates this completed tree from discovery;
                # byte/table validation above precedes the reversible removal.
                shutil.rmtree(quarantine)
                removed += 1
        return {"runs": len(selected), "files": len(table), "raw_bytes": sum(x["size"] for x in table),
                "archive_bytes": archive.stat().st_size, "archive": str(archive),
                "manifest": str(manifest_path), "archive_sha256": manifest["archive_sha256"],
                "removed_runs": removed, "skipped": skipped, **selection}
    finally:
        temporary.unlink(missing_ok=True)


def restore_runs(archive, manifest_path, destination):
    archive, manifest_path = Path(archive), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != "lossless-known-recovery-archive-v1":
        raise ValueError("unsupported recovery archive")
    verify_bundle(archive, manifest)
    destination = runs_root(destination)
    # Preflight all existing paths before creating or modifying any member.
    for item in manifest["files"]:
        path = destination/item["path"]
        for ancestor in (path, *path.parents):
            if ancestor == destination.parent:
                break
            if ancestor.is_symlink():
                raise ValueError("restore destination contains symlink")
            if ancestor != path and ancestor.exists() and not ancestor.is_dir():
                raise ValueError("restore parent is not a directory")
        if path.exists() and (not path.is_file() or path.stat().st_size != item["size"] or sha256_file(path) != item["sha256"]):
            raise ValueError("existing restore file differs; no overwrite allowed")
    table = {item["path"]: item for item in manifest["files"]}
    written = identical = 0
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            path = destination/member.name
            if path.exists():
                identical += 1
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(member) as content, path.open("xb") as target:
                shutil.copyfileobj(content, target, length=1024*1024)
            item = table[member.name]
            if sha256_file(path) != item["sha256"]:
                raise ValueError("restored file checksum mismatch")
            path.chmod(item["mode"] & 0o777)
            os.utime(path, ns=(item["mtime_ns"], item["mtime_ns"]))
            written += 1
    return {"restored_files": written, "existing_identical_files": identical,
            "destination": str(destination)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("archive")
    pack.add_argument("--runs-dir", type=Path, required=True)
    pack.add_argument("--output-dir", type=Path, required=True)
    pack.add_argument("--minimum-age", type=float, default=30)
    pack.add_argument("--max-runs", type=int, default=1000)
    pack.add_argument("--record-rank", type=int, default=92)
    pack.add_argument("--remove-after-verify", action="store_true")
    unpack = sub.add_parser("restore")
    unpack.add_argument("--archive", type=Path, required=True)
    unpack.add_argument("--manifest", type=Path, required=True)
    unpack.add_argument("--destination", type=Path, required=True)
    args = p.parse_args(argv)
    if args.command == "archive":
        value = archive_runs(args.runs_dir, args.output_dir, minimum_age=args.minimum_age,
                             max_runs=args.max_runs, remove_after_verify=args.remove_after_verify,
                             record_rank=args.record_rank)
    else:
        value = restore_runs(args.archive, args.manifest, args.destination)
    print(json.dumps(value, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
