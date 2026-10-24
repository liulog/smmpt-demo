#!/usr/bin/env bash
# Run existing artifacts only. Never configure, build, or install anything.
set -euo pipefail
cd "$(dirname "$0")/.."
qemu=./build/qemu-smmpt/qemu-system-riscv64
firmware=./build/opensbi-smmpt/platform/generic/firmware/fw_dynamic.bin
image=${IMAGE:-../linux-riscv-gate-merge/arch/riscv/boot/Image}
initrd=${INITRD:-../linux-riscv-gate-merge/rootfs.cpio.gz}
if [[ ! -x "$qemu" ]]; then
    echo "Missing QEMU artifact: $qemu; explicit compilation is required." >&2
    exit 2
fi
for input in "$firmware" "$image" "$initrd"; do
    if [[ ! -r "$input" ]]; then
        echo "Missing input: $input" >&2
        exit 2
    fi
done
exec "$qemu" \
    -machine virt -accel tcg \
    -cpu rv64,sv48=off,sv57=off,x-smsdid=on,x-smmpt=on,mptsdidlen=6 \
    -smp 1 -m 1G -nographic -monitor none -nic none \
    -bios "$firmware" -kernel "$image" -initrd "$initrd" \
    -append "${APPEND:-console=ttyS0 earlycon=sbi rdinit=/init}" \
    "$@"
