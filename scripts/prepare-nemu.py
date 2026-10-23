#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build-only preparation: synchronize tracked sources and fetch locked dependencies."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def sync_sources(source, destination, dependencies):
    with tempfile.TemporaryDirectory(prefix='nemu-tracked-') as temp:
        staging = Path(temp)
        for record in git(source, 'ls-files', '--stage', '-z').split(b'\0'):
            if not record:
                continue
            meta, raw_name = record.split(b'\t', 1)
            mode = meta.split()[0]
            if mode == b'160000':
                # Unused SimPoint gitlink; active dependencies are explicitly locked below.
                continue
            name = raw_name.decode()
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target, follow_symlinks=False)
        # Delete obsolete source files, preserving only generated build state and deps.
        excludes = ['.git', 'build/', '/include/config/', '/include/generated/',
                    '/.config', '/.config.old']
        excludes += ['/resource/' + name + '/' for name in dependencies]
        for name in dependencies:
            (staging / 'resource' / name).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['rsync', '-a', '--delete',
                        *['--exclude=' + value for value in excludes],
                        str(staging) + '/', str(destination) + '/'], check=True)


def prepare(source, destination, lockfile):
    source = source.resolve()
    if destination.is_symlink():
        raise ValueError('NEMU build copy must not be a symlink')
    destination = destination.resolve()
    if source == destination or source.is_relative_to(destination):
        raise ValueError('source must be outside the destination')
    # Only manage this demo's disposable copy, never an arbitrary source checkout.
    if destination.name != 'nemu' or destination.parent.parent.name != 'build':
        raise ValueError('expected build/<mode>/nemu destination')
    if (destination / '.git').exists():
        raise ValueError('refusing to synchronize over a Git checkout')
    git(source, 'diff', '--exit-code', 'HEAD', '--')
    dependencies = json.loads(lockfile.read_text())
    for name, entry in dependencies.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('unsafe dependency path')
        if len(entry['commit']) != 40 or any(c not in '0123456789abcdef' for c in entry['commit']):
            raise ValueError('dependency requires a full commit hash')
    destination.mkdir(parents=True, exist_ok=True)
    sync_sources(source, destination, dependencies)
    for name, entry in dependencies.items():
        repo = destination / 'resource' / name
        if not repo.exists():
            repo.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'init', str(repo)], check=True)
        # Require an actual separate repository, not the parent demo repository.
        if not (repo / '.git').exists():
            raise ValueError('dependency is not a Git checkout: ' + str(repo))
        if subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', 'HEAD'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['git', '-C', str(repo), 'fetch', '--depth=1',
                            entry['url'], entry['commit']], check=True)
            subprocess.run(['git', '-C', str(repo), 'checkout', '--detach',
                            entry['commit']], check=True)
        if git(repo, 'rev-parse', 'HEAD').decode().strip() != entry['commit']:
            raise ValueError('dependency revision differs from lock: ' + str(repo))
        git(repo, 'diff', '--exit-code', 'HEAD', '--')
        if (repo / '.gitmodules').exists():
            subprocess.run(['git', '-C', str(repo), 'submodule', 'update',
                            '--init', '--recursive'], check=True)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: prepare-nemu.py SOURCE DESTINATION LOCKFILE')
    try:
        prepare(*(Path(arg) for arg in sys.argv[1:]))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit('NEMU preparation failed: ' + str(error))
