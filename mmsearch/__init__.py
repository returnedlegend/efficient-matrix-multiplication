"""Exact F2 matrix-multiplication search and certificate tools."""

from importlib import import_module

__all__ = ["multiplication_tensor", "naive_candidate", "strassen_candidate",
           "verify_candidate", "verify_file", "write_standalone_verifier"]


def __getattr__(name):
    """Keep module entry points unloaded until their package export is used."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = "tensor" if name in __all__[:3] else "verify"
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value
