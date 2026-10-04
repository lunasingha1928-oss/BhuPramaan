"use strict";
/* Helpers shared by every page. Loaded as a classic script before each page's own code. */

const $ = (id) => document.getElementById(id);
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
const pct = (x, d = 1) => (x * 100).toFixed(d) + "%";
const key = (a, b) => a + "|" + b;
const fmtInt = (n) => Number(n).toLocaleString("en-IN");

/* Version tag added to page links, so a browser never reuses a page cached by an older release. */
const UI_VERSION = "9";
function pageUrl(p) {
  const [path, hash] = p.split("#");
  return path + "?v=" + UI_VERSION + (hash ? "#" + hash : "");
}

function toLogin() {
  if (!/login\.html$/.test(location.pathname)) location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop() + location.hash);
}
async function j(url, opts) {
  const r = await fetch(url, opts);
  if (r.status === 401 && url !== "/api/login") { toLogin(); throw new Error("Please sign in."); }
  let body = null;
  try { body = await r.json(); } catch (e) { /* not json */ }
  if (!r.ok) {
    const d = body && body.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || `${url} returned ${r.status}`);
  }
  return body;
}

const STATUS = {
  auto: { label: "Auto-resolved", color: "#0ca30c", stroke: "#0a7d0a" },
  review: { label: "Needs review", color: "#fab219", stroke: "#b07a00" },
  unmatched: { label: "No counterpart", color: "#9a988f", stroke: "#6f6d66" },
};

const LABELS = {
  iou: "Overlap of the two outlines", inter_over_a: "Share of cadastral parcel covered", inter_over_b: "Share of revenue parcel covered",
  centroid_dist: "Distance between centres", area_ratio: "Similarity of areas", hausdorff_norm: "Shape / position difference",
  rank_a: "Closest-candidate rank (cadastral side)", rank_b: "Closest-candidate rank (revenue side)",
  n_cand_a: "Competing candidates (cadastral side)", n_cand_b: "Competing candidates (revenue side)",
  gap_a: "Gap to the nearest competitor (cadastral)", gap_b: "Gap to the nearest competitor (revenue)",
};

const ERROR_LABELS = { clean: "Survey jitter only", offset: "Shifted position", scale: "Area mismatch", rotate: "Rotated",
                       split: "Split into two", merge: "Two merged into one" };

const PAGES = [
  ["admin.html", "Administration"], ["index.html", "Dashboard"], ["review.html", "Review queue"],
  ["map.html", "Map explorer"], ["quality.html", "Data quality"], ["changes.html", "Changes"], ["real.html", "Real data"], ["upload.html", "Match your data"],
  ["audit.html", "Audit log"], ["method.html", "Methodology"],
];
const CHANGE = {
  new: { label: "New building", color: "#2a78d6" },
  demolished: { label: "Demolished", color: "#eb6834" },
  altered: { label: "Altered / extended", color: "#1baf7a" },
};

/* Signs the page in: sends visitors to the login page, sends users away from pages their role can't use,
   then draws the top bar for that role. Resolves to the signed-in user. */
async function renderNav(active) {
  let me;
  try { me = await j("/api/me"); } catch (e) { return new Promise(() => {}); }   // redirected to login
  if (!me.pages.includes(active)) { location.replace(pageUrl(me.home)); return new Promise(() => {}); }
  const h = $("topbar");
  h.textContent = "";
  const brand = el("div", "brand");
  brand.append(el("b", "", "Parcel Reconciliation Console"), el("span", "", "Cadastral ↔ revenue layers · SIH26013"));
  const nav = el("nav", "pages");
  nav.setAttribute("aria-label", "Pages");
  for (const [href, name] of PAGES.filter(([p]) => me.pages.includes(p)).sort((x, y) => me.pages.indexOf(x[0]) - me.pages.indexOf(y[0]))) {
    const a = el("a", "", name);
    a.href = pageUrl(href);
    a.dataset.page = href;
    if (href === active) a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  const right = el("div");
  right.id = "topbar-right";
  const who = el("div", "who");
  who.append(el("b", "", me.name), el("span", `role-chip role-${me.role}`, me.role_label));
  const out = el("button", "btn", "Sign out");
  out.addEventListener("click", async () => { await fetch("/api/logout", { method: "POST" }); location.href = pageUrl("login.html"); });
  right.append(typeof langPicker === "function" ? langPicker(true) : "", who, out);
  h.append(brand, nav, right);
  // pending-review badge on the Review link
  if (me.pages.includes("review.html")) Promise.all([j("/api/pairs?bucket=review"), j("/api/decisions")]).then(([rev, log]) => {
    const decided = new Set(log.map((d) => key(d.a_id, d.b_id)));
    const n = rev.filter((p) => !decided.has(key(p.a, p.b))).length;
    const link = nav.querySelector('[data-page="review.html"]');
    if (n && link) link.append(el("span", "count", String(n)));
  }).catch(() => {});
  return me;
}

/* Latest decision per link from the append-only log. */
function latestDecisions(log) {
  const m = new Map();
  for (const d of log) m.set(key(d.a_id, d.b_id), d);
  return m;
}

function download(filename, text, type) {
  const blob = new Blob([text], { type: type || "text/plain" });
  const a = el("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

function fatal(container, err) {
  container.textContent = "";
  container.append(el("div", "empty", "Could not load data. Run scripts/build_demo.py, then scripts/serve.py. (" + err.message + ")"));
}


/* Which dataset a page shows: ?data=real|synthetic in the URL wins, then the last choice, then synthetic. */
function dataset() {
  const q = new URLSearchParams(location.search).get("data");
  if (q === "real" || q === "synthetic") { try { localStorage.setItem("dataset", q); } catch (e) { /* blocked */ } return q; }
  try { return localStorage.getItem("dataset") === "real" ? "real" : "synthetic"; } catch (e) { return "synthetic"; }
}
function datasetSwitch(box, current) {
  if (!box) return;
  box.textContent = "";
  for (const [v, label] of [["synthetic", "Synthetic test"], ["real", "Real: OSM ↔ Microsoft"]]) {
    const b = el("button", "", label); b.type = "button"; b.setAttribute("aria-pressed", String(v === current));
    b.addEventListener("click", () => { if (v === current) return; const u = new URL(location.href); u.searchParams.set("data", v); u.hash = ""; location.href = u.toString(); });
    box.append(b);
  }
}
