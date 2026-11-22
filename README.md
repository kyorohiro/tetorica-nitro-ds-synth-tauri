# Tetorica Nitro DS Synth — Desktop

A Tauri desktop app for exploring Nintendo DS sound. Play the Synth from
the keyboard or JavaScript, load 2SF and mini2SF files, edit the selected
channel while a song plays, and audition or capture its sample when paused.
Bring your own music files.

Keyboard, Code, 2SF playback and paused audition use the same SkyEmu sound
renderer in WebAssembly. The desktop app sends its output through Web Audio.

## Run and build

Install Node.js 22 or newer, Python 3.11 or newer, and the
[Tauri prerequisites](https://tauri.app/start/prerequisites/).

```sh
npm ci
npm test
npm run dev
```

The committed `dist/` directory contains the imported Synth. Dev and build
verify it against `release.lock.json`. The plain JavaScript editor works
offline. Monaco can load when its CDN is reachable.

Build on the target platform:

```sh
# macOS, unsigned
npm run build -- --no-sign --bundles app,dmg -- --locked
# Windows
npm run build -- --bundles nsis -- --locked
# Linux
npm run build -- --bundles deb,appimage -- --locked
```

GitHub Actions runs on `v*` tags and manual dispatches. Tag builds attach
installers to a draft release. To build signed macOS app and DMG bundles for
Intel and Apple Silicon locally, set `APPLE_PASSWORD` in the environment
and run `sh deploy_mac.sh` on a Mac with your Developer ID signing
certificate and both Rust targets installed.

## Import a Web release

Create a ZIP with `sh scripts/package_itch_nitro_ds_synth.sh` in the parent
project. From this repository, run:

```sh
npm run import:release -- ../../release/tetorica_nitro_ds_synth_dev_itch.zip --version 0.0.1
```

`--version` updates the desktop app version in the npm, Cargo and Tauri
files. Omit it to keep the current version. The importer preserves the
original Web files and records their hashes in `release.lock.json`.

## Edit and rebuild

- `dist/synth-nitro-ds/` contains the readable Synth, 2SF player and
  AudioWorklet modules.
- `dist/sources/2sf/` contains the pinned SkyEmu source, the Tetorica adapter,
  source notices and the WebAssembly build recipe.
- `desktop/` and `src-tauri/` contain the Tauri integration.

To try a Web edit in the desktop build, edit `dist/` and run
`npm run record:edits` before rebuilding. A subsequent ZIP import replaces
the Web snapshot. Keep any local changes you want to reuse in Git.

The app bundle also includes a readable copy of the Web files under
`source/`. You can serve that folder as a standalone Web app. To rebuild
its WASM with Emscripten, run from that folder:

```sh
sh sources/2sf/rebuild.sh synth-nitro-ds/generated/skyemu-2sf.wasm
```

The wrapper uses the BSD-3-Clause license. SkyEmu, its Nintendo DS ROM
database and DS FreeBIOS have their own notices in
`dist/sources/2sf/skyemu-2sf-notices.txt`.

[Tetorica Web source](https://github.com/kyorohiro/hello_ymfm_wasm/tree/main/docs/synth-nitro-ds)
