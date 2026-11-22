#!/bin/sh
set -eu
cd "$(dirname "$0")"

export CI=true
export APPLE_SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-Developer ID Application: KIYOHIRO KAWAMURA (5H7KW7PC7C)}"
export APPLE_ID="${APPLE_ID:-kyorohiro@gmail.com}"
export APPLE_TEAM_ID="${APPLE_TEAM_ID:-5H7KW7PC7C}"

npm run build -- --target x86_64-apple-darwin --bundles app,dmg -- --locked
npm run build -- --target aarch64-apple-darwin --bundles app,dmg -- --locked
