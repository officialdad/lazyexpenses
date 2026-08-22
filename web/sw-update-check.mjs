// #67: the service-worker update reloader wired in src/app.html. Playwright, run
// after `npm run build`, from web/ — it serves build/ itself, no preview needed.
//   node sw-update-check.mjs
// Proves the loop guard (a first install must not prompt or reload) and that a real
// deploy prompts instead of reloading. Mutation-checked: dropping the guard fails it.
//
// It serves build/ itself because `vite preview` holds sw.js in memory — an on-disk
// edit is invisible to reg.update() there, so no update can ever be simulated.
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const root = 'build';
const MIME = {
	'.js': 'text/javascript',
	'.css': 'text/css',
	'.json': 'application/json',
	'.png': 'image/png',
	'.svg': 'image/svg+xml',
	'.html': 'text/html',
	'.webmanifest': 'application/manifest+json',
	'.txt': 'text/plain'
};
const srv = http
	.createServer((req, res) => {
		let f = path.join(root, decodeURIComponent(req.url.split('?')[0]));
		if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) {
			const idx = path.join(f, 'index.html');
			f = fs.existsSync(idx) ? idx : path.join(root, 'index.html');
		}
		res.writeHead(200, {
			'content-type': MIME[path.extname(f)] || 'application/octet-stream',
			'cache-control': 'no-store'
		});
		fs.createReadStream(f).pipe(res);
	})
	.listen(4184);

const SW = 'build/sw.js';
const base = 'http://localhost:4184';
const orig = fs.readFileSync(SW, 'utf8');
const deploy = (tag) => fs.writeFileSync(SW, orig + '\n// ' + tag + ' ' + Date.now() + '\n');

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
// Counts real document loads: a fresh document re-runs this, a SvelteKit
// same-document replaceState does not.
await ctx.addInitScript(() => {
	sessionStorage.loads = String(Number(sessionStorage.loads || 0) + 1);
});
const page = await ctx.newPage();
page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
const loads = () => page.evaluate(() => Number(sessionStorage.loads));
const banner = () => page.evaluate(() => !!document.getElementById('sw-update'));
const update = () =>
	page.evaluate(() => navigator.serviceWorker.getRegistration().then((r) => r.update()));

let fails = 0;
const ok = (cond, msg) => {
	if (!cond) {
		fails++;
		console.log('   FAIL: ' + msg);
	}
};

try {
	// 1. First-ever install. clientsClaim fires controllerchange with no previous
	//    controller — must not banner and must not reload.
	await page.goto(base + '/', { waitUntil: 'load' });
	await page.waitForFunction(() => !!navigator.serviceWorker.controller, { timeout: 20000 });
	await page.waitForTimeout(3000);
	console.log(
		'1. first install (no previous controller) -> controlled=%s banner=%s documentLoads=%d',
		await page.evaluate(() => !!navigator.serviceWorker.controller),
		await banner(),
		await loads()
	);
	ok(await page.evaluate(() => !!navigator.serviceWorker.controller), 'SW never took control');
	ok((await banner()) === false, 'bannered on first install');
	ok((await loads()) === 1, 'reloaded on first install — loop guard broken');

	// 2. A deploy in that same never-reloaded document. The promoted flag means this
	//    still prompts, and must NOT reload by itself.
	deploy('v2');
	await update();
	await page.waitForSelector('#sw-update', { timeout: 20000 });
	const a11y = await page.evaluate(() => {
		const d = document.getElementById('sw-update'),
			btn = d.querySelector('button');
		btn.focus();
		return {
			role: d.getAttribute('role'),
			text: d.textContent,
			tag: btn.tagName,
			spanFont: getComputedStyle(d.querySelector('span')).fontSize,
			btnFont: getComputedStyle(btn).fontSize,
			focused: document.activeElement === btn
		};
	});
	console.log('2. deploy v2 -> banner shown, documentLoads=%d (no auto-reload)', await loads());
	console.log(
		'   role=%s text=%j control=%s fonts=%s/%s keyboard-focusable=%s',
		a11y.role,
		a11y.text,
		a11y.tag,
		a11y.spanFont,
		a11y.btnFont,
		a11y.focused
	);
	ok((await loads()) === 1, 'auto-reloaded instead of prompting');
	ok(a11y.focused === true, 'banner button is not keyboard-focusable');
	ok(a11y.role === 'status', 'banner is not an aria live region');
	ok(parseFloat(a11y.spanFont) >= 11 && parseFloat(a11y.btnFont) >= 11, 'sub-11px text');

	// 3. Enter on the focused button reloads, and the banner is gone afterwards.
	await page.keyboard.press('Enter');
	await page.waitForLoadState('load');
	await page.waitForTimeout(2000);
	console.log('3. Enter on the button -> documentLoads=%d banner=%s', await loads(), await banner());
	ok((await loads()) === 2, 'Enter did not reload');
	ok((await banner()) === false, 'banner survived the reload');

	// 4. The reloaded document IS controlled at load. A further deploy must prompt
	//    again, and the reload itself must not have re-prompted (no loop).
	deploy('v3');
	await update();
	await page.waitForSelector('#sw-update', { timeout: 20000 });
	console.log('4. deploy v3 on a controlled document -> banner=%s documentLoads=%d', await banner(), await loads());
	ok((await loads()) === 2, 'auto-reloaded on the second update');
} finally {
	fs.writeFileSync(SW, orig);
	await b.close();
	srv.close();
}
console.log(fails ? 'SW67 CHECK FAILED (' + fails + ')' : 'SW67 CHECK OK');
process.exit(fails ? 1 : 0);
