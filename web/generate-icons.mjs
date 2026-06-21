/**
 * Generate PWA icons: black background + amber rounded-rect mark.
 * Uses pngjs (pure JS, no native deps).
 * Usage: node generate-icons.mjs
 */
import { PNG } from 'pngjs';
import { writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dir = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dir, 'static');

// Colours
const BLACK  = [0x00, 0x00, 0x00, 0xff];
const AMBER  = [0xff, 0xb0, 0x20, 0xff];

/** Set a pixel (x,y) in the PNG data buffer */
function setPixel(data, w, x, y, rgba) {
  const i = (y * w + x) * 4;
  data[i]     = rgba[0];
  data[i + 1] = rgba[1];
  data[i + 2] = rgba[2];
  data[i + 3] = rgba[3];
}

/**
 * Draw a filled rounded rectangle on `data`.
 * @param {Buffer} data - raw RGBA buffer
 * @param {number} w - image width
 * @param {number} x0,y0 - top-left corner
 * @param {number} rw,rh - rect width/height
 * @param {number} r  - corner radius
 * @param {number[]} color - [r,g,b,a]
 */
function fillRoundRect(data, w, x0, y0, rw, rh, r, color) {
  for (let y = y0; y < y0 + rh; y++) {
    for (let x = x0; x < x0 + rw; x++) {
      const dx = Math.min(x - x0, x0 + rw - 1 - x);
      const dy = Math.min(y - y0, y0 + rh - 1 - y);
      if (dx >= r || dy >= r) {
        setPixel(data, w, x, y, color);
      } else {
        // corner: check distance from arc centre
        const cx = x0 + r - 1 - (r - 1 - dx);
        const cy = y0 + r - 1 - (r - 1 - dy);
        const dist = Math.sqrt((x - (x0 + r - 1)) ** 2 + (y - (y0 + r - 1)) ** 2);
        if (dist <= r) setPixel(data, w, x, y, color);
        // also handle the other three corners symmetrically via the clamp logic above
      }
    }
  }
}

/**
 * Proper rounded rectangle: test all four corners explicitly.
 */
function fillRR(data, w, x0, y0, rw, rh, r, color) {
  const x1 = x0 + rw - 1;
  const y1 = y0 + rh - 1;
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      // corner centres
      const inCorner = (
        (x < x0 + r && y < y0 + r && Math.hypot(x - (x0 + r), y - (y0 + r)) > r) ||
        (x > x1 - r && y < y0 + r && Math.hypot(x - (x1 - r), y - (y0 + r)) > r) ||
        (x < x0 + r && y > y1 - r && Math.hypot(x - (x0 + r), y - (y1 - r)) > r) ||
        (x > x1 - r && y > y1 - r && Math.hypot(x - (x1 - r), y - (y1 - r)) > r)
      );
      if (!inCorner) setPixel(data, w, x, y, color);
    }
  }
}

function makeIcon(size) {
  const png = new PNG({ width: size, height: size });
  // Fill black background
  for (let i = 0; i < size * size; i++) {
    png.data[i * 4]     = 0;
    png.data[i * 4 + 1] = 0;
    png.data[i * 4 + 2] = 0;
    png.data[i * 4 + 3] = 255;
  }
  // Amber rounded rectangle mark — centred, within 80% safe area for maskable
  const safe = Math.floor(size * 0.80);
  const margin = Math.floor((size - safe) / 2);
  const r = Math.floor(safe * 0.18);  // corner radius ~18% of safe area
  fillRR(png.data, size, margin, margin, safe, safe, r, AMBER);

  // "RM" text via simple pixel art for the 192+ sizes (drawn as thick rectangles)
  // For the icon mark we draw two thin vertical bars with a diagonal (R) and two bars (M)
  // Kept simple: just draw a bold "₹"-like slash — actually just leave it as amber rounded square
  // (a clean geometric mark is cleaner than pixel-font at these sizes)

  return PNG.sync.write(png);
}

const sizes = [
  { name: 'pwa-192x192.png', size: 192 },
  { name: 'pwa-512x512.png', size: 512 },
  { name: 'favicon.png',     size: 64  },
];

for (const { name, size } of sizes) {
  const buf = makeIcon(size);
  writeFileSync(join(OUT, name), buf);
  console.log(`wrote static/${name} (${buf.length} bytes)`);
}
console.log('Done.');
