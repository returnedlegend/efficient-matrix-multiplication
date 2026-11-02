#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
lean_bin="${LEAN_BIN:-lean/.toolchain/lean-4.19.0-linux/bin/lean}"
"$lean_bin" --version
"$lean_bin" -o lean/Certificate.olean lean/Certificate.lean
if [[ $# -gt 0 ]]; then
  LEAN_PATH=lean "$lean_bin" "$1"
fi
