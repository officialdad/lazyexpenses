import { chromium } from 'playwright';

const base = process.env.AUDIT_BASE || 'http://localhost:4173';
const routes = [
  { name: 'home', url: '/' },
  // `shot` is an extra README capture from the same page: /trends is two screens on a
  // phone, and the merchants table is the half that never fits in the viewport shot.
  // Scrolled by heading text rather than an id — TrendsView mounts in BOTH layout
  // subtrees at every width, so any id it carried would trip the duplicate-id check.
  { name: 'trends', url: '/trends', shot: { name: 'merchants', to: 'main h2', text: /Merchants/ } },
  { name: 'cuts', url: '/cuts' },
  { name: 'fees', url: '/fees' },
  // #74: /settings was never audited, and it is where #40 shipped two real bugs —
  // a doubled mount duplicating every id, and the page invisible above 1024px.
  // `must` is what catches the second one: the desktop subtree renders <Dashboard/>
  // rather than children(), so a route that lands in the wrong branch does not go
  // blank — it silently shows the dashboard instead, and overflow/tiny-text/blank
  // checks all pass on that. Naming one element of the route's OWN content is the
  // only thing that tells the two apart.
  { name: 'settings', url: '/settings', must: '#setup-bank' },
];
const widths = [
  { tag: 'mobile', width: 390, height: 844 },
  { tag: 'tablet', width: 834, height: 1112 },
  { tag: 'desktop', width: 1440, height: 900 },
];

const waitReady = (page) =>
  page.waitForFunction(() => !document.querySelector('[data-loading]'), { timeout: 8000 });

// absent | hidden | ok — a display:none'd subtree measures 0x0, which is how the
// width-toggled halves of the shell are told apart from a missing element.
const shown = (page, sel) =>
  page.evaluate((s) => {
    const el = document.querySelector(s);
    if (!el) return 'absent';
    const rc = el.getBoundingClientRect();
    return rc.width > 0 && rc.height > 0 ? 'ok' : 'hidden';
  }, sel);

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
    // #86: the hrefs are `/#id`, not `#id`, so a click on a route without that section
    // navigates home instead of dying.
    const links = Array.from(document.querySelectorAll('header nav a[href^="/#"]'));
    const active = links.filter(a => a.getAttribute('aria-current') === 'page').map(a => a.getAttribute('href'));
    const overviewActive = document.querySelector('a[href="/#overview"]')?.getAttribute('aria-current') === 'page';
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
  page.on('console', (m) => {
    // `npm run preview` is a static file server with no API behind it, so /api/* 404s
    // here and only here. Narrowed to that prefix rather than dropped, because a console
    // error is exactly what this audit exists to catch.
    if (m.type() !== 'error') return;
    if (m.location()?.url?.includes('/api/')) return;
    issues.push(`[${vp.tag}] console: ${m.text()}`);
  });
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

    // A route rendered by BOTH layout subtrees duplicates every id, which silently
    // breaks every <label for=> on the page — the #40 bug, invisible to the eye.
    const dupes = await page.evaluate(() => {
      const seen = new Set(), out = new Set();
      for (const el of document.querySelectorAll('[id]'))
        (seen.has(el.id) ? out : seen).add(el.id);
      return [...out].slice(0, 6);
    });
    if (dupes.length) issues.push(`[${vp.tag}] ${r.name}: DUPLICATE IDS -> ${dupes.join(', ')}`);

    if (r.must) {
      const s = await shown(page, r.must);
      if (s !== 'ok') issues.push(`[${vp.tag}] ${r.name}: ${r.must} is ${s}`);
    }

    // #86: /settings rendered outside the shell for two releases, so it had no navigation
    // at any width — the third time this regresses, this is what catches it. Which nav is
    // expected depends on the width: BottomNav below 1024px, TopBar above it. The
    // BottomNav selector cannot be `nav a[href="/settings"]` alone at desktop, because
    // that element still exists there — it is display:none'd, hence the visibility check.
    const navSel = vp.width >= 1024 ? 'header nav a[href="/#overview"]' : 'nav a[href="/settings"]';
    const navShown = await shown(page, navSel);
    if (navShown !== 'ok') issues.push(`[${vp.tag}] ${r.name}: nav (${navSel}) is ${navShown}`);

    await page.screenshot({ path: `audit-shots/${vp.tag}-${r.name}.png`, fullPage: true });

    // #88: the README's five screenshots are these — sourced here so a UI change refreshes
    // them with one command instead of five hand captures at five different scales. Viewport
    // height, not fullPage: a phone frame, where the diagnostic shot above wants the whole
    // scroll. See README.md for the copy step into docs/img/ (audit-shots/ is gitignored).
    if (vp.tag === 'mobile') {
      await page.screenshot({ path: `audit-shots/readme-${r.name}.png` });
      if (r.shot) {
        // scrollIntoView, not scrollIntoViewIfNeeded — the latter no-ops here and leaves
        // the shot identical to the route's own. Scroll the whole card, not its heading,
        // so the frame starts at the card border rather than mid-way through the one above.
        await page
          .locator(r.shot.to, { hasText: r.shot.text })
          .first()
          .evaluate((e) => (e.closest('.border') ?? e).scrollIntoView({ block: 'start' }));
        await page.waitForTimeout(500); // the bars animate in on first view (use:inview)
        await page.screenshot({ path: `audit-shots/readme-${r.shot.name}.png` });
        await page.evaluate(() => window.scrollTo(0, 0));
      }
    }
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
