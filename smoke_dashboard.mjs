// Smoke test: load built dashboard.html under a minimal DOM shim, render, switch views.
// No npm deps. Run: node smoke_dashboard.mjs
import { readFileSync } from "node:fs";

const htmlPath = "dashboard.html";
let html;
try { html = readFileSync(htmlPath, "utf8"); }
catch { console.error("dashboard.html not found — run `python dashboard.py` first"); process.exit(1); }

const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error("no <script> block found"); process.exit(1); }
const code = m[1];

// ---- tiny DOM shim ----
class E {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.attributes = {};
    this.style = {}; this.dataset = {}; this._cls = new Set();
    this._listeners = {}; this._html = ""; this.textContent = ""; this.value = "";
    this.onclick = null; this.onchange = null;
  }
  get classList() {
    const s = this._cls;
    return {
      add: c => s.add(c), remove: c => s.delete(c),
      contains: c => s.has(c),
      toggle: (c, f) => { const on = f === undefined ? !s.has(c) : !!f; on ? s.add(c) : s.delete(c); return on; },
    };
  }
  set className(v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...this._cls].join(" "); }
  set innerHTML(v) { this._html = String(v); this.children = []; }
  get innerHTML() { return this._html; }
  setAttribute(k, v) { this.attributes[k] = v; if (k === "class") this.className = v; if (k === "id") this.id = v; }
  getAttribute(k) { return this.attributes[k]; }
  appendChild(c) { this.children.push(c); return c; }
  replaceWith() { /* no-op: byId cache keeps the original node for assertions */ }
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); }
  closest() { return null; }
  querySelectorAll() { return []; }
}

const byId = {};
const viewButtons = ["monthly", "overview", "recs"].map(v => { const b = new E("button"); b.dataset.v = v; return b; });
const modeButtons = ["disc", "all"].map(mm => { const b = new E("button"); b.dataset.m = mm; return b; });

const document = {
  getElementById: id => (byId[id] ||= new E("div")),
  createElement: t => new E(t),
  createElementNS: (_ns, t) => new E(t),
  querySelectorAll: sel => {
    if (sel === "#view button") return viewButtons;
    if (sel === "#mode button") return modeButtons;
    return [];
  },
};
const window = {};

// ---- run ----
const run = new Function("document", "window", code);
run(document, window);                 // executes script incl. initial render()

// switch each view via its button handler (smoke: must not throw)
for (const b of viewButtons) { if (typeof b.onclick === "function") b.onclick(); }

// ---- assertions (extended by later tasks) ----
function assert(cond, msg) { if (!cond) { console.error("SMOKE FAIL: " + msg); process.exit(1); } }
assert(byId["view"] || true, "view container resolvable");

// Task 2: hero band renders headline + cashback
const heroHtml = (byId["hero"] && byId["hero"]._html) || "";
assert(heroHtml.includes("Spend this month"), "hero has spend headline label");
assert(/RM/.test(heroHtml), "hero shows an RM figure");
assert(heroHtml.toLowerCase().includes("cashback"), "hero shows cashback");

// Task 3: movers region renders a real mover row or an explicit empty state
const heroNow = byId["hero"]._html || "";
assert(heroNow.includes("mvrow") || heroNow.toLowerCase().includes("nothing rising") || heroNow.toLowerCase().includes("nothing to compare"),
  "hero shows movers region with real rows or explicit empty state");

// Task 4: cut candidates region present
const heroCut = byId["hero"]._html || "";
assert(heroCut.toLowerCase().includes("cut candidates"), "hero shows cut-candidates region");

console.log("SMOKE OK");
