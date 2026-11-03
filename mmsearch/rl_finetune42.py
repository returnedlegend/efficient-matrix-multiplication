"""V42 continuation: phase-local auxiliary allocation, frozen-source curriculum.

The inherited exact transition, actor-critic loss, Adam, action vocabulary and
F2 verifier stay unchanged. A new immutable checkpoint format binds the phase
clock and curriculum identity to the continued optimizer and random streams.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import uuid

from mmsearch.rl_restart_curriculum import RestartRecordController
from mmsearch.rl_search import _write

CHECKPOINT_FORMAT = "mmsearch-finetune-a2c-v42"
SCHEDULE_FORMAT = "mmsearch-finetune-schedule-v42"


def code_hashes42():
    root = Path(__file__).resolve().parents[1]
    files = [Path(__file__), Path(__file__).with_name("rl_recovery42.py"), root/"scripts/train_finetune42.py"]
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def phase_clock(record_cpu, recovery_cpu, *, fraction=0.05, phase_id="finetune42-v1",
                episode_origin=0, delayed_origin=0):
    if not phase_id or not math.isfinite(fraction) or not 0 <= fraction <= 0.5:
        raise ValueError("invalid phase identity or auxiliary fraction")
    if (type(episode_origin) is not int or type(delayed_origin) is not int
            or not 0 <= delayed_origin <= episode_origin):
        raise ValueError("invalid phase episode origins")
    value = {"phase_id": phase_id, "record_origin": record_cpu,
             "recovery_origin": recovery_cpu, "recovery_fraction": fraction,
             "episode_origin": episode_origin, "delayed_origin": delayed_origin}
    phase_usage(value, record_cpu, recovery_cpu)
    return value


def phase_usage(clock, record_cpu, recovery_cpu):
    values = (record_cpu, recovery_cpu, clock["record_origin"], clock["recovery_origin"])
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("invalid measured phase CPU")
    record = record_cpu-clock["record_origin"]
    recovery = recovery_cpu-clock["recovery_origin"]
    if record < -1e-9 or recovery < -1e-9:
        raise ValueError("phase CPU precedes its origin")
    return max(0, record), max(0, recovery)


def recovery_due(clock, record_cpu, recovery_cpu):
    record, recovery = phase_usage(clock, record_cpu, recovery_cpu)
    # A bounded episode may overshoot the share; do not launch another until
    # main search catches up. Historical v4 allocation creates no phase debt.
    return bool(clock["recovery_fraction"] and record > 0 and
                recovery < clock["recovery_fraction"]*(record+recovery))


class Finetune42Controller(RestartRecordController):
    def __init__(self, initial_terms, *, finetune_context=None, **kwargs):
        self.finetune_context = copy.deepcopy(finetune_context or {})
        super().__init__(initial_terms, **kwargs)

    def candidate(self):
        value = super().candidate()
        value["metadata"]["finetune42"] = copy.deepcopy(self.finetune_context)
        return value

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name("."+path.name+".v42-private-"+uuid.uuid4().hex)
        try:
            super().save(staged)
            value = json.loads(staged.read_text())
            value.update(format=CHECKPOINT_FORMAT, finetune42=self.finetune_context)
            value["code_hashes"].update(code_hashes42())
            _write(path, value)
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(staged.suffix+".tmp").unlink(missing_ok=True)

    @classmethod
    def load(cls, path, *, native_bridge=None):
        payload = Path(path).read_bytes()
        value = json.loads(payload)
        if value["format"] == CHECKPOINT_FORMAT:
            if not value.get("finetune42"):
                raise ValueError("v42 checkpoint missing phase identity")
            for name, expected in code_hashes42().items():
                if value.get("code_hashes", {}).get(name) != expected:
                    raise ValueError("v42 source identity changed across resume")
            context = value["finetune42"]
            value["format"] = "mmsearch-restart-a2c-v4"
        elif value["format"] == "mmsearch-restart-a2c-v4":
            context = {}
        else:
            raise ValueError("v42 migration requires a matched v4 checkpoint")
        # Keep the input checkpoint directory untouched, including transient
        # parent-format load files. The existing v4 loader verifies its hashes.
        with tempfile.TemporaryDirectory(prefix="mmsearch-v42-load-") as temporary:
            staged = Path(temporary)/"checkpoint.json"
            _write(staged, value)
            obj = super().load(staged, native_bridge=native_bridge)
        obj.finetune_context = copy.deepcopy(context)
        return obj
