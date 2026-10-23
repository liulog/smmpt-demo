#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check guest evidence: NEMU exit status alone does not prove completion."""
import re
import sys
from pathlib import Path


def check(mode, console, runtime):
    if mode not in ('enabled', 'disabled', 'no-csr'):
        raise ValueError('unknown mode: ' + mode)
    for failure in ('MPT-DEMO FAIL', 'HIT BAD TRAP', 'ABORT', 'Kernel panic'):
        if failure in console or failure in runtime:
            raise ValueError('guest/emulator failure: ' + failure)
    if 'HIT GOOD TRAP' not in runtime:
        raise ValueError('missing NEMU good trap (timeout/budget is not success)')
    if mode == 'enabled':
        required = ['MPT-DEMO: S-mode tests starting',
                    'MPT-DEMO: ABI, splitting, exhaustion PASS',
                    'MPT-DEMO: all RWX combinations and access faults PASS']
        required += [f'MPT-DEMO: permissions={p:016x} load/store/fetch + recovery PASS'
                     for p in range(8)]
        for marker in required:
            if marker not in console:
                raise ValueError('missing guest marker: ' + marker)
        if not re.search(r'MPT-DEMO PASS checks=0x[0-9a-f]{16}; '
                         r'standalone S-mode payload, MPT enabled', console):
            raise ValueError('missing standalone payload completion')
    elif 'MPT-DEMO: absent-extension regression PASS' not in console:
        raise ValueError('missing absent-extension completion')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: check-log.py MODE CONSOLE_LOG RUNTIME_LOG')
    try:
        check(sys.argv[1], Path(sys.argv[2]).read_text(errors='replace'),
              Path(sys.argv[3]).read_text(errors='replace'))
    except ValueError as error:
        sys.exit('FAIL: ' + str(error))
