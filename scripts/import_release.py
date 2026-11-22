"""Import an editable Nitro DS Synth ZIP and pin its exact contents."""
# SPDX-License-Identifier: BSD-3-Clause
import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP = 'synth-nitro-ds'
KIT = 'sources/2sf'
WASM = f'{APP}/generated/skyemu-2sf.wasm'
NOTICES = 'skyemu-2sf-notices.txt'
KIT_FILES = {
    'LICENSE', 'rebuild.sh', NOTICES, 'skyemu_2sf.c', 'skyemu_adpcm_cache.patch',
    'src/arm7.h', 'src/nds.h', 'src/nds_rom_database.h', 'src/sb_types.h', 'src/shared.h',
    'src/freebios/drastic_bios_arm7.h', 'src/freebios/drastic_bios_arm9.h',
    'src/freebios/drastic_bios_readme.txt',
}
LOCAL_REQUIRED = {
    'index.html', 'tetorica_nitro_ds_synth.webp', 'LICENSE', WASM,
    'licenses/tetorica-virtual-files/LICENSE', 'playground/vendor/fflate-LICENSE',
    f'{APP}/generated/{NOTICES}',
    *(f'{APP}/{name}' for name in (
        'index.html', 'synth.js', 'synth.css', '2sf-player.js', '2sf-worker.js',
        '2sf-waveform.js', '2sf_source.js', 'nds-worklet.js', 'nds-skyemu-core.js', 'nds-skyemu-wasm.js',
    )),
    *(f'{KIT}/{name}' for name in KIT_FILES),
}
LOCAL_MANIFEST = 'local-changes.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_release(destination, hashes):
    missing = LOCAL_REQUIRED - hashes.keys()
    if missing:
        raise ValueError('Expected Nitro DS Synth ZIP; missing: ' + ', '.join(sorted(missing)))
    kit_files = {name.removeprefix(KIT + '/') for name in hashes if name.startswith(KIT + '/')}
    unexpected = kit_files - KIT_FILES
    if unexpected:
        raise ValueError('Unexpected SkyEmu build inputs: ' + ', '.join(sorted(unexpected)))
    for name in ('index.html', f'{APP}/index.html'):
        html = (destination / name).read_text(encoding='utf-8')
        if '<title>Tetorica Nitro DS Synth</title>' not in html or 'type="module"' not in html:
            raise ValueError(f'Expected Nitro DS Synth module entry: {name}')
    if not (destination / WASM).read_bytes().startswith(b'\0asm\x01\0\0\0'):
        raise ValueError('Expected a WebAssembly SkyEmu renderer')
    if hashes[f'{APP}/generated/{NOTICES}'] != hashes[f'{KIT}/{NOTICES}']:
        raise ValueError('SkyEmu renderer and source kit notices differ')
    notices = (destination / KIT / NOTICES).read_text(encoding='utf-8')
    emulator = (destination / KIT / 'LICENSE').read_text(encoding='utf-8').strip()
    bios = (destination / KIT / 'src/freebios/drastic_bios_readme.txt').read_text(encoding='utf-8').strip()
    if not emulator.startswith('MIT License') or emulator not in notices or not bios or bios not in notices:
        raise ValueError('Expected the SkyEmu MIT and DS FreeBIOS notices in the source kit')


def unpack(archive, destination):
    hashes = {}
    members = set()
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            name = safe_name(entry.filename.removesuffix('/') if entry.is_dir() else entry.filename)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if kind not in (0, stat.S_IFDIR if entry.is_dir() else stat.S_IFREG):
                raise ValueError(f'Expected a regular ZIP entry: {name}')
            folded = name.casefold()
            if folded in members:
                raise ValueError(f'Duplicate ZIP entry: {name}')
            members.add(folded)
            if entry.is_dir():
                continue
            data = source.read(entry)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[name] = digest(data)
    validate_release(destination, hashes)
    return hashes


def safe_name(name):
    if not isinstance(name, str) or not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValueError('Expected a safe relative release file path')
    path = PurePosixPath(name)
    if (path.is_absolute() or name != path.as_posix() or '..' in path.parts
            or name == '.' or '\\' in name or ':' in name):
        raise ValueError(f'Unsafe release file path: {name}')
    return name


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def snapshot_dist(root):
    directory = root / 'dist'
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Expected a real dist directory')
    hashes = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlinks are not release files: {path.relative_to(directory)}')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f'Expected a regular release file: {path.relative_to(directory)}')
        name = safe_name(path.relative_to(directory).as_posix())
        hashes[name] = digest(path.read_bytes())
    return hashes


def baseline_files(lock):
    files = lock.get('files') if isinstance(lock, dict) else None
    if not isinstance(files, dict) or not valid_hash(lock.get('sha256')):
        raise ValueError('Expected a pinned release SHA-256 and file hashes')
    for name, sha in files.items():
        safe_name(name)
        if not valid_hash(sha):
            raise ValueError(f'Invalid imported file SHA-256: {name}')
    return files


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate local manifest property: {key}')
        result[key] = value
    return result


def local_changes(root, lock):
    path = root / LOCAL_MANIFEST
    if path.is_symlink():
        raise ValueError('Local change manifest must not be a symlink')
    if not path.exists():
        return None
    baseline = baseline_files(lock)
    manifest = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if (not isinstance(manifest, dict) or set(manifest) != {'schemaVersion', 'baseSha256', 'files'}
            or type(manifest['schemaVersion']) is not int or manifest['schemaVersion'] != 1
            or not isinstance(manifest['files'], dict)):
        raise ValueError('Invalid local change manifest schema')
    if manifest['baseSha256'] != lock['sha256']:
        raise ValueError('Local changes belong to a different imported release; import and reapply edits')
    for name, sha in manifest['files'].items():
        safe_name(name)
        if sha is None:
            if name not in baseline:
                raise ValueError(f'Cannot delete an unknown imported file: {name}')
        elif not valid_hash(sha):
            raise ValueError(f'Invalid local file SHA-256: {name}')
    return manifest


def require_entries(files):
    missing = LOCAL_REQUIRED - files.keys()
    if missing:
        raise ValueError('Local edits must keep application entry files: ' + ', '.join(sorted(missing)))


def record_local_changes(root):
    lock = json.loads((root / 'release.lock.json').read_text())
    baseline = baseline_files(lock)
    local_changes(root, lock)  # Reject stale or malformed records before replacing them.
    actual = snapshot_dist(root)
    require_entries(actual)
    changes = {name: actual.get(name) for name in sorted(baseline.keys() | actual.keys())
               if actual.get(name) != baseline.get(name)}
    manifest = {'schemaVersion': 1, 'baseSha256': lock['sha256'], 'files': changes}
    destination = root / LOCAL_MANIFEST
    if changes:
        with tempfile.TemporaryDirectory(prefix='.local-edits-', dir=root) as temporary:
            staging = Path(temporary) / LOCAL_MANIFEST
            staging.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
            staging.replace(destination)
        print(f"Recorded {len(changes)} local changes over Synth {lock['version']}; imported release hashes kept")
    else:
        destination.unlink(missing_ok=True)
        print(f"Restored imported Synth {lock['version']}; no local changes")
    return manifest


def check(root):
    lock = json.loads((root / 'release.lock.json').read_text())
    actual = snapshot_dist(root)
    manifest = local_changes(root, lock)
    expected = dict(baseline_files(lock))
    if manifest is not None:
        for name, sha in manifest['files'].items():
            if sha is None:
                expected.pop(name)
            else:
                expected[name] = sha
    require_entries(actual)
    if actual != expected:
        raise ValueError('dist has unrecorded changes; run npm run record:edits or import the pinned ZIP again')
    return lock


def prepare_app_version(root, version):
    # Keep each checkout self-contained and support tests loading this module
    # directly by filename, without relying on the caller's Python path.
    spec = importlib.util.spec_from_file_location('app_version', Path(__file__).with_name('app_version.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.prepare_version_update(root, version)


def import_release(root, archive, version=None):
    version_update = prepare_app_version(root, version) if version is not None else None
    if not archive.is_file():
        raise FileNotFoundError(f'Synth release ZIP not found: {archive}')
    sha = digest(archive.read_bytes())
    previous = root / 'release.lock.json'
    old_receipt = previous.read_bytes() if previous.exists() else None
    old_lock = json.loads(old_receipt) if old_receipt is not None else {}
    release_version = old_lock.get('version') if old_lock.get('sha256') == sha else f'sha256-{sha[:12]}'
    local_manifest = root / LOCAL_MANIFEST
    old_local = local_manifest.read_bytes() if local_manifest.exists() else None
    with tempfile.TemporaryDirectory(prefix='.import-', dir=root) as temporary:
        staging = Path(temporary) / 'dist'
        staging.mkdir()
        hashes = unpack(archive, staging)
        lock = {'version': release_version, 'archive': archive.name, 'sha256': sha, 'files': hashes}
        destination = root / 'dist'
        backup = Path(temporary) / 'previous-dist'
        if destination.exists():
            destination.rename(backup)
        try:
            staging.rename(destination)
            previous.write_text(json.dumps(lock, indent=2, sort_keys=True) + '\n')
            local_manifest.unlink(missing_ok=True)
            if version_update is not None:
                version_update.apply()
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            if backup.exists():
                backup.rename(destination)
            if old_receipt is None:
                previous.unlink(missing_ok=True)
            else:
                previous.write_bytes(old_receipt)
            if old_local is not None:
                local_manifest.write_bytes(old_local)
            raise
    print(f'Imported {release_version}: {len(hashes)} files, SHA256 {sha}')
    if version_update is not None:
        print(f'App version set to {version_update.version}; dependency versions preserved')
    return lock

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', nargs='?', type=Path, help='Path to the Synth release ZIP')
    parser.add_argument('--version', help='Set the desktop app version (X.Y.Z), independently of the ZIP name')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--check', action='store_true')
    actions.add_argument('--record-local-changes', action='store_true')
    args = parser.parse_args()
    if (args.check or args.record_local_changes) and (args.zip is not None or args.version is not None):
        parser.error('choose a ZIP import with optional --version, --check, or --record-local-changes')
    if not args.check and not args.record_local_changes and args.zip is None:
        parser.error('provide the ZIP path: npm run import:release -- ./xxx.zip')
    try:
        if args.check:
            lock = check(ROOT)
            manifest = local_changes(ROOT, lock)
            if manifest is None:
                print(f"Verified Synth {lock['version']}: {len(lock['files'])} files")
            else:
                print(f"Verified locally edited Synth {lock['version']}: {len(manifest['files'])} recorded local changes over SHA256 {lock['sha256']}")
        elif args.record_local_changes:
            record_local_changes(ROOT)
        else:
            import_release(ROOT, args.zip, version=args.version)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
