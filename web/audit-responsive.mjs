import { chromium } from 'playwright';

const base = process.env.AUDIT_BASE || 'http://localhost:4173';
const routes = [
  { name: 'home', url: '/' },
  { name: 'trends', url: '/trends' },
  { name: 'cuts', url: '/cuts' },
  { name: 'fees', url: '/fees' },
];
const widths = [
  { tag: 'mobile', width: 390, height: 844 },
  { tag: 'tablet', width: 834, height: 1112 },
  { tag: 'desktop', width: 1440, height: 900 },
];

const waitReady = (page) =>
  page.waitForFunction(() => !document.querySelector('[data-loading]'), { timeout: 8000 });

const b = await chromium.launch();
const issues = [];

// Desktop scroll-spy check: after loading / at scrollTop=0, #overview link must
// be aria-current="page" and no other nav link may be.
async function checkDesktopScrollSpy(b) {
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  await waitReady(page);
  await page.waitForTimeout(600); // allow IntersectionObserver + scroll listener to fire
  const result = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('header nav a[href^="#"]'));
    const active = links.filter(a => a.getAttribute('aria-current') === 'page').map(a => a.getAttribute('href'));
    const overviewActive = document.querySelector('a[href="#overview"]')?.getAttribute('aria-current') === 'page';
    return { active, overviewActive };
  });
  await ctx.close();
  return result;
}

const spyResult = await checkDesktopScrollSpy(b);
if (!spyResult.overviewActive) {
  issues.push(`[desktop] scroll-spy: #overview link NOT aria-current="page" at scrollTop=0 (active: ${spyResult.active.join(', ') || 'none'})`);
} else if (spyResult.active.length > 1) {
  issues.push(`[desktop] scroll-spy: multiple links are aria-current="page" at scrollTop=0 (${spyResult.active.join(', ')})`);
} else {
  console.log('[desktop] scroll-spy: #overview is active at scrollTop=0 OK');
}

for (const vp of widths) {
  const ctx = await b.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') issues.push(`[${vp.tag}] console: ${m.text()}`); });
  page.on('pageerror', (e) => issues.push(`[${vp.tag}] pageerror: ${e.message}`));

  for (const r of routes) {
    await page.goto(base + r.url, { waitUntil: 'networkidle' });
    await waitReady(page);
    await page.waitForTimeout(400);

    const ov = await page.evaluate(() => {
      const de = document.documentElement;
      return de.scrollWidth - de.clientWidth;
    });
    if (ov > 1) issues.push(`[${vp.tag}] ${r.name}: H-OVERFLOW ${ov}px`);

    const wide = await page.evaluate((w) => {
      const out = [];
      for (const el of document.querySelectorAll('*')) {
        const rc = el.getBoundingClientRect();
        if (rc.width > w + 1 && rc.height > 4) out.push(`${el.tagName.toLowerCase()} w=${Math.round(rc.width)}`);
      }
      return out.slice(0, 6);
    }, vp.width);
    if (wide.length) issues.push(`[${vp.tag}] ${r.name}: WIDE ELEMENTS -> ${wide.join(' | ')}`);

    const tiny = await page.evaluate(() => {
      const out = new Set();
      for (const el of document.querySelectorAll('*')) {
        if (!el.children.length && el.textContent.trim()) {
          const fs = parseFloat(getComputedStyle(el).fontSize);
          if (fs < 11) out.add(`${Math.round(fs)}px:"${el.textContent.trim().slice(0, 18)}"`);
        }
      }
      return [...out].slice(0, 6);
    });
    if (tiny.length) issues.push(`[${vp.tag}] ${r.name}: TINY TEXT -> ${tiny.join(' | ')}`);

    await page.screenshot({ path: `audit-shots/${vp.tag}-${r.name}.png`, fullPage: true });
  }
  await ctx.close();
}

await b.close();
if (issues.length) {
  console.log('ISSUES:\n' + issues.join('\n'));
  process.exit(1);
} else {
  console.log('AUDIT OK: no overflow / sub-11px text / console errors at 390/834/1440 across all routes');
}
