"""Lossless all-native archive V4 with fresh exact audit of every candidate.

Explicit native/runs, native/record/runs and native/known-recovery/runs only.
Records, WINNER/FOUND files, active/incomplete trees and invalid candidates
remain untouched. Every persisted bundle is bytewise checked before removal.
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
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.campaign_operations_v3 import canonical_candidate
from scripts.rl_campaign_queue import load_json, unique_object
from mmsearch.native_bridge import _read_terms
from mmsearch.verify import verify_candidate
from scripts.verify_record42_independent import verify_bytes


BASE_SOURCE_SHA256 = 'a50c930208a1b3d9fc83ef6adc34cb43146d0074e59e07a57a34d52177763d4b'


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runs_root(path, *, allowed_campaigns=()):
    """Legacy roots unchanged; nested evaluation arms require explicit authority."""
    original = Path(path).absolute()
    if any(p.is_symlink() for p in (original,*original.parents)):
        raise ValueError("symlink native directory is not accepted")
    path = original.resolve()
    legacy = (path.name == 'runs' and
              (path.parent.name == 'native' or
               (path.parent.name in ('known-recovery','record') and path.parent.parent.name == 'native')))
    if legacy:
        return path
    nested = (path.name == 'runs' and path.parent.name in ('known-recovery','record')
              and path.parent.parent.name in ('learned','frozenwarm','random')
              and path.parent.parent.parent.name == 'native')
    authorized = any(path.is_relative_to(Path(root).resolve()) for root in allowed_campaigns)
    if not nested or not authorized:
        raise ValueError('nested native evaluation runs require approved arm/kind and explicit authorized campaign')
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


class RecordFound(ValueError):
    def __init__(self,message,candidate,report):
        super().__init__(message); self.candidate=candidate; self.report=report


def audit_candidates(value, source, cache, audits):
    if isinstance(value, dict):
        if 'terms' in value:
            canonical=canonical_candidate(value)
            raw=(json.dumps(canonical,sort_keys=True,separators=(',',':'))+'\n').encode()
            digest=hashlib.sha256(raw).hexdigest()
            if digest not in cache:
                report=verify_candidate(canonical,random_trials=0)
                if report.get('valid') is not True or report.get('exact_entries_checked')!=15625:
                    raise ValueError('fresh exhaustive candidate audit failed: '+str(source))
                cache[digest]=dict(rank=len(canonical['terms']),valid=True,exact_entries_checked=15625,
                                   canonical_certificate=canonical)
            rank=cache[digest]['rank']
            audits.append(dict(source=str(source),canonical_sha256=digest,rank=rank,exact_entries_checked=15625))
            if rank<=92:
                second=verify_bytes(raw)
                if second.get('record_eligible') is not True:
                    raise ValueError('record failed second independent verifier: '+str(source))
                raise RecordFound('actual exact n5F2 canonical product count<=92: '+str(source),canonical,second)
            return
        for key,item in value.items(): audit_candidates(item,str(source)+'#'+key,cache,audits)
    elif isinstance(value,list):
        for i,item in enumerate(value): audit_candidates(item,str(source)+'#'+str(i),cache,audits)


def file_identities(files,run):
    rows=[]
    for path in sorted(files):
        info=path.stat()
        rows.append((str(path.relative_to(run)),info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_ino))
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()


def completed_run(run, *, minimum_age, record_rank, now=None):
    now=time.time() if now is None else now
    if run.is_symlink() or not run.is_dir() or run.name.startswith('.'):
        return 'not_run_directory',None
    result_path,manifest_path=run/'result.json',run/'manifest.json'
    if not result_path.is_file() or not manifest_path.is_file():
        return 'active_or_incomplete',None
    files=[]
    for path in run.rglob('*'):
        if path.is_symlink(): return 'symlink_artifact',None
        if path.is_file(): files.append(path)
    if any(now-p.stat().st_mtime<minimum_age for p in files): return 'too_recent',None
    identities=file_identities(files,run)
    if result_path.stat().st_mode&0o222: return 'result_not_frozen',None
    if any(p.name in ('WINNER.json','FOUND.json') for p in files): return 'explicit_record_marker',None
    result,_=load_json(result_path);manifest,_=load_json(manifest_path)
    if result.get('status')!='ok': return 'result_not_complete',None
    if Path(result.get('run_dir','')).resolve()!=run.resolve(): return 'result_directory_mismatch',None
    if sha256_file(run/'input.json')!=manifest.get('input_sha256'):
        raise ValueError('completed input hash mismatch')
    if not result.get('candidates'): return 'missing_verified_candidates',None
    for item in result['candidates']:
        candidate=checked_child(item['path'],run); report_path=checked_child(item['verification_path'],run)
        if sha256_file(candidate)!=item['sha256']: raise ValueError('completed candidate hash mismatch')
        report,_=load_json(report_path)
        if report.get('valid') is not True or report.get('rank')!=item['rank']:
            raise ValueError('completed candidate lacks consistent historical report')
    cache={};audits=[]
    try:
        # Every JSON certificate, including embedded result best/current, and
        # every native mask snapshot is audited, even if omitted from result.
        for path in sorted(files):
            first=len(audits)
            if path.suffix=='.json':
                raw=path.read_bytes();value=json.loads(raw,object_pairs_hook=unique_object)
                audit_candidates(value,path.relative_to(run),cache,audits)
            elif path.suffix=='.txt':
                triples=_read_terms(path,5)
                audit_candidates(dict(dimension=5,field=2,terms=[list(t) for t in triples]),path.relative_to(run),cache,audits)
            for item in audits[first:]: item['source_file_sha256']=sha256_file(path)
    except RecordFound as exc:
        return 'genuine_exact_record_preserved',dict(reason=str(exc),candidate=exc.candidate,independent_verification=exc.report)
    if not audits: raise ValueError('no freshly verified native candidates')
    if file_identities(files,run)!=identities:
        raise ValueError('completed run changed during fresh candidate audit')
    best_rank=min(v['rank'] for v in cache.values())
    best=min((v for v in cache.values() if v['rank']==best_rank),key=lambda v:json.dumps(v['canonical_certificate'],sort_keys=True))
    return None,dict(run=run.name,file_count=len(files),result_sha256=sha256_file(result_path),
        manifest_sha256=sha256_file(manifest_path),files_identity_sha256=identities,raw_bytes=sum(p.stat().st_size for p in files),
        candidate_audits=audits,distinct_candidates=len(cache),best_rank=best_rank,
        preserved_manifest=manifest,best_certificate=best['canonical_certificate'])


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
                 remove_after_verify=False, record_rank=92, max_raw_bytes=512*1024**2, allowed_campaigns=()):
    root, output = runs_root(directory, allowed_campaigns=allowed_campaigns), Path(output_dir).resolve()
    if not root.is_dir() or output.is_relative_to(root):
        raise ValueError("runs must exist and archives must be outside the run tree")
    if minimum_age < 0 or not 1 <= max_runs <= 1000 or max_raw_bytes < 1:
        raise ValueError("invalid minimum age or batch bound")
    selected, skipped = [], {}
    selected_bytes = 0
    run_entries = sorted(root.iterdir())
    scanned_entries = 0
    for run in run_entries:
        scanned_entries += 1
        reason, metadata = completed_run(run, minimum_age=minimum_age, record_rank=record_rank)
        if reason:
            if reason=='genuine_exact_record_preserved':
                return dict(status='record_preserved',runs=0,removed_runs=0,record=metadata,source_run=str(run),skipped=skipped)
            skipped[reason] = skipped.get(reason, 0)+1
        else:
            if selected_bytes+metadata["raw_bytes"] > max_raw_bytes:
                if selected:
                    break
                skipped["oversized_completed_run"] = skipped.get("oversized_completed_run",0)+1
                continue
            selected_bytes += metadata["raw_bytes"]
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
    basename = "native-runs-"+time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())+"-"+uuid.uuid4().hex
    archive = output/(basename+".tar.gz")
    temporary = output/(basename+".tar.gz.tmp")
    table = file_table(root, [x["run"] for x in selected])
    try:
        with tarfile.open(temporary, "w:gz", compresslevel=1) as stream:
            for item in table:
                stream.add(root/item["path"], arcname=item["path"], recursive=False)
        manifest = {"format": "lossless-native-runs-archive-v4", "runs_directory": str(root),
                    "archive": archive.name, "archive_sha256": sha256_file(temporary),
                    "runs": selected, "files": table, "record_rank_excluded": record_rank,
                    "remove_requested": remove_after_verify,
                    "utility_source_sha256": sha256_file(Path(__file__)),
                    "base_source_sha256": BASE_SOURCE_SHA256,
                    "archive_v2_source_sha256": sha256_file(REPO/"scripts/archive_recovery_runs_v2.py"),
                    "fresh_candidate_audit": "every JSON certificate and native mask snapshot exact15625 F2 coefficients",
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


def restore_runs(archive, manifest_path, destination, *, allowed_campaigns=()):
    archive, manifest_path = Path(archive), Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != "lossless-native-runs-archive-v4":
        raise ValueError("unsupported recovery archive")
    verify_bundle(archive, manifest)
    destination = runs_root(destination, allowed_campaigns=allowed_campaigns)
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
    pack.add_argument("--max-raw-bytes", type=int, default=512*1024**2)
    pack.add_argument("--remove-after-verify", action="store_true")
    unpack = sub.add_parser("restore")
    unpack.add_argument("--archive", type=Path, required=True)
    unpack.add_argument("--manifest", type=Path, required=True)
    unpack.add_argument("--destination", type=Path, required=True)
    args = p.parse_args(argv)
    if args.command == "archive":
        value = archive_runs(args.runs_dir, args.output_dir, minimum_age=args.minimum_age,
                             max_runs=args.max_runs, remove_after_verify=args.remove_after_verify,
                             record_rank=args.record_rank, max_raw_bytes=args.max_raw_bytes)
    else:
        value = restore_runs(args.archive, args.manifest, args.destination)
    print(json.dumps(value, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
