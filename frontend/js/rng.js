/* Seeded PRNG (mulberry32) with Python-random-style helpers.
   Deterministic per seed — same seed, same campaign, same heartbreaks. */
"use strict";

function makeRng(seed) {
  let t = seed >>> 0;
  const next = () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
  let spare = null;
  return {
    random: next,
    uniform(a, b) {
      return a + (b - a) * next();
    },
    randint(a, b) {
      return a + Math.floor(next() * (b - a + 1));
    },
    gauss(mu = 0, sigma = 1) {
      if (spare !== null) {
        const s = spare;
        spare = null;
        return mu + sigma * s;
      }
      let u = 0;
      let v = 0;
      while (u === 0) u = next();
      while (v === 0) v = next();
      const m = Math.sqrt(-2 * Math.log(u));
      spare = m * Math.sin(2 * Math.PI * v);
      return mu + sigma * m * Math.cos(2 * Math.PI * v);
    },
    choice(arr) {
      return arr[Math.floor(next() * arr.length)];
    },
    sample(arr, k) {
      const pool = arr.slice();
      const out = [];
      while (out.length < k && pool.length) {
        out.push(pool.splice(Math.floor(next() * pool.length), 1)[0]);
      }
      return out;
    },
    shuffle(arr) {
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(next() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
      }
      return arr;
    },
  };
}
