// crypto.randomUUID exists only in secure contexts (HTTPS or localhost). A
// phone testing the dev server over the LAN (http://192.168.x.x:5174), and
// some older browsers, lack it; getRandomValues is available everywhere.
if (typeof crypto !== 'undefined' && typeof crypto.randomUUID !== 'function') {
  Object.defineProperty(crypto, 'randomUUID', {
    configurable: true,
    value: () => {
      const b = crypto.getRandomValues(new Uint8Array(16))
      b[6] = (b[6] & 0x0f) | 0x40 // version 4
      b[8] = (b[8] & 0x3f) | 0x80 // RFC 4122 variant
      const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
      return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
    },
  })
}

export {}
