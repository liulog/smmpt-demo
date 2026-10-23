# SPDX-License-Identifier: BSD-2-Clause
"""Host-only checks: temporary text fixtures and rsync; no compiler/build/network."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layout = load('firmware-layout')
record = load('build-record')
prepare = load('prepare-nemu')
logs = load('check-log')


class ToolingTests(unittest.TestCase):
    def test_pool_layout_from_sized_bss_symbol(self):
        self.assertEqual(layout.pool_layout('80047000 00020000 b tables\n'),
                         struct.pack('<QQ', 0x80047000, 0x20000))

    def test_pool_layout_rejects_missing_ambiguous_and_unsafe_bounds(self):
        for text in ('', '80047000 b tables', '80047001 20000 b tables',
                     '80047000 1000 b tables', '801ff000 20000 b tables',
                     '80047000 20000 T tables',
                     '80047000 20000 b tables\n80067000 20000 b tables'):
            with self.subTest(symbols=text), self.assertRaises(ValueError):
                layout.pool_layout(text)

    def test_sync_removes_obsolete_sources_preserves_builds_and_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            source, dest = Path(temp) / 'source', Path(temp) / 'copy'
            source.mkdir()
            dest.mkdir()
            (source / 'current.c').write_text('current source')
            (source / 'untracked.c').write_text('must not be copied')
            (dest / 'removed.c').write_text('obsolete source')
            (dest / 'build').mkdir()
            (dest / 'build' / 'keep').write_text('build fixture')
            dep = dest / 'resource' / 'nanopb'
            dep.mkdir(parents=True)
            (dep / 'keep').write_text('dependency fixture')
            # Real rsync, only Git file enumeration is substituted; no builds.
            entries = b'100644 0000000000000000000000000000000000000000 0\tcurrent.c\0'
            with patch.object(prepare, 'git', return_value=entries):
                prepare.sync_sources(source, dest, {'nanopb': {}})
            self.assertFalse((dest / 'removed.c').exists())
            self.assertFalse((dest / 'untracked.c').exists())
            self.assertEqual((dest / 'current.c').read_text(), 'current source')
            self.assertEqual((dest / 'build' / 'keep').read_text(), 'build fixture')
            self.assertEqual((dep / 'keep').read_text(), 'dependency fixture')

    def test_preparation_rejects_source_checkout_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'build' / 'enabled' / 'nemu'
            dest.mkdir(parents=True)
            (dest / '.git').write_text('gitdir: elsewhere')
            with self.assertRaisesRegex(ValueError, 'Git checkout'):
                prepare.prepare(Path(temp) / 'source', dest, Path(temp) / 'lock')

    def test_build_record_rejects_changed_source_and_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            mode = 'disabled'
            for name in record.artifact_paths(mode):
                path = out / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('artifact fixture')
            with patch.object(record, 'sources', return_value={'payload/main.c': 'original'}):
                record.main('capture', ROOT, out, mode)
                record.main('record', ROOT, out, mode)
                record.main('verify', ROOT, out, mode)
                (out / 'payload.bin').write_text('changed artifact')
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    record.main('verify', ROOT, out, mode)
            with patch.object(record, 'sources', return_value={'payload/main.c': 'changed'}):
                with self.assertRaisesRegex(ValueError, 'sources changed'):
                    record.main('verify', ROOT, out, mode)

    def test_build_record_rejects_missing_and_wrong_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                record.main('verify', ROOT, Path(temp), 'enabled')
            with self.assertRaisesRegex(ValueError, 'format/mode'):
                record.validate(ROOT, Path(temp), 'enabled', {'format': 1, 'mode': 'disabled'})

    def test_historical_log_cannot_validate_extended_payload(self):
        archive = ROOT / 'docs/results/2026-10-24-enabled'
        with self.assertRaisesRegex(ValueError, 'missing guest marker'):
            logs.check('enabled', (archive / 'console.log').read_text(),
                       (archive / 'nemu-runtime.log').read_text())

    def test_extended_log_requires_each_added_check(self):
        # Synthetic parser inputs only, never presented as emulator results.
        archive = ROOT / 'docs/results/2026-10-24-enabled'
        original = (archive / 'console.log').read_text()
        runtime = (archive / 'nemu-runtime.log').read_text()
        markers = [
            'MPT-DEMO: RW data and X-only code coexist PASS',
            'MPT-DEMO: all 16 leaf slots with independent RWX PASS',
            'MPT-DEMO: real 64 KiB and 32 MiB boundary accesses PASS',
            'MPT-DEMO: entire firmware table pool read/write protection PASS',
        ]
        logs.check('enabled', original + '\n'.join(markers), runtime)
        for missing in markers:
            with self.subTest(marker=missing), self.assertRaises(ValueError):
                logs.check('enabled', original + '\n'.join(x for x in markers if x != missing), runtime)


if __name__ == '__main__':
    unittest.main()
