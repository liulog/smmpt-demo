#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-2-Clause
# Execute existing artifacts only; no compilation or implicit build.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
mode=${1:-enabled}
case "$mode" in
    enabled|disabled|no-csr) ;;
    *) echo "usage: $0 [enabled|disabled|no-csr]" >&2; exit 2 ;;
esac
out="$root/build/$mode"
nemu="$out/nemu/build/riscv64-nemu-interpreter"
firmware="$out/opensbi/platform/generic/firmware/fw_payload.bin"
if [[ ! -x "$nemu" || ! -f "$firmware" ]]; then
    echo "Missing artifacts for $mode. Explicit build required: bash scripts/build.sh $mode" >&2
    exit 2
fi
# Failures and timeouts retain both logs for inspection.
timeout "${TIMEOUT:-120}s" "$nemu" -b -I 2000000000 \
    -l "$out/nemu-runtime.log" "$firmware" > "$out/console.log" 2>&1
python3 "$root/scripts/check-log.py" "$mode" "$out/console.log" "$out/nemu-runtime.log"
echo "PASS ($mode): $out/console.log"
