"""V43 checkpoint identity for the unchanged V42 5%-CPU continued learner."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
from mmsearch.rl_finetune42 import Finetune42Controller, phase_clock, phase_usage, recovery_due
from mmsearch.rl_search import _write

CHECKPOINT_FORMAT = "mmsearch-finetune-a2c-v43"
SCHEDULE_FORMAT = "mmsearch-finetune-schedule-v43"


def code_hashes43():
    root = Path(__file__).resolve().parents[1]
    paths = [Path(__file__), Path(__file__).with_name("rl_recovery43.py"),
             root/"scripts/train_finetune43.py", root/"scripts/train_recovery_pool43.py"]
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


class Finetune43Controller(Finetune42Controller):
    def candidate(self):
        value = super().candidate()
        value["metadata"]["finetune43"] = value["metadata"].pop("finetune42")
        return value

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name("."+path.name+".v43-private-"+uuid.uuid4().hex)
        try:
            super().save(staged)
            value = json.loads(staged.read_text())
            value["format"] = CHECKPOINT_FORMAT
            value["finetune43"] = value.pop("finetune42")
            value["code_hashes"].update(code_hashes43())
            _write(path, value)
        finally:
            staged.unlink(missing_ok=True)
            staged.with_suffix(staged.suffix+".tmp").unlink(missing_ok=True)

    @classmethod
    def load(cls, path, *, native_bridge=None):
        value = json.loads(Path(path).read_bytes())
        if value["format"] == CHECKPOINT_FORMAT:
            if not value.get("finetune43"):
                raise ValueError("v43 missing phase identity")
            for name, expected in code_hashes43().items():
                if value.get("code_hashes", {}).get(name) != expected:
                    raise ValueError("v43 source identity changed across resume")
            value["format"] = "mmsearch-finetune-a2c-v42"
            value["finetune42"] = value.pop("finetune43")
        elif value["format"] != "mmsearch-restart-a2c-v4":
            raise ValueError("v43 requires matched v4 migration or v43 checkpoint")
        with tempfile.TemporaryDirectory(prefix="mmsearch-v43-load-") as temporary:
            staged = Path(temporary)/"checkpoint.json"
            _write(staged, value)
            obj = super().load(staged, native_bridge=native_bridge)
        return obj
