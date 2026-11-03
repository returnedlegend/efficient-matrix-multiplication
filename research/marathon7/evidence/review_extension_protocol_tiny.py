"""Independent protocol checks using only an exact n2 base and mocked ancestry.

No production preparation/source files are opened. Auth is deliberately replaced
only to exercise CLI lifecycle on the known eight-product n2 schoolbook tensor.
"""
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from mmsearch.tensor import naive_candidate
from mmsearch.tensor_code7 import prepare
from mmsearch.tensor_code7_extension import WITNESS_SCHEMA, plus_atoms

spec = importlib.util.spec_from_file_location("extension_protocol_review", REPO / "scripts/tensor_code7_extension.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    observations = []
    for mode in ["expired_dispatch", "late_after_build", "late_after_publication"]:
        with tempfile.TemporaryDirectory(prefix="extension-protocol-review-") as directory:
            root = Path(directory)
            campaign = root / "synthetic-campaign"
            campaign.mkdir()
            config = json.dumps(dict(deadline_utc="2026-11-03T19:24:17Z")).encode()
            (campaign / "campaign.json").write_bytes(config)
            config_sha = hashlib.sha256(config).hexdigest()
            tail = Path("/proc", str(os.getpid()), "stat").read_text().rsplit(")", 1)[1].split()
            guard_state = campaign / "resource.json"
            guard_state.write_text(json.dumps(dict(updated_utc=datetime.now(timezone.utc).isoformat(),
                pid=os.getpid(), process_identity=dict(start_ticks=int(tail[19])), campaign_allocated_bytes=1024)))
            base = prepare([naive_candidate(2)])
            base["lifecycle_config"] = dict(campaign_sha256=config_sha,
                campaign_dir=str(campaign.resolve()), guard_state=str(guard_state.resolve()),
                deadline_utc="2026-11-03T19:24:17+00:00")
            base_root = root / "synthetic-base"
            base_root.mkdir()
            base_path = base_root / "prepared.json"
            base_raw = json.dumps(base).encode()
            base_path.write_bytes(base_raw)
            base_sha = hashlib.sha256(base_raw).hexdigest()
            proposed = plus_atoms(tuple(base["atoms"][0]), tuple(base["atoms"][7]), [0, 1, 2], 2)
            manifest = dict(schema=WITNESS_SCHEMA, base_prepared_sha256=base_sha,
                base_dictionary_sha256=base["dictionary_sha256"], max_new_atoms=100,
                relations=[dict(id="synthetic-odd-cycle", parent_atom_ids=[0, 7],
                                axis_permutation=[0, 1, 2], new_atoms=[list(t) for t in proposed])])
            witness_path = root / "synthetic-witness.json"
            witness_raw = json.dumps(manifest).encode()
            witness_path.write_bytes(witness_raw)
            output = root / "result"
            approved = root / "synthetic-approved"
            approved.mkdir()
            args = ["--authorize-extension-preparation", "--qa-approval", "root-reviewed",
                "--base-prepared", str(base_path), "--base-sha256", base_sha,
                "--witnesses", str(witness_path), "--witnesses-sha256", hashlib.sha256(witness_raw).hexdigest(),
                "--source-manifest", str(approved / "MISSING_NO_SOURCE_IO"), "--source-manifest-sha256", "a" * 64,
                "--approved-root", str(approved), "--campaign-dir", str(campaign),
                "--campaign-sha256", config_sha, "--guard-state", str(guard_state),
                "--outdir", str(output), "--seconds", "120"]
            actual_guard = runner.Guard
            actual_build = runner.build_extension
            flags = dict(built=False)
            class Guard:
                def __init__(self, *a, **kw):
                    self.actual = actual_guard(*a, **kw)
                    self.hard = self.actual.hard
                def __call__(self, barrier="loop"):
                    if mode == "expired_dispatch" and barrier == "pre_dispatch":
                        raise runner.Stop("synthetic_expired_dispatch")
                    if mode == "late_after_build" and flags["built"]:
                        raise runner.Stop("synthetic_late_after_build")
                    if mode == "late_after_publication" and barrier == "post_prepared_publication":
                        raise runner.Stop("synthetic_late_publication")
                    self.actual(barrier)
            def build(*a, **kw):
                document = actual_build(*a, **kw)
                flags["built"] = True
                return document
            with ExitStack() as stack:
                stack.enter_context(patch.object(runner, "Guard", Guard))
                authentication = stack.enter_context(patch.object(runner, "authenticate_base", return_value=(base, None)))
                stack.enter_context(patch.object(runner, "build_extension", build))
                stack.enter_context(patch.object(runner.os, "sched_setaffinity"))
                stack.enter_context(patch.object(runner.resource, "setrlimit"))
                stdout = stack.enter_context(redirect_stdout(io.StringIO()))
                code = runner.main(args)
            result = json.loads(stdout.getvalue())
            assert code == 0 and result["status"] == "UNKNOWN" and result["complete"] is False, result
            assert not result["search_called"] and not result["sat_called"]
            assert not (output / "prepared.json").exists()
            if mode == "expired_dispatch":
                authentication.assert_not_called()
                assert not output.exists()
            if mode == "late_after_publication":
                raw = json.loads((output / "after-cutoff-raw-prepared.json").read_bytes())
                from scripts.campaign_operations_v3 import canonical_candidate
                try:
                    canonical_candidate(raw)
                except ValueError:
                    pass
                else:
                    raise AssertionError("late prepared data was ingested as a candidate")
            observations.append(dict(mode=mode, status=result["status"], complete=False,
                                     prepared_publication_absent=True, search_called=False, sat_called=False))
    result = dict(status="PASS_INDEPENDENT_TINY_CLI_LIFECYCLE", controls=observations,
                  fixture="exact known n2 schoolbook8 and one certified5cycle; ancestry mocked",
                  production_source_files_opened=False, n5_generation_called=False,
                  prototype_sha256=hashlib.sha256((REPO / "scripts/tensor_code7_extension.py").read_bytes()).hexdigest())
    path = REPO / "research/marathon7/evidence/tensor-code-extension-independent-protocol-v2.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
