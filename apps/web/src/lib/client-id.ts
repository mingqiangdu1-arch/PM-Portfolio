/**
 * Generate a client-side identifier without relying on Secure Context-only APIs.
 *
 * `crypto.randomUUID()` is preferred when the browser exposes it. HTTP origins
 * may still expose `getRandomValues()`, so use it to construct an RFC 4122
 * version 4 UUID when `randomUUID()` is unavailable.
 */
export function createClientId(): string {
  const cryptoApi = globalThis.crypto;

  if (typeof cryptoApi?.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  if (typeof cryptoApi?.getRandomValues !== "function") {
    throw new Error("Web Crypto API is unavailable; cannot generate a client ID.");
  }

  const bytes = new Uint8Array(16);
  cryptoApi.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
