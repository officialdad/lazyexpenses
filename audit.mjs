// Playwright audit of the built dashboard.html (offline file://). Checks: console/page
// errors, horizontal overflow, clipped/overflowing nodes, tiny fonts, icon render — across
// the 3 views at desktop + mobile widths. Screenshots to audit-shots/. Run after dashboard.py.
import { chromium } from "playwright";
import { pathToFileURL } from "url";
import { mkdirSync } from "fs";
import path from "path";

const FILE = pathToFileURL(path.resolve("dashboard.html")).href;
const SHOTS = "audit-shots";
mkdirSync(SHOTS, { recursive: true });

const VIEWS = [["monthly", "This Month"], ["overview", "Overview"], ["recs", "Recommendations"]];
const SIZES = [["desktop", 1366, 900], ["mobile", 390, 844]];
const issues = [];

const browser = await chromium.launch();
const ctx = await browser.newContext();
const page = await ctx.newPage();
const logs = [];
page.on("console", m => { if (m.type() === "error" || m.type() === "warning") logs.push(`[${m.type()}] ${m.text()}`); });
page.on("pageerror", e => logs.push(`[pageerror] ${e.message}`));

await page.goto(FILE, { waitUntil: "load" });

// switch to a view by clicking its tab and wait a tick for render()
async function show(v) {
  await page.evaluate(v => { document.querySelector(`#view button[data-v="${v}"]`).click(); }, v);
  await page.waitForTimeout(120);
}

// nodes whose box sticks out past the viewport width (right edge) -> horizontal-scroll culprits
async function overflowNodes() {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth, bad = [];
    for (const el of document.querySelectorAll("*")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > vw + 1 || r.left < -1) {
        const id = el.id ? "#" + el.id : "";
        bad.push(`${el.tagName.toLowerCase()}${id}.${[...el.classList].join(".")} right=${Math.round(r.right)} vw=${vw}`);
      }
    }
    return [...new Set(bad)].slice(0, 12);
  });
}

// visible text nodes rendered below 11px -> readability floor
async function tinyText() {
  return page.evaluate(() => {
    const bad = [];
    for (const el of document.querySelectorAll("body *")) {
      if (!el.childNodes.length) continue;
      const hasText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
      if (!hasText) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs && fs < 11) bad.push(`${el.tagName.toLowerCase()}.${[...el.classList].join(".")} ${fs}px "${el.textContent.trim().slice(0, 24)}"`);
    }
    return [...new Set(bad)].slice(0, 12);
  });
}

for (const [vk, vlabel] of VIEWS) {
  await show(vk);
  for (const [sk, w, h] of SIZES) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(120);
    const docScroll = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    if (docScroll.sw > docScroll.cw + 1) {
      const nodes = await overflowNodes();
      issues.push({ view: vlabel, size: sk, kind: "h-overflow", detail: `scrollWidth ${docScroll.sw} > ${docScroll.cw}`, nodes });
    }
    const tiny = await tinyText();
    if (tiny.length) issues.push({ view: vlabel, size: sk, kind: "tiny-font", nodes: tiny });
    await page.screenshot({ path: `${SHOTS}/${vk}-${sk}.png`, fullPage: true });
  }
}

// icon render sanity on each view
await page.setViewportSize({ width: 1366, height: 900 });
const iconCounts = {};
for (const [vk, vlabel] of VIEWS) {
  await show(vk);
  iconCounts[vlabel] = await page.evaluate(() => document.querySelectorAll(".view.on svg.mdi").length);
}

await browser.close();

console.log("=== CONSOLE / PAGE ERRORS ===");
console.log(logs.length ? logs.join("\n") : "none");
console.log("\n=== ICON COUNTS (visible mdi per view) ===");
console.log(JSON.stringify(iconCounts));
console.log("\n=== ISSUES ===");
if (!issues.length) console.log("none — no overflow, no sub-11px text in any view/size");
else for (const i of issues) {
  console.log(`\n[${i.view} · ${i.size}] ${i.kind}${i.detail ? " — " + i.detail : ""}`);
  (i.nodes || []).forEach(n => console.log("   " + n));
}
console.log(`\nscreenshots -> ${SHOTS}/`);
