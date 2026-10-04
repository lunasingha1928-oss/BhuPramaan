"use strict";
/* Small dependency-free SVG charts (work offline). Every chart has hover tooltips and a table view. */

const SVGNS = "http://www.w3.org/2000/svg";
function sv(tag, attrs, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
  if (parent) parent.append(n);
  return n;
}

/* ---------- tooltip ---------- */
const Tip = (() => {
  let t = null;
  function node() { if (!t) { t = el("div"); t.id = "tip"; t.setAttribute("role", "tooltip"); document.body.append(t); } return t; }
  return {
    show(ev, title, lines) {
      const n = node(); n.textContent = "";
      n.append(el("b", "", title));
      for (const l of lines || []) { n.append(el("br")); n.append(document.createTextNode(l)); }
      n.style.display = "block";
      const x = Math.min(ev.clientX + 14, window.innerWidth - n.offsetWidth - 8);
      const y = Math.min(ev.clientY + 14, window.innerHeight - n.offsetHeight - 8);
      n.style.left = x + "px"; n.style.top = y + "px";
    },
    hide() { if (t) t.style.display = "none"; },
  };
})();

function onResize(fn) {
  let id = null;
  window.addEventListener("resize", () => { clearTimeout(id); id = setTimeout(fn, 120); });
}

function legend(items) {
  const lg = el("div", "legend");
  for (const it of items) {
    const s = el("span"); const i = el("i"); i.style.background = it.color;
    s.append(i, document.createTextNode(it.name)); lg.append(s);
  }
  return lg;
}

function tableView(container, headers, rows, title) {
  const d = el("details", "tableview");
  d.append(el("summary", "", title || "Show as table"));
  const t = el("table", "data");
  const tr = el("tr"); headers.forEach((h, i) => { const th = el("th", i ? "num" : "", h); tr.append(th); }); t.append(tr);
  for (const r of rows) { const row = el("tr"); r.forEach((c, i) => row.append(el("td", i ? "num" : "", c))); t.append(row); }
  d.append(t); container.append(d);
}

function barPath(x, y, w, h, r) {
  if (w <= 0) return "";
  r = Math.min(r, w, h / 2);
  return `M${x} ${y}h${w - r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - r)}Z`;
}

/* Grouped horizontal bars on a 0..max scale. */
function barsGrouped(container, cfg) {
  const { categories, series, max = 1, format = (v) => pct(v, 1), labelWidth = 170, note } = cfg;
  function draw() {
    container.textContent = "";
    if (series.length > 1) container.append(legend(series));
    const box = el("div", "chart"); container.append(box);
    const W = Math.max(container.clientWidth, 280);
    const bh = 12, gap = 2, block = series.length * bh + (series.length - 1) * gap, bgap = 16, axisH = 22;
    const lw = Math.min(labelWidth, W * 0.42), x0 = lw + 8, x1 = W - 52;
    const H = categories.length * block + (categories.length - 1) * bgap + axisH;
    const svg = sv("svg", { width: W, height: H, role: "img", "aria-label": cfg.title || "bar chart" }, box);
    const g = sv("g", { class: "grid" }, svg);
    const xs = (v) => x0 + (Math.max(0, v) / max) * (x1 - x0);
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      sv("line", { x1: xs(t * max), x2: xs(t * max), y1: 0, y2: H - axisH + 4 }, g);
      const tx = sv("text", { x: xs(t * max), y: H - 4, "text-anchor": "middle" }, svg); tx.textContent = format(t * max).replace(".0%", "%");
    }
    categories.forEach((cat, ci) => {
      const yb = ci * (block + bgap);
      const lab = sv("text", { x: lw, y: yb + block / 2 + 4, "text-anchor": "end", class: "cat" }, svg); lab.textContent = cat;
      series.forEach((s, si) => {
        const v = s.values[ci], y = yb + si * (bh + gap);
        if (v === null || v === undefined) return;
        sv("path", { d: barPath(x0, y, xs(v) - x0, bh, 4), fill: s.color }, svg);
        const t = sv("text", { x: xs(v) + 6, y: y + bh - 2, "font-size": 11 }, svg); t.textContent = format(v);
        const hit = sv("rect", { x: x0, y: y - 1, width: x1 - x0 + 50, height: bh + 2, fill: "transparent" }, svg);
        hit.addEventListener("mousemove", (e) => Tip.show(e, cat, [`${s.name}: ${format(v)}`]));
        hit.addEventListener("mouseleave", Tip.hide);
      });
    });
    if (note) container.append(el("div", "card-foot", note));
    tableView(container, ["", ...series.map((s) => s.name)], categories.map((c, i) => [c, ...series.map((s) => format(s.values[i]))]));
  }
  draw(); onResize(draw);
}

/* One 100% stacked bar with direct labels underneath. */
function stack100(container, segments) {
  function draw() {
    container.textContent = "";
    const total = segments.reduce((a, s) => a + s.value, 0) || 1;
    const W = Math.max(container.clientWidth, 280), H = 28, gap = 2;
    const box = el("div", "chart"); container.append(box);
    const svg = sv("svg", { width: W, height: H, role: "img", "aria-label": "Parcel status breakdown" }, box);
    let x = 0;
    const live = segments.filter((s) => s.value > 0);
    live.forEach((s, i) => {
      const w = (s.value / total) * (W - gap * (live.length - 1));
      const r = sv("rect", { x, y: 0, width: Math.max(w, 1), height: H, rx: 4, fill: s.color }, svg);
      r.addEventListener("mousemove", (e) => Tip.show(e, s.label, [`${fmtInt(s.value)} parcels · ${pct(s.value / total)}`]));
      r.addEventListener("mouseleave", Tip.hide);
      x += w + gap;
    });
    const labels = el("div", "legend"); labels.style.marginTop = "10px"; labels.style.gap = "22px";
    for (const s of segments) {
      const sp = el("span"); const i = el("i"); i.style.background = s.color;
      const b = el("b", "", pct(s.value / total)); b.style.color = "var(--ink)";
      sp.append(i, b, document.createTextNode(` ${s.label} (${fmtInt(s.value)})`)); labels.append(sp);
    }
    container.append(labels);
  }
  draw(); onResize(draw);
}

/* Reliability diagram: predicted probability vs observed frequency, per bin. */
function reliability(container, bins) {
  function draw() {
    container.textContent = "";
    const box = el("div", "chart"); container.append(box);
    const W = Math.min(Math.max(container.clientWidth, 260), 520), H = 280, m = { l: 58, r: 12, t: 10, b: 38 };
    const svg = sv("svg", { width: W, height: H, role: "img", "aria-label": "Calibration: predicted vs observed" }, box);
    const xs = (v) => m.l + v * (W - m.l - m.r), ys = (v) => H - m.b - v * (H - m.t - m.b);
    const g = sv("g", { class: "grid" }, svg);
    for (const t of [0, 0.25, 0.5, 0.75, 1]) {
      sv("line", { x1: xs(0), x2: xs(1), y1: ys(t), y2: ys(t) }, g);
      const a = sv("text", { x: m.l - 6, y: ys(t) + 4, "text-anchor": "end" }, svg); a.textContent = pct(t, 0);
      const b = sv("text", { x: xs(t), y: H - m.b + 16, "text-anchor": "middle" }, svg); b.textContent = pct(t, 0);
    }
    const xl = sv("text", { x: xs(0.5), y: H - 4, "text-anchor": "middle" }, svg); xl.textContent = "Model's predicted probability";
    const yl = sv("text", { x: 12, y: ys(0.5), transform: `rotate(-90 12 ${ys(0.5)})`, "text-anchor": "middle" }, svg); yl.textContent = "Actually a link";
    sv("line", { x1: xs(0), y1: ys(0), x2: xs(1), y2: ys(1), stroke: "#9a988f", "stroke-dasharray": "4 4", "stroke-width": 1.5 }, svg);
    const pts = bins.map((b) => [xs(b.mean_pred), ys(b.observed)]);
    bins.forEach((b, i) => {
      const few = b.n < 30;
      sv("circle", { cx: pts[i][0], cy: pts[i][1], r: 5, fill: few ? "#ffffff" : "var(--series-model)",
                     stroke: few ? "var(--series-model)" : "#ffffff", "stroke-width": 2 }, svg);
      const hit = sv("circle", { cx: pts[i][0], cy: pts[i][1], r: 12, fill: "transparent" }, svg);
      hit.addEventListener("mousemove", (e) => Tip.show(e, `Predicted ${pct(b.lo, 0)}–${pct(b.hi, 0)}`,
        [`${fmtInt(b.n)} candidate pairs`, `mean prediction ${pct(b.mean_pred)}`, `actually links ${pct(b.observed)}`]));
      hit.addEventListener("mouseleave", Tip.hide);
    });
    const lg = legend([{ name: "Model (filled: 30+ pairs, hollow: fewer)", color: "var(--series-model)" }, { name: "Perfect calibration (dashed)", color: "#9a988f" }]);
    container.prepend(lg);
    tableView(container, ["Predicted bin", "Pairs", "Mean predicted", "Observed"],
      bins.map((b) => [`${pct(b.lo, 0)}–${pct(b.hi, 0)}`, fmtInt(b.n), pct(b.mean_pred), pct(b.observed)]));
  }
  draw(); onResize(draw);
}

/* Static overview map of the cadastral layer, coloured by status. */
function minimap(svgEl, fc, onClick) {
  function draw() {
    svgEl.textContent = "";
    const W = svgEl.clientWidth || 600, H = svgEl.clientHeight || 300, pad = 10;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const rings = (g) => (g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : []);
    for (const f of fc.features) for (const poly of rings(f.geometry)) for (const [x, y] of poly[0]) {
      if (x < minX) minX = x; if (x > maxX) maxX = x; if (y < minY) minY = y; if (y > maxY) maxY = y;
    }
    const k = Math.cos(((minY + maxY) / 2) * Math.PI / 180);
    const s = Math.min((W - 2 * pad) / ((maxX - minX) * k), (H - 2 * pad) / (maxY - minY));
    const ox = (W - (maxX - minX) * k * s) / 2, oy = (H - (maxY - minY) * s) / 2;
    const P = ([x, y]) => `${(ox + (x - minX) * k * s).toFixed(1)},${(oy + (maxY - y) * s).toFixed(1)}`;
    svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const order = ["auto", "unmatched", "review"];   // review drawn last so it stays visible
    for (const st of order) {
      let d = "";
      for (const f of fc.features) if (f.properties.status === st)
        for (const poly of rings(f.geometry)) d += "M" + poly[0].map(P).join("L") + "Z";
      sv("path", { d, fill: STATUS[st].color, "fill-opacity": st === "auto" ? 0.55 : 0.9, stroke: STATUS[st].stroke, "stroke-width": st === "review" ? 1.2 : 0.4 }, svgEl);
    }
  }
  draw(); onResize(draw);
  if (onClick) svgEl.addEventListener("click", onClick);
}
