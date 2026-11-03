"""Create a separate combined source manifest before freezing a new pool."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mmsearch.rl_pool_curriculum import combine_raw_pools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    value = combine_raw_pools(args.sources, args.output_dir)
    print(json.dumps({"path": str(args.output_dir.resolve()), "source_pools": len(value["source_pools"]),
                      "all_trial_entries": len(value["entries"])}))


if __name__ == "__main__":
    main()
