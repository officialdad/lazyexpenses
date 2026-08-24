// Renders each HTML diagram in this folder to a PNG beside it. One theme only: the pages
// carry the app's own black palette, so they look the same on a light and a dark README.
// Run from the repo root, after `cd web && npm i` once:
//   node docs/img/shoot.mjs
import { chromium } from './../../web/node_modules/playwright/index.mjs'
import { fileURLToPath } from 'node:url'

const browser = await chromium.launch()
for (const name of ['why-lazy', 'pipeline']) {
  const page = await browser.newPage({
    viewport: { width: 1200, height: 900 },
    deviceScaleFactor: 2,
  })
  await page.goto(new URL(`${name}.html`, import.meta.url).href)
  const out = fileURLToPath(new URL(`${name}.png`, import.meta.url))
  await page.locator('body').screenshot({ path: out })
  console.log('wrote', out)
}
await browser.close()
