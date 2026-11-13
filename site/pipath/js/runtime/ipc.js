// A one-way message queue in shared memory, so the page can talk to a Python program that is
// busy running (a worker that is waiting inside time.sleep() can't receive postMessage).
// One side writes (push), the other reads (pop). Messages are short strings.

const HEADER = 8; // two Int32: write position, read position

export class Ring {
  /** @param {SharedArrayBuffer} sab */
  constructor(sab) {
    this.idx = new Int32Array(sab, 0, 2);
    this.data = new Uint8Array(sab, HEADER);
    this.size = this.data.length;
  }

  static create(bytes = 64 * 1024) {
    return new SharedArrayBuffer(HEADER + bytes);
  }

  /** Adds a message. False if it doesn't fit (the reader is far behind). */
  push(text) {
    const body = new TextEncoder().encode(text);
    const need = 4 + body.length;
    const w = Atomics.load(this.idx, 0);
    const r = Atomics.load(this.idx, 1);
    const used = (w - r + this.size) % this.size;
    if (need >= this.size - used - 1) return false;
    const put = (pos, bytes) => {
      for (let i = 0; i < bytes.length; i++) this.data[(pos + i) % this.size] = bytes[i];
    };
    put(w, [body.length & 255, (body.length >> 8) & 255, (body.length >> 16) & 255, (body.length >> 24) & 255]);
    put(w + 4, body);
    Atomics.store(this.idx, 0, (w + need) % this.size);
    return true;
  }

  /** The oldest message, or null if there isn't one. */
  pop() {
    const w = Atomics.load(this.idx, 0);
    const r = Atomics.load(this.idx, 1);
    if (w === r) return null;
    const get = (pos, n) => Uint8Array.from({ length: n }, (_, i) => this.data[(pos + i) % this.size]);
    const h = get(r, 4);
    const len = h[0] | (h[1] << 8) | (h[2] << 16) | (h[3] << 24);
    const text = new TextDecoder().decode(get(r + 4, len));
    Atomics.store(this.idx, 1, (r + 4 + len) % this.size);
    return text;
  }

  get hasData() {
    return Atomics.load(this.idx, 0) !== Atomics.load(this.idx, 1);
  }

  clear() {
    Atomics.store(this.idx, 1, Atomics.load(this.idx, 0));
  }
}

/** Slots in the shared control array. */
export const CTL = { STOP: 0, ACTIVITY: 1, WAKE: 2, EOF: 3 };
