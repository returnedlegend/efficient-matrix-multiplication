"""Export the trace-form 5x5 multiplication tensor, with optional NumPy output."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.tensor import multiplication_tensor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/T_5_5_5.npy"))
    args = parser.parse_args()
    tensor = multiplication_tensor(5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix == ".npy":
        import numpy as np
        np.save(args.output, np.array(tensor, dtype=np.uint8).reshape(25,25,25), allow_pickle=False)
    else:
        args.output.write_text(json.dumps({"shape": [25,25,25], "field": 2,
                                         "indexing": "A[i,j] B[j,k] C[k,i]", "entries": tensor}) + "\n")
    print(json.dumps({"path": str(args.output), "shape": [25,25,25],
                      "nonzero": sum(tensor), "coefficients": len(tensor)}))


if __name__ == "__main__":
    main()
