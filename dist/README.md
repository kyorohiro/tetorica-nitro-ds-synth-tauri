# Tetorica Nitro DS Synth

Serve this directory over HTTPS or localhost and open index.html.
For itch.io, upload the ZIP as an HTML playable project.

Try the Keyboard or the JavaScript examples in Files. Use Menu → Import to open a
2SF folder or select song and library files. 2SF playback supports ROM-boot sets
with standard timing. Supply your own songs and libraries.
Use `liveFx()` in Code for software effects on the Synth output.

The JavaScript and CSS are copied from the authored files. Edit and reload
the page to try your changes. Monaco can load from its CDN, with a local text
editor available when the CDN is unavailable.

## Rebuild the shared DS sound renderer

Install Emscripten, then run from the unpacked ZIP:

    sh sources/2sf/rebuild.sh synth-nitro-ds/generated/skyemu-2sf.wasm

The required SkyEmu source, Tetorica adapter and build recipe are in sources/2sf.
See LICENSE and sources/2sf/skyemu-2sf-notices.txt for attribution.
The software effect source and rebuild instructions are in sources/code-effects.
