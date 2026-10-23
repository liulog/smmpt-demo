#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Extract test-only table bounds from nm output; no new SBI table-pointer API."""
from pathlib import Path
import struct
import subprocess
import sys


def pool_layout(symbols):
    matches = [line.split() for line in symbols.splitlines()
               if line.split() and line.split()[-1] == 'tables']
    if len(matches) != 1 or len(matches[0]) != 4 or matches[0][2] not in ('b', 'B'):
        raise ValueError('expected one BSS tables symbol with a size')
    base, size = (int(value, 16) for value in matches[0][:2])
    if base & 4095 or size != 32 * 4096 or not 0x80000000 <= base < base + size <= 0x80200000:
        raise ValueError('unexpected firmware table pool layout')
    return struct.pack('<QQ', base, size)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: firmware-layout.py NM FIRMWARE_ELF OUTPUT')
    try:
        symbols = subprocess.check_output([sys.argv[1], '-S', sys.argv[2]], text=True)
        Path(sys.argv[3]).write_bytes(pool_layout(symbols))
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit('Firmware layout failed: ' + str(error))
