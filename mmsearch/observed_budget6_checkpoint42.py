"""Reuse the audited branch ledger while preserving a nested partial child."""
import json
from pathlib import Path
from .observed_rank3_checkpoint42 import append_checkpoint,save_checkpoint
from .observed_rank3_checkpoint42 import load_checkpoint as _load


def load_checkpoint(directory,quotient_sha):
    checked=_load(directory,quotient_sha)
    if checked is None:return None
    path=Path(directory)/'decoder-state.json'
    if path.exists():
        stored=json.loads(path.read_text())['cursor']
        if stored['next_branch']==checked['next_branch']:
            if stored['prefix_chain_sha256']!=checked['prefix_chain_sha256']:raise AssertionError('nested cursor ledger chain mismatch')
            # The atomic state can advance within the active child without
            # completing another top-level branch; retain that exact state.
            return dict(stored,completed_prefix=checked['completed_prefix'])
    return checked
