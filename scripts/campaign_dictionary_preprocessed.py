"""Frozen dictionary subset SAT with exact RREF/weighted-class preprocessing.

Accepts campaign_recombine_sat arguments, including --extra-terms TXT. Uses
original term IDs and the unchanged independent full-tensor model verifier.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.recombine_sat_preprocessed import build_problem as preprocessed_problem
from scripts import campaign_recombine_sat as driver


def build_problem(*args, **kwargs):
    problem = preprocessed_problem(*args, **kwargs)
    problem["metadata"]["preprocessing"]["driver_code_sha256"] = {
        Path(driver.__file__).name: hashlib.sha256(Path(driver.__file__).read_bytes()).hexdigest(),
        Path(__file__).name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return problem


def main(argv=None):
    # A private namespace reuses the frozen snapshot, feasibility-control,
    # resource-limit and independent decode workflow without mutating it.
    original = driver.main
    namespace = dict(original.__globals__, build_problem=build_problem, __file__=__file__, __doc__=__doc__)
    run = types.FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
