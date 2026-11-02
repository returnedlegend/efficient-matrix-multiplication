#!/usr/bin/env bash
# Pinned official Lean release. SHA256 recorded from the HTTPS-verified release.
set -euo pipefail
cd "$(dirname "$0")"
toolchain_dir=.toolchain/lean-4.19.0-linux
if [[ -x "$toolchain_dir/bin/lean" ]]; then
  "$toolchain_dir/bin/lean" --version
  exit 0
fi
mkdir -p .toolchain
curl -fL --retry 2 --proto '=https' --tlsv1.2 \
  -o .toolchain/lean.tar.zst \
  https://github.com/leanprover/lean4/releases/download/v4.19.0/lean-4.19.0-linux.tar.zst
printf '%s\n' '6fe3ce97a58f44e2b3567d455b994eacec5bfe9ae7774f2a573444480ba813fe  .toolchain/lean.tar.zst' | sha256sum -c -
tar --zstd -xf .toolchain/lean.tar.zst -C .toolchain
"$toolchain_dir/bin/lean" --version
rm .toolchain/lean.tar.zst
