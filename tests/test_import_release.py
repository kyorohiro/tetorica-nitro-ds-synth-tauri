# SPDX-License-Identifier: BSD-3-Clause
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import app_version
import import_release as installer


def fixture_files():
    files = {name: b'fixture\n' for name in installer.LOCAL_REQUIRED}
    index = b'<title>Tetorica Nitro DS Synth</title><script type="module" src="synth.js"></script>'
    for name in ('index.html', f'{installer.APP}/index.html'):
        files[name] = index
    files[installer.WASM] = b'\0asm\x01\0\0\0'
    license_text = b'MIT License\n'
    bios_text = b'DS FreeBIOS notice\n'
    files[f'{installer.KIT}/LICENSE'] = license_text
    files[f'{installer.KIT}/src/freebios/drastic_bios_readme.txt'] = bios_text
    files[f'{installer.KIT}/{installer.NOTICES}'] = license_text + bios_text
    files[f'{installer.APP}/generated/{installer.NOTICES}'] = license_text + bios_text
    return files


class ReleaseImportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def make_zip(self, name, files):
        path = self.root / name
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for entry, data in files.items():
                archive.writestr(entry, data)
        return path

    def make_version_files(self):
        cargo = self.root / 'src-tauri'
        cargo.mkdir()
        (self.root / 'package.json').write_text(json.dumps({'name': 'nitro-test', 'version': '0.0.1'}))
        (self.root / 'package-lock.json').write_text(json.dumps({
            'name': 'nitro-test', 'version': '0.0.1', 'packages': {'': {'version': '0.0.1'}},
        }))
        (cargo / 'tauri.conf.json').write_text(json.dumps({
            'productName': 'Tetorica Nitro DS Synth', 'version': '0.0.1',
        }))
        (cargo / 'Cargo.toml').write_text('[package]\nname = "nitro-test"\nversion = "0.0.1"\n')
        (cargo / 'Cargo.lock').write_text(
            'version = 4\n[[package]]\nname = "nitro-test"\nversion = "0.0.1"\n'
            '[[package]]\nname = "dependency"\nversion = "1.2.3"\n'
        )

    def test_import_pins_bytes_and_records_deliberate_edits(self):
        files = fixture_files()
        lock = installer.import_release(self.root, self.make_zip('known.zip', files))
        self.assertEqual(installer.check(self.root), lock)
        for name, original in files.items():
            self.assertEqual((self.root / 'dist' / name).read_bytes(), original, name)

        module = f'{installer.APP}/synth.js'
        (self.root / 'dist' / module).write_bytes(b'// A local edit\n')
        with self.assertRaisesRegex(ValueError, 'unrecorded changes'):
            installer.check(self.root)
        changes = installer.record_local_changes(self.root)
        self.assertEqual(set(changes['files']), {module})
        self.assertEqual(installer.check(self.root), lock)

    def test_import_updates_app_and_lock_versions_independently_of_zip_name(self):
        self.make_version_files()
        dependencies = app_version.dependency_snapshot(self.root)
        lock = installer.import_release(self.root, self.make_zip('unchanged-dev.zip', fixture_files()), '0.1.2')
        app_version.verify_metadata(self.root, '0.1.2')
        self.assertEqual(app_version.dependency_snapshot(self.root), dependencies)
        self.assertEqual(lock['archive'], 'unchanged-dev.zip')

    def test_invalid_release_keeps_existing_dist_and_versions(self):
        self.make_version_files()
        files = fixture_files()
        lock = installer.import_release(self.root, self.make_zip('known.zip', files))
        del files[f'{installer.KIT}/rebuild.sh']
        with self.assertRaisesRegex(ValueError, 'missing: sources/2sf/rebuild.sh'):
            installer.import_release(self.root, self.make_zip('missing.zip', files), '0.1.2')
        self.assertEqual(installer.check(self.root), lock)
        app_version.verify_metadata(self.root, '0.0.1')

    def test_import_rejects_wrong_wasm_and_mismatched_notices(self):
        files = fixture_files()
        with self.assertRaisesRegex(ValueError, 'WebAssembly SkyEmu renderer'):
            installer.import_release(self.root, self.make_zip('wrong-wasm.zip', {**files, installer.WASM: b'broken'}))
        with self.assertRaisesRegex(ValueError, 'notices differ'):
            installer.import_release(self.root, self.make_zip(
                'wrong-notices.zip', {**files, f'{installer.APP}/generated/{installer.NOTICES}': b'wrong'},
            ))
        self.assertFalse((self.root / 'dist').exists())

    def test_import_rejects_traversal_and_case_insensitive_duplicates(self):
        files = fixture_files()
        for name, pattern in [('../outside', 'Unsafe release file path'),
                              ('INDEX.HTML', 'Duplicate ZIP entry')]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, pattern):
                installer.import_release(self.root, self.make_zip('bad.zip', {**files, name: b'extra'}))
        self.assertFalse((self.root / 'dist').exists())


if __name__ == '__main__':
    unittest.main()
