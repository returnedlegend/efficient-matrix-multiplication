#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="${1:-$repo_dir/native/flip_worker}"
mkdir -p "$(dirname "$output")"
"${CXX:-g++}" -std=c++17 -O3 -DNDEBUG -Wall -Wextra -Wpedantic "$repo_dir/native/flip_worker.cpp" -o "$output"
sha256sum "$repo_dir/native/flip_worker.cpp" "$output" > "$output.sha256"
echo "$output"
