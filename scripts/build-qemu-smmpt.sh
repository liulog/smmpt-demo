#!/usr/bin/env bash
# Explicit build entry point; no install or clean targets.
set -euo pipefail
cd "$(dirname "$0")/.."
cross=${CROSS_COMPILE:-riscv64-unknown-linux-gnu-}
jobs=${JOBS:-8}
for tool in gcc g++ python3 ninja pkg-config make "${cross}gcc"; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 2; }
done
mkdir -p build/qemu-smmpt build/opensbi-smmpt
(
    cd build/qemu-smmpt
    ../../qemu-smmpt/configure \
        --target-list=riscv64-softmmu --without-default-features \
        --enable-tcg --enable-fdt=system --disable-docs --disable-rust \
        --disable-tools --disable-guest-agent
    ninja -j "$jobs" qemu-system-riscv64
) > build/qemu-smmpt/build.log 2>&1
make -C opensbi-smmpt O=../build/opensbi-smmpt \
    PLATFORM=generic PLATFORM_RISCV_XLEN=64 CROSS_COMPILE="$cross" \
    FW_DYNAMIC=y FW_JUMP=n FW_PAYLOAD=n -j"$jobs" \
    > build/opensbi-smmpt/build.log 2>&1
echo "Built QEMU and OpenSBI. Run: make qemu-run"
