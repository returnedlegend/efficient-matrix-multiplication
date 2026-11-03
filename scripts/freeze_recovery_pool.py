"""Freeze one empirical recovery-pool version and its held-out split."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.rl_pool_curriculum import freeze_pool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    value = freeze_pool(args.source, args.destination)
    print(json.dumps({"path": str(args.destination.resolve()),
                      "sha256": hashlib.sha256((args.destination/"manifest.json").read_bytes()).hexdigest(),
                      "task_buckets": dict(Counter(x["task_bucket"] for x in value["entries"])),
                      "train": len(value["split"]["train"]), "heldout": len(value["split"]["heldout"]),
                      "small_pool": value["small_pool"]}))


if __name__ == "__main__":
    main()
