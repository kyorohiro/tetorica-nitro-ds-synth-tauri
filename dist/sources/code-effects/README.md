# Code software effects

The BSD-3-Clause Tetorica effect rack processes the Synth output after the DS renderer.
To rebuild its WASM with Emscripten installed, run from this directory:

    sh scripts/build_native_audio_effect.sh /tmp/tetorica-nitro-ds-code-effects
    cp /tmp/tetorica-nitro-ds-code-effects/gain.wasm ../../js/native_audio_effect.wasm
