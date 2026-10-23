#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-2-Clause
# Explicit build entry point. run.sh never invokes this script.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
mode=${1:-enabled}
case "$mode" in
    enabled) option=y; absent=(); mpt=y ;;
    disabled) option=n; absent=(-DEXPECT_ABSENT); mpt=y ;;
    no-csr) option=y; absent=(-DEXPECT_ABSENT); mpt=n ;;
    *) echo "usage: $0 [enabled|disabled|no-csr]" >&2; exit 2 ;;
esac
cross=${CROSS_COMPILE:-riscv64-unknown-linux-gnu-}
jobs=${JOBS:-8}
out="$root/build/$mode"
copy="$out/nemu"
if [[ "$root" =~ [[:space:]] ]]; then
    echo "OpenSBI requires a checkout path without whitespace" >&2; exit 2
fi
for tool in rsync python3 dtc make gcc g++ "${cross}gcc" "${cross}objcopy"; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 2; }
done
test -f "$root/NEMU/Kconfig"
test -f "$root/opensbi/include/sbi/sbi_ecall_mpt.h"
mkdir -p "$out" "$copy"
# Per-mode copies keep generated NEMU files outside the submodule checkout.
rsync -a --exclude=.git --exclude=/build --exclude=/include/config \
    --exclude=/include/generated --exclude=/.config --exclude=/.config.old \
    "$root/NEMU/" "$copy/"
python3 - "$copy" "$mpt" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
config = (root / 'configs/riscv64-xs_mpt_defconfig').read_text()
required = ('CONFIG_MSIZE=0x7ff80000000', 'CONFIG_PERF_OPT=y',
            'CONFIG_RV_MPT_CHECK=y')
for value in required:
    if value not in config:
        raise SystemExit('Unexpected pinned NEMU config: missing ' + value)
# 4 GiB sparse host backing retains NEMU's 64-bit paddr_t; DT advertises 2 GiB.
config = config.replace(required[0], 'CONFIG_MSIZE=0x100000000')
config = config.replace(required[1], '# CONFIG_PERF_OPT is not set\n'
                        'CONFIG_RV_PMP_CHECK=y\nCONFIG_RV_PMA_CHECK=y')
if sys.argv[2] == 'n':
    config = config.replace(required[2], '# CONFIG_RV_MPT_CHECK is not set')
(root / '.config').write_text(config)
PY
(
    cd "$copy"
    export NEMU_HOME="$copy"
    # Suppress NEMU's upstream automatic git-add/commit recipes.
    make __NOT_DEFINED=1 "$copy/tools/kconfig/build/conf" "$copy/tools/fixdep/build/fixdep"
    tools/kconfig/build/conf --olddefconfig Kconfig
    tools/kconfig/build/conf --syncconfig Kconfig
    # Validate the effective config before compiling the emulator.
    python3 - "$mpt" <<'PY'
from pathlib import Path
import sys
text = Path('.config').read_text().splitlines()
for value in ('CONFIG_RV_PMP_CHECK=y', 'CONFIG_RV_PMA_CHECK=y',
              '# CONFIG_PERF_OPT is not set', 'CONFIG_MSIZE=0x100000000'):
    if value not in text:
        raise SystemExit('Unsafe effective NEMU config: missing ' + value)
expected = ('CONFIG_RV_MPT_CHECK=y' if sys.argv[1] == 'y'
            else '# CONFIG_RV_MPT_CHECK is not set')
if expected not in text:
    raise SystemExit('Wrong effective MPT configuration')
PY
    make __NOT_DEFINED=1 -j"$jobs"
) > "$out/nemu-build.log" 2>&1
cp "$copy/.config" "$out/nemu.config"
dtc -I dts -O dtb -o "$out/nemu.dtb" "$root/payload/nemu.dts"
flags=(-march=rv64imac_zicsr_zifencei -mabi=lp64 -mcmodel=medany -mno-relax
       -msmall-data-limit=0 -ffreestanding -fno-builtin -fno-stack-protector
       -nostdlib -static -no-pie -O2 -Wall -Wextra -Werror
       -I"$root/opensbi/include" -Wl,--build-id=none)
"${cross}gcc" "${flags[@]}" "${absent[@]}" -Wl,-T,"$root/payload/link.ld" \
    "$root/payload/start.S" "$root/payload/main.c" -o "$out/payload.elf" \
    > "$out/payload-build.log" 2>&1
"${cross}objcopy" -O binary "$out/payload.elf" "$out/payload.bin"
make -C "$root/opensbi" PLATFORM=generic PLATFORM_RISCV_XLEN=64 \
    O="$out/opensbi" CROSS_COMPILE="$cross" \
    CONFIG_SBI_ECALL_MPT_DEMO="$option" FW_TEXT_START=0x80000000 \
    FW_DYNAMIC=n FW_JUMP=n FW_PAYLOAD=y FW_PAYLOAD_OFFSET=0x200000 \
    FW_FDT_PATH="$out/nemu.dtb" FW_PAYLOAD_PATH="$out/payload.bin" \
    FW_PAYLOAD_FDT_OFFSET=0x8000000 -j"$jobs" > "$out/opensbi-build.log" 2>&1
{
    git -C "$root/NEMU" rev-parse HEAD
    git -C "$root/opensbi" rev-parse HEAD
    sha256sum "$out/payload.bin" "$out/opensbi/platform/generic/firmware/fw_payload.bin"
} > "$out/manifest.txt"
echo "Built ($mode): $out; run explicitly with bash scripts/run.sh $mode"
