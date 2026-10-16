// Hand-written replacement for the npm `uuid` package - @bridgething/lib's
// uuid.js only imports `parse`, `stringify`, and `v7` from it, so vendoring
// the real multi-file package (each submodule statically re-exported from
// its index.js, all fetched by the browser regardless of usage) isn't worth
// it for three small, well-specified functions.

export function stringify(bytes) {
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return (
    hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" +
    hex.slice(16, 20) + "-" + hex.slice(20)
  );
}

export function parse(uuid) {
  const hex = uuid.replace(/-/g, "");
  const bytes = new Uint8Array(16);
  for (let i = 0; i < 16; i++) bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  return bytes;
}

// RFC 9562 UUIDv7: 48-bit big-endian ms timestamp + random bits, with the
// version/variant nibbles set per spec.
export function v7() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);

  let ts = Date.now();
  for (let i = 5; i >= 0; i--) {
    bytes[i] = ts & 0xff;
    ts = Math.floor(ts / 256);
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x70; // version 7
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10

  return stringify(bytes);
}
