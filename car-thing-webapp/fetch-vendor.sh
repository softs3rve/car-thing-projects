#!/bin/sh
# Downloads the third-party files index.html expects in vendor/ and fonts/
# (see the importmap and @font-face rules in index.html). They're not
# committed to this repo: they're other people's code and fonts, each with
# its own license, which this script copies alongside them.
#
# Needs Node.js (for `npm pack`). Run from anywhere:
#   sh car-thing-webapp/fetch-vendor.sh
set -eu

BRIDGETHING_CLIENT=0.12.1
BRIDGETHING_LIB=0.12.1   # @bridgething/client 0.12.1 pins lib to exactly this
MSGPACK=3.1.3
PAKO=3.0.2

HERE=$(cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cd "$TMP"
npm pack --silent \
  "@bridgething/client@$BRIDGETHING_CLIENT" \
  "@bridgething/lib@$BRIDGETHING_LIB" \
  "@msgpack/msgpack@$MSGPACK" \
  "pako@$PAKO" \
  "@fontsource/arimo" \
  "@fontsource/source-code-pro" > /dev/null

unpack() { mkdir -p "$2" && tar xzf "$1" -C "$2" --strip-components=1; }
unpack bridgething-client-*.tgz client
unpack bridgething-lib-*.tgz lib
unpack msgpack-msgpack-*.tgz msgpack
unpack pako-*.tgz pako
unpack fontsource-arimo-*.tgz arimo
unpack fontsource-source-code-pro-*.tgz scp

V="$HERE/vendor"
F="$HERE/fonts"
rm -rf "$V" "$F"
mkdir -p "$V/bridgething-client" "$V/bridgething-lib" "$V/msgpack" "$F"

cp -R client/dist "$V/bridgething-client/"
cp client/LICENSE "$V/bridgething-client/"
cp -R lib/dist "$V/bridgething-lib/"
cp lib/LICENSE "$V/bridgething-lib/"
cp -R msgpack/dist.esm "$V/msgpack/"
cp msgpack/LICENSE "$V/msgpack/"
cp pako/dist/browser/pako.esm.min.mjs "$V/"
cp pako/LICENSE "$V/pako-LICENSE"
cp "$HERE/uuid-shim.js" "$V/"

# Type declarations, source maps, and build metadata aren't needed on the device.
find "$V" \( -name '*.d.ts' -o -name '*.map' -o -name '*.tsbuildinfo' \) -exec rm {} +

cp arimo/files/arimo-latin-700-normal.woff2 "$F/arimo-bold.woff2"
cp arimo/LICENSE "$F/arimo-LICENSE"
cp scp/files/source-code-pro-latin-400-normal.woff2 "$F/source-code-pro-regular.woff2"
cp scp/files/source-code-pro-latin-700-normal.woff2 "$F/source-code-pro-bold.woff2"
cp scp/LICENSE "$F/source-code-pro-LICENSE"

echo "vendor/ and fonts/ ready in $HERE"
