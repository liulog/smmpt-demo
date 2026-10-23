#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bind a run to the exact source inputs and artifacts; never invoke a build."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def sources(root):
    result = {}
    for directory in ('payload', 'scripts'):
        for path in sorted((root / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                result[str(path.relative_to(root))] = digest(path)
    for directory in ('NEMU', 'opensbi'):
        repo = root / directory
        entries = subprocess.check_output(['git', '-C', str(repo), 'ls-files',
                                           '--stage', '-z']).split(b'\0')
        for entry in entries:
            if not entry:
                continue
            metadata, name = entry.split(b'\t', 1)
            mode, blob, stage = metadata.split()
            if stage != b'0':
                raise ValueError('unmerged source index: ' + directory)
            path = repo / name.decode()
            if mode == b'160000':
                result[str(path.relative_to(root))] = 'gitlink:' + blob.decode()
            elif path.is_symlink():
                result[str(path.relative_to(root))] = 'symlink:' + str(path.readlink())
            else:
                result[str(path.relative_to(root))] = digest(path)
        # Reject untracked compiled inputs: otherwise the manifest would omit them.
        untracked = subprocess.check_output(['git', '-C', str(repo), 'ls-files',
                                             '--others', '--exclude-standard', '-z'])
        if untracked:
            raise ValueError('stage new ' + directory + ' source files before building')
    return result


def artifact_paths(mode):
    paths = ['nemu/build/riscv64-nemu-interpreter', 'payload.bin', 'payload.elf',
             'opensbi/platform/generic/firmware/fw_payload.bin',
             'opensbi/platform/generic/firmware/fw_payload.elf', 'nemu.dtb', 'nemu.config']
    if mode == 'enabled':
        paths += ['pool-layout.bin', 'pool-layout-final.bin']
    return paths


def validate(root, out, mode, record):
    if record.get('format') != 1 or record.get('mode') != mode:
        raise ValueError('build record format/mode mismatch')
    if record['sources'] != sources(root):
        raise ValueError('sources changed since build; explicit rebuild required')
    if set(record['artifacts']) != set(artifact_paths(mode)):
        raise ValueError('incomplete artifact record')
    for name, expected in record['artifacts'].items():
        if digest(out / name) != expected:
            raise ValueError('artifact changed since build: ' + name)


def main(action, root, out, mode):
    if mode not in ('enabled', 'disabled', 'no-csr'):
        raise ValueError('unknown mode')
    initial = out / 'input-sources.json'
    record_path = out / 'build-record.json'
    if action == 'capture':
        initial.write_text(json.dumps(sources(root), indent=2) + '\n')
    elif action == 'record':
        record = {'format': 1, 'mode': mode, 'sources': json.loads(initial.read_text()),
                  'artifacts': {name: digest(out / name) for name in artifact_paths(mode)}}
        validate(root, out, mode, record)
        record_path.write_text(json.dumps(record, indent=2) + '\n')
    elif action == 'verify':
        validate(root, out, mode, json.loads(record_path.read_text()))
    else:
        raise ValueError('unknown action')


if __name__ == '__main__':
    if len(sys.argv) != 5:
        sys.exit('usage: build-record.py capture|record|verify ROOT OUTPUT MODE')
    try:
        main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit('Build provenance check failed: ' + str(error))
