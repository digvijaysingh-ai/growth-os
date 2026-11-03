// Growth OS console: chart kit (plain SVG, CSP-safe, no libraries) and the enterprise dashboard.
// Colour: categorical slots in fixed order, one sequential hue, one diverging pair with a grey midpoint,
// status colours only for state. Every mark has a hover tooltip; every chart has a legend or a title naming it.

var VZ = { tipEl: null };
function vzTip() {
  if (!VZ.tipEl) {
    VZ.tipEl = document.createElement("div");
    VZ.tipEl.className = "vz-tip";
    VZ.tipEl.setAttribute("role", "tooltip");
    document.body.appendChild(VZ.tipEl);
    document.addEventListener("pointermove", function (e) {
      var t = e.target.closest ? e.target.closest("[data-tip]") : null;
      if (!t) { VZ.tipEl.style.opacity = 0; return; }
      VZ.tipEl.replaceChildren(vzSafe(t.getAttribute("data-tip")));
      var x = e.clientX + 14, y = e.clientY + 14, w = VZ.tipEl.offsetWidth, h = VZ.tipEl.offsetHeight;
      if (x + w > innerWidth - 8) x = e.clientX - w - 14;
      if (y + h > innerHeight - 8) y = e.clientY - h - 14;
      VZ.tipEl.style.transform = "translate(" + x + "px," + y + "px)";
      VZ.tipEl.style.opacity = 1;
    });
  }
}
// Tooltip markup is parsed in an inert <template> (nothing runs) and rebuilt from a short list of tags with no
// attributes except a colour swatch, so a string that slipped into a tip unescaped renders as text, never as code.
var VZ_TAGS = { B: 1, DIV: 1, I: 1, BR: 1, SPAN: 1 };
function vzSafe(markup) {
  var tpl = document.createElement("template"), out = document.createDocumentFragment();
  tpl.innerHTML = markup || "";
  (function copy(from, to) {
    from.childNodes.forEach(function (n) {
      if (n.nodeType === 3) { to.appendChild(document.createTextNode(n.nodeValue)); return; }
      if (n.nodeType !== 1) return;
      if (!VZ_TAGS[n.tagName]) { to.appendChild(document.createTextNode(n.textContent)); return; }
      var el = document.createElement(n.tagName.toLowerCase()), bg = n.style && n.style.background;
      if (n.tagName === "I" && bg && /^(var\(--[a-z0-9-]+\)|#[0-9a-f]{3,8}|rgba?\([0-9., ]+\))$/i.test(bg)) el.style.background = bg;
      copy(n, el);
      to.appendChild(el);
    });
  })(tpl.content, out);
  return out;
}
function S(i) { return "var(--s" + ((i % 8) + 1) + ")"; }
function eurS(v) {
  if (v == null || isNaN(v)) return "–";
  var a = Math.abs(v), s = v < 0 ? "−" : "";
  return s + "€" + (a >= 1e6 ? (a / 1e6).toFixed(a >= 1e7 ? 1 : 2) + "M" : a >= 1e3 ? Math.round(a / 1e3) + "k" : Math.round(a));
}
function sgn(v, f) { return (v > 0 ? "+" : v < 0 ? "−" : "±") + f(Math.abs(v)); }
function pctS(v, d) { return v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(d == null ? 1 : d) + "%"; }
function nice(max) { var p = Math.pow(10, Math.floor(Math.log10(max || 1))), n = max / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; }
function shortN(v) { var a = Math.abs(v); return a >= 1e6 ? (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : a >= 1e3 ? Math.round(v / 1e3) + "k" : (Math.round(v * 100) / 100).toString(); }
function axisY(y, P, W, ticks, f) { return ticks.map(function (t) { return '<line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + y(t) + '" y2="' + y(t) + '" class="vz-grid"/><text x="' + (P.l - 6) + '" y="' + (y(t) + 4) + '" text-anchor="end" class="vz-ax">' + f(t) + "</text>"; }).join(""); }

// Line / area chart with a crosshair: series = [{key, label, color, area?, dash?}]
function vzLine(id, rows, xKey, series, o) {
  o = o || {};
  var W = o.w || 640, H = o.h || 220, P = { l: 52, r: 14, t: 12, b: 26 };
  var vals = []; rows.forEach(function (r) { series.forEach(function (s) { if (r[s.key] != null) vals.push(r[s.key]); }); });
  if (o.target != null) vals.push(o.target);
  var lo = o.zero === false ? Math.min.apply(null, vals) : Math.min(0, Math.min.apply(null, vals)), hi = nice(Math.max.apply(null, vals));
  if (o.zero === false) { var pad = (hi - lo) * 0.08; lo = lo - pad; }
  var x = function (i) { return P.l + i * (W - P.l - P.r) / Math.max(1, rows.length - 1); }, y = function (v) { return H - P.b - (v - lo) / (hi - lo) * (H - P.t - P.b); };
  var ticks = [lo, lo + (hi - lo) / 2, hi], f = o.fmt || shortN;
  var g = axisY(y, P, W, ticks, f);
  if (o.target != null) g += '<line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + y(o.target) + '" y2="' + y(o.target) + '" class="vz-target"/><text x="' + (W - P.r) + '" y="' + (y(o.target) - 5) + '" text-anchor="end" class="vz-ax">target ' + f(o.target) + "</text>";
  if (o.marker != null) { var mi = rows.findIndex(function (r) { return r[xKey] >= o.marker; }); if (mi >= 0) g += '<line x1="' + x(mi) + '" x2="' + x(mi) + '" y1="' + P.t + '" y2="' + (H - P.b) + '" class="vz-target"/><text x="' + (x(mi) + 4) + '" y="' + (P.t + 10) + '" class="vz-ax">' + esc(o.markerLabel || "") + "</text>"; }
  series.forEach(function (s) {
    var pts = rows.map(function (r, i) { return r[s.key] == null ? null : [x(i), y(r[s.key])]; }).filter(Boolean);
    if (s.area) g += '<path d="M' + pts[0][0] + "," + y(Math.max(lo, 0)) + " L" + pts.map(function (p) { return p.join(","); }).join(" L") + " L" + pts[pts.length - 1][0] + "," + y(Math.max(lo, 0)) + ' Z" fill="' + s.color + '" opacity=".14"/>';
    g += '<polyline fill="none" stroke="' + s.color + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"' + (s.dash ? ' stroke-dasharray="5 4"' : "") + ' points="' + pts.map(function (p) { return p.join(","); }).join(" ") + '"/>';
  });
  var step = Math.max(1, Math.ceil(rows.length / 6));
  rows.forEach(function (r, i) { if (i % step === 0) g += '<text x="' + x(i) + '" y="' + (H - 7) + '" text-anchor="middle" class="vz-ax">' + esc(String(r[xKey]).slice(2, 10)) + "</text>"; });
  // hover bands: one per x, with the crosshair readout
  var bw = (W - P.l - P.r) / Math.max(1, rows.length - 1);
  rows.forEach(function (r, i) {
    var tip = "<b>" + esc(r[xKey]) + "</b>" + series.map(function (s) { return '<div><i style="background:' + s.color + '"></i>' + esc(s.label) + ": <b>" + (r[s.key] == null ? "–" : f(r[s.key])) + "</b></div>"; }).join("");
    g += '<rect class="vz-hit" x="' + (x(i) - bw / 2) + '" y="' + P.t + '" width="' + bw + '" height="' + (H - P.t - P.b) + '" data-tip="' + esc(tip) + '"/>';
  });
  var legend = series.length > 1 ? '<div class="vz-legend">' + series.map(function (s) { return '<span><i style="background:' + s.color + (s.dash ? ';opacity:.6' : "") + '"></i>' + esc(s.label) + "</span>"; }).join("") + "</div>" : "";
  return legend + '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="' + esc(o.label || series.map(function (s) { return s.label; }).join(", ")) + '">' + g + "</svg>";
}

// Stacked area (shares of a whole over time)
function vzStack(rows, xKey, keys, o) {
  o = o || {};
  var W = o.w || 640, H = o.h || 220, P = { l: 52, r: 14, t: 12, b: 26 };
  var tot = rows.map(function (r) { return keys.reduce(function (a, k) { return a + (r[k.key] || 0); }, 0); });
  var hi = nice(Math.max.apply(null, tot));
  var x = function (i) { return P.l + i * (W - P.l - P.r) / Math.max(1, rows.length - 1); }, y = function (v) { return H - P.b - v / hi * (H - P.t - P.b); };
  var g = axisY(y, P, W, [0, hi / 2, hi], o.fmt || shortN), base = rows.map(function () { return 0; });
  keys.forEach(function (k) {
    var top = rows.map(function (r, i) { return base[i] + (r[k.key] || 0); });
    var d = "M" + rows.map(function (r, i) { return x(i) + "," + y(top[i]); }).join(" L") + " L" + rows.map(function (r, i) { return x(rows.length - 1 - i) + "," + y(base[rows.length - 1 - i]); }).join(" L") + " Z";
    g += '<path d="' + d + '" fill="' + k.color + '" opacity=".85" stroke="var(--surface)" stroke-width="1"/>';
    base = top;
  });
  var step = Math.max(1, Math.ceil(rows.length / 6));
  rows.forEach(function (r, i) { if (i % step === 0) g += '<text x="' + x(i) + '" y="' + (H - 7) + '" text-anchor="middle" class="vz-ax">' + esc(String(r[xKey]).slice(2, 10)) + "</text>"; });
  var bw = (W - P.l - P.r) / Math.max(1, rows.length - 1);
  rows.forEach(function (r, i) {
    var t = tot[i] || 1, tip = "<b>" + esc(r[xKey]) + "</b>" + keys.map(function (k) { return '<div><i style="background:' + k.color + '"></i>' + esc(k.label) + ": <b>" + (o.fmt || shortN)(r[k.key] || 0) + "</b> (" + Math.round(100 * (r[k.key] || 0) / t) + "%)</div>"; }).join("");
    g += '<rect class="vz-hit" x="' + (x(i) - bw / 2) + '" y="' + P.t + '" width="' + bw + '" height="' + (H - P.t - P.b) + '" data-tip="' + esc(tip) + '"/>';
  });
  return '<div class="vz-legend">' + keys.map(function (k) { return '<span><i style="background:' + k.color + '"></i>' + esc(k.label) + "</span>"; }).join("") + "</div>" +
    '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="' + esc(o.label || "stacked area") + '">' + g + "</svg>";
}

// Horizontal bars, signed: items = [{label, value, tip?, color?}]
function vzBars(items, o) {
  o = o || {};
  var W = o.w || 560, rowH = o.rowH || 26, P = { l: o.labelW || 190, r: 64, t: 6, b: 6 }, H = P.t + P.b + items.length * rowH;
  var mx = Math.max.apply(null, items.map(function (d) { return Math.abs(d.value); }).concat([1])), neg = items.some(function (d) { return d.value < 0; });
  var z = neg ? P.l + (W - P.l - P.r) / 2 : P.l, sc = (neg ? (W - P.l - P.r) / 2 : (W - P.l - P.r)) / mx, f = o.fmt || shortN, g = "";
  items.forEach(function (d, i) {
    var y = P.t + i * rowH, w = Math.max(1, Math.abs(d.value) * sc), x0 = d.value >= 0 ? z : z - w, col = d.color || (d.value >= 0 ? (o.pos || "var(--s1)") : (o.neg || "var(--s8)"));
    g += '<text x="' + (P.l - 8) + '" y="' + (y + rowH / 2 + 4) + '" text-anchor="end" class="vz-lab">' + esc(d.label) + "</text>";
    g += '<rect x="' + x0 + '" y="' + (y + 5) + '" width="' + w + '" height="' + (rowH - 10) + '" rx="4" fill="' + col + '"/>';
    g += '<text x="' + (d.value >= 0 ? x0 + w + 6 : x0 - 6) + '" y="' + (y + rowH / 2 + 4) + '" text-anchor="' + (d.value >= 0 ? "start" : "end") + '" class="vz-val">' + f(d.value) + "</text>";
    g += '<rect class="vz-hit" x="0" y="' + y + '" width="' + W + '" height="' + rowH + '" data-tip="' + esc(d.tip || ("<b>" + esc(d.label) + "</b><div>" + f(d.value) + "</div>")) + '"/>';
  });
  if (neg) g += '<line x1="' + z + '" x2="' + z + '" y1="' + P.t + '" y2="' + (H - P.b) + '" class="vz-zero"/>';
  return '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="' + esc(o.label || "bar chart") + '">' + g + "</svg>";
}

// Waterfall: start -> steps -> adjustment -> end (only the change is drawn, from a common baseline)
function vzWaterfall(w) {
  var items = w.steps.concat(w.combined_adjustment ? [{ label: "combined effects", value: w.combined_adjustment, adj: true }] : []);
  var W = 640, H = 260, P = { l: 56, r: 12, t: 16, b: 70 }, run = 0, pts = [];
  items.forEach(function (d) { pts.push([run, run + d.value]); run += d.value; });
  var all = [0, run].concat(pts.reduce(function (a, p) { return a.concat(p); }, [])), lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
  hi = nice(hi); lo = lo < 0 ? -nice(-lo) : 0;
  var n = items.length + 1, bw = (W - P.l - P.r) / n, y = function (v) { return H - P.b - (v - lo) / (hi - lo) * (H - P.t - P.b); };
  var g = axisY(y, P, W, [lo, (lo + hi) / 2, hi].filter(function (v, i, a) { return a.indexOf(v) === i; }), eurS);
  items.forEach(function (d, i) {
    var a = pts[i][0], b = pts[i][1], x = P.l + i * bw + 4, top = y(Math.max(a, b)), h = Math.max(1.5, Math.abs(y(a) - y(b)));
    var col = d.adj ? "var(--muted-fill)" : d.value >= 0 ? "var(--s3)" : "var(--s8)";
    g += '<rect x="' + x + '" y="' + top + '" width="' + (bw - 8) + '" height="' + h + '" rx="3" fill="' + col + '" data-tip="' + esc("<b>" + esc(d.label) + "</b><div>gross profit " + sgn(d.value, eurS) + "</div>" + (d.adj ? "<div>overlap between decisions and guardrail deferrals when all run together</div>" : "<div>this decision alone, simulated quarter</div>")) + '"/>';
    if (i < items.length - 1) g += '<line x1="' + (x + bw - 8) + '" x2="' + (x + bw + 4) + '" y1="' + y(b) + '" y2="' + y(b) + '" class="vz-grid"/>';
    g += '<text transform="translate(' + (x + (bw - 8) / 2) + "," + (H - P.b + 10) + ') rotate(-40)" text-anchor="end" class="vz-ax">' + esc(d.label) + "</text>";
  });
  var xe = P.l + items.length * bw + 4;
  g += '<rect x="' + xe + '" y="' + y(Math.max(0, run)) + '" width="' + (bw - 8) + '" height="' + Math.max(1.5, Math.abs(y(0) - y(run))) + '" rx="3" fill="var(--s1)" data-tip="' + esc("<b>All decisions together</b><div>gross profit " + sgn(run, eurS) + " this quarter</div>") + '"/>';
  g += '<text transform="translate(' + (xe + (bw - 8) / 2) + "," + (H - P.b + 10) + ') rotate(-40)" text-anchor="end" class="vz-ax">all together</text>';
  g += '<line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + y(0) + '" y2="' + y(0) + '" class="vz-zero"/>';
  return '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="Gross profit change by decision">' + g + "</svg>";
}

// Range + dot + tick: value vs peers' range and last year
function vzDotRange(rows, o) {
  o = o || {};
  var W = 560, rowH = 24, P = { l: 110, r: 70, t: 22, b: 8 }, H = P.t + P.b + rows.length * rowH, f = o.fmt || function (v) { return v == null ? "–" : v.toFixed(1); };
  var vals = []; rows.forEach(function (r) { [r.value, r.same_period_last_year].concat(r.peer_range || []).forEach(function (v) { if (v != null) vals.push(v); }); });
  var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * .06 || 1; lo -= pad; hi += pad;
  var x = function (v) { return P.l + (v - lo) / (hi - lo) * (W - P.l - P.r); }, g = "";
  g += '<text x="' + P.l + '" y="12" class="vz-ax">' + f(lo) + '</text><text x="' + (W - P.r) + '" y="12" text-anchor="end" class="vz-ax">' + f(hi) + "</text>";
  rows.forEach(function (r, i) {
    var y = P.t + i * rowH + rowH / 2, bad = r.outside_peer_range;
    g += '<text x="' + (P.l - 8) + '" y="' + (y + 4) + '" text-anchor="end" class="vz-lab">' + esc(r.market) + "</text>";
    if (r.peer_range) g += '<rect x="' + x(r.peer_range[0]) + '" y="' + (y - 5) + '" width="' + Math.max(2, x(r.peer_range[1]) - x(r.peer_range[0])) + '" height="10" rx="5" class="vz-band"/>';
    if (r.same_period_last_year != null) g += '<line x1="' + x(r.same_period_last_year) + '" x2="' + x(r.same_period_last_year) + '" y1="' + (y - 8) + '" y2="' + (y + 8) + '" stroke="var(--text-2)" stroke-width="2"/>';
    if (r.value != null) g += '<circle cx="' + x(r.value) + '" cy="' + y + '" r="5.5" fill="' + (bad ? "var(--critical)" : "var(--s1)") + '" stroke="var(--surface)" stroke-width="2"/>';
    g += '<text x="' + (W - P.r + 8) + '" y="' + (y + 4) + '" class="vz-val">' + f(r.value) + (bad ? " ⚠" : "") + "</text>";
    g += '<rect class="vz-hit" x="0" y="' + (y - rowH / 2) + '" width="' + W + '" height="' + rowH + '" data-tip="' + esc("<b>" + esc(r.market) + "</b><div>now: <b>" + f(r.value) + "</b></div><div>same weeks last year: " + f(r.same_period_last_year) + "</div><div>peers: " + (r.peer_range ? f(r.peer_range[0]) + "–" + f(r.peer_range[1]) : "–") + "</div>" + (bad ? "<div>⚠ outside the peers' range</div>" : "")) + '"/>';
  });
  return '<div class="vz-legend"><span><i style="background:var(--s1)"></i>last 28 days</span><span><i class="tick"></i>same weeks last year</span><span><i class="band"></i>peer markets\' range</span><span><i style="background:var(--critical)"></i>outside range</span></div>' +
    '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="' + esc(o.label || "benchmark") + '">' + g + "</svg>";
}

// Heatmap: rows x cols, sequential (one hue) or diverging around a midpoint
function vzHeat(rowLabels, colLabels, get, o) {
  o = o || {};
  var cw = o.cw || 58, rh = o.rh || 26, L = o.labelW || 150, T = o.headH || 64, W = L + colLabels.length * cw + 4, H = T + rowLabels.length * rh + 4, g = "";
  var vals = []; rowLabels.forEach(function (r) { colLabels.forEach(function (c) { var v = get(r, c); if (v != null) vals.push(v); }); });
  var lo = o.lo != null ? o.lo : Math.min.apply(null, vals), hi = o.hi != null ? o.hi : Math.max.apply(null, vals), mid = o.mid;
  function col(v) {
    if (v == null) return "transparent";
    if (mid != null) { var t = v >= mid ? Math.min(1, (v - mid) / ((hi - mid) || 1)) : -Math.min(1, (mid - v) / ((mid - lo) || 1)); return t >= 0 ? "color-mix(in oklab, var(--div-pos) " + Math.round(t * 85) + "%, var(--div-mid))" : "color-mix(in oklab, var(--div-neg) " + Math.round(-t * 85) + "%, var(--div-mid))"; }
    var u = Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1))); return "color-mix(in oklab, var(--seq-hi) " + Math.round(8 + u * 84) + "%, var(--seq-lo))";
  }
  colLabels.forEach(function (c, j) { g += '<text transform="translate(' + (L + j * cw + cw / 2) + "," + (T - 8) + ') rotate(-35)" class="vz-ax">' + esc((o.colName || String)(c)) + "</text>"; });
  rowLabels.forEach(function (r, i) {
    g += '<text x="' + (L - 8) + '" y="' + (T + i * rh + rh / 2 + 4) + '" text-anchor="end" class="vz-lab">' + esc((o.rowName || String)(r)) + "</text>";
    colLabels.forEach(function (c, j) {
      var v = get(r, c), dark = v != null && (mid != null ? Math.abs(v - mid) / Math.max(hi - mid, mid - lo) > .55 : (v - lo) / ((hi - lo) || 1) > .6);
      g += '<rect x="' + (L + j * cw + 1) + '" y="' + (T + i * rh + 1) + '" width="' + (cw - 2) + '" height="' + (rh - 2) + '" rx="4" fill="' + col(v) + '" data-tip="' + esc("<b>" + esc((o.rowName || String)(r)) + " · " + esc((o.colName || String)(c)) + "</b><div>" + (o.tip ? o.tip(v, r, c) : (v == null ? "–" : (o.fmt || shortN)(v))) + "</div>") + '"/>';
      if (v != null && o.showValues !== false) g += '<text x="' + (L + j * cw + cw / 2) + '" y="' + (T + i * rh + rh / 2 + 4) + '" text-anchor="middle" class="vz-cell' + (dark ? " inv" : "") + '" pointer-events="none">' + (o.fmt || shortN)(v) + "</text>";
    });
  });
  return '<div class="vz-scroll"><svg viewBox="0 0 ' + W + " " + H + '" style="min-width:' + Math.min(W, 640) + 'px" class="vz" role="img" aria-label="' + esc(o.label || "heatmap") + '">' + g + "</svg></div>";
}

// Scatter with optional y=x reference
function vzScatter(pts, o) {
  var W = 420, H = 320, P = { l: 48, r: 14, t: 12, b: 40 }, mx = nice(Math.max.apply(null, pts.map(function (p) { return Math.max(p.x, p.y); }).concat([1])));
  var x = function (v) { return P.l + v / mx * (W - P.l - P.r); }, y = function (v) { return H - P.b - v / mx * (H - P.t - P.b); }, g = axisY(y, P, W, [0, mx / 2, mx], shortN);
  [0, mx / 2, mx].forEach(function (t) { g += '<text x="' + x(t) + '" y="' + (H - P.b + 16) + '" text-anchor="middle" class="vz-ax">' + shortN(t) + "</text>"; });
  if (o.diag) g += '<line x1="' + x(0) + '" y1="' + y(0) + '" x2="' + x(mx) + '" y2="' + y(mx) + '" class="vz-target"/>';
  pts.forEach(function (p) { g += '<circle cx="' + x(p.x) + '" cy="' + y(p.y) + '" r="4.5" fill="' + (p.color || "var(--s1)") + '" fill-opacity=".75" stroke="var(--surface)" stroke-width="1.5" data-tip="' + esc(p.tip) + '"/>'; });
  g += '<text x="' + ((W + P.l) / 2) + '" y="' + (H - 4) + '" text-anchor="middle" class="vz-ax">' + esc(o.xLabel) + '</text><text transform="translate(12,' + ((H - P.b) / 2) + ') rotate(-90)" text-anchor="middle" class="vz-ax">' + esc(o.yLabel) + "</text>";
  return '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" style="max-width:560px;margin:auto" role="img" aria-label="' + esc(o.label) + '">' + g + "</svg>";
}

// Forest plot: estimate with 95% range per row
function vzForest(rows, o) {
  var W = 560, rowH = 24, P = { l: 170, r: 60, t: 20, b: 8 }, H = P.t + P.b + rows.length * rowH;
  var lo = Math.min(0, Math.min.apply(null, rows.map(function (r) { return r.lo; }))), hi = Math.max.apply(null, rows.map(function (r) { return r.hi; }));
  var x = function (v) { return P.l + (v - lo) / (hi - lo) * (W - P.l - P.r); }, g = '<line x1="' + x(0) + '" x2="' + x(0) + '" y1="' + (P.t - 6) + '" y2="' + (H - P.b) + '" class="vz-zero"/><text x="' + x(0) + '" y="12" text-anchor="middle" class="vz-ax">0%</text><text x="' + x(hi) + '" y="12" text-anchor="end" class="vz-ax">+' + Math.round(hi) + "%</text>";
  rows.forEach(function (r, i) {
    var y = P.t + i * rowH + rowH / 2;
    g += '<text x="' + (P.l - 8) + '" y="' + (y + 4) + '" text-anchor="end" class="vz-lab">' + esc(r.label) + "</text>";
    g += '<line x1="' + x(r.lo) + '" x2="' + x(r.hi) + '" y1="' + y + '" y2="' + y + '" stroke="var(--s1)" stroke-width="2" stroke-linecap="round"/><circle cx="' + x(r.est) + '" cy="' + y + '" r="5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>';
    g += '<text x="' + (W - P.r + 8) + '" y="' + (y + 4) + '" class="vz-val">' + pctS(r.est) + "</text>";
    g += '<rect class="vz-hit" x="0" y="' + (y - rowH / 2) + '" width="' + W + '" height="' + rowH + '" data-tip="' + esc("<b>" + esc(r.label) + "</b><div>rainy day: <b>" + pctS(r.est) + "</b> orders</div><div>95% range " + pctS(r.lo) + " to " + pctS(r.hi) + "</div>") + '"/>';
  });
  return '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="' + esc(o.label) + '">' + g + "</svg>";
}

// Bubble map: two insets (Europe, Americas), equirectangular, bubbles sized by revenue, coloured by MER vs target
function vzMap(markets, target) {
  var boxes = [{ name: "Europe", lon: [-11, 16], lat: [37, 55], x: 0, w: 390 }, { name: "Americas", lon: [-104, -38], lat: [-28, 45], x: 404, w: 236 }];
  var H = 320, g = "", mxR = Math.max.apply(null, markets.map(function (m) { return m.revenue; }));
  function col(m) {
    if (m.mer == null) return "var(--muted-fill)";
    var t = Math.max(-1, Math.min(1, (m.mer - target) / (target * 0.25)));
    return t >= 0 ? "color-mix(in oklab, var(--div-pos) " + Math.round(25 + t * 75) + "%, var(--div-mid))" : "color-mix(in oklab, var(--div-neg) " + Math.round(25 - t * 75) + "%, var(--div-mid))";
  }
  boxes.forEach(function (b) {
    g += '<rect x="' + b.x + '" y="0" width="' + b.w + '" height="' + H + '" rx="14" class="vz-mapbg"/><text x="' + (b.x + 12) + '" y="20" class="vz-ax">' + b.name + "</text>";
    for (var la = Math.ceil(b.lat[0] / 10) * 10; la <= b.lat[1]; la += 10) { var yy = 30 + (1 - (la - b.lat[0]) / (b.lat[1] - b.lat[0])) * (H - 60); g += '<line x1="' + (b.x + 8) + '" x2="' + (b.x + b.w - 8) + '" y1="' + yy + '" y2="' + yy + '" class="vz-grid"/><text x="' + (b.x + b.w - 10) + '" y="' + (yy - 3) + '" text-anchor="end" class="vz-ax">' + la + "°</text>"; }
    var ms = markets.filter(function (m) { return m.lon >= b.lon[0] && m.lon <= b.lon[1] && m.lat >= b.lat[0] && m.lat <= b.lat[1]; });
    var placed = [];
    ms.sort(function (a, c) { return c.revenue - a.revenue; }).forEach(function (m) {
      var cx = b.x + 24 + (m.lon - b.lon[0]) / (b.lon[1] - b.lon[0]) * (b.w - 48), cy = 34 + (1 - (m.lat - b.lat[0]) / (b.lat[1] - b.lat[0])) * (H - 70), r = 5 + 15 * Math.sqrt(m.revenue / mxR);
      g += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="' + col(m) + '" fill-opacity=".8" stroke="var(--surface)" stroke-width="1.5" data-tip="' + esc("<b>" + esc(m.market) + (m.new ? " (new market)" : "") + "</b><div>revenue 28 days: <b>" + eurS(m.revenue) + "</b></div><div>marketing: " + eurS(m.spend) + " · MER <b>" + (m.mer == null ? "–" : m.mer.toFixed(1)) + "</b> (target " + target + ")</div><div>vs last year: " + pctS(m.yoy_pct) + "</div>") + '"/>';
      var ly = cy + r + 12, lx = cx;
      placed.forEach(function (q) { if (Math.abs(q[0] - lx) < 56 && Math.abs(q[1] - ly) < 12) ly = q[1] + 13; });
      placed.push([lx, ly]);
      g += '<text x="' + lx + '" y="' + ly + '" text-anchor="middle" class="vz-lab" pointer-events="none">' + esc(m.market) + " · " + (m.mer == null ? "–" : m.mer.toFixed(1)) + "×</text>";
    });
  });
  return '<div class="vz-legend"><span><i style="background:var(--div-neg)"></i>MER below the ' + target + '× target</span><span><i style="background:var(--div-mid)"></i>at target</span><span><i style="background:var(--div-pos)"></i>above</span><span>bubble size: revenue, last 28 days</span></div>' +
    '<svg viewBox="0 0 640 ' + H + '" class="vz" role="img" aria-label="Markets by revenue and MER">' + g + "</svg>";
}

// Response curves as small multiples: revenue change when one channel's spend is scaled
function vzCurves(cv) {
  var chans = Object.keys(cv.channels), out = "", all = [];
  chans.forEach(function (c) { cv.channels[c].pts.forEach(function (p) { all.push(p[1]); }); });
  var lo = Math.min(0, Math.min.apply(null, all)), hi = Math.max(1, Math.max.apply(null, all));
  chans.forEach(function (c) {
    var d = cv.channels[c], W = 200, H = 128, P = { l: 40, r: 8, t: 22, b: 20 }, pts = d.pts;
    var x = function (k) { return P.l + (k - .25) / 1.75 * (W - P.l - P.r); }, y = function (v) { return H - P.b - (v - lo) / (hi - lo) * (H - P.t - P.b); };
    var good = d.mroas != null && d.mroas >= 1, colr = good ? S(0) : S(7);
    var g = '<text x="' + (P.l - 30) + '" y="13" class="vz-lab" style="font-size:10.5px"><tspan font-weight="650">' + esc(CH(c)) + '</tspan></text><text x="' + (W - P.r) + '" y="13" text-anchor="end" class="vz-ax">mROAS ' + (d.mroas == null ? "–" : d.mroas.toFixed(1)) + "</text>";
    g += '<text x="' + (P.l - 4) + '" y="' + (y(hi) + 4) + '" text-anchor="end" class="vz-ax">' + eurS(hi) + '</text><text x="' + (P.l - 4) + '" y="' + (y(lo) + 4) + '" text-anchor="end" class="vz-ax">' + eurS(lo) + "</text>";
    g += '<line x1="' + P.l + '" x2="' + (W - P.r) + '" y1="' + y(0) + '" y2="' + y(0) + '" class="vz-zero"/><line x1="' + x(1) + '" x2="' + x(1) + '" y1="' + P.t + '" y2="' + (H - P.b) + '" class="vz-target"/>';
    g += '<polyline fill="none" stroke="' + colr + '" stroke-width="2" points="' + pts.map(function (p) { return x(p[0]) + "," + y(p[1]); }).join(" ") + '"/>';
    g += '<circle cx="' + x(1) + '" cy="' + y(0) + '" r="4" fill="' + colr + '"/><text x="' + P.l + '" y="' + (H - 5) + '" class="vz-ax">×0.25</text><text x="' + (W - P.r) + '" y="' + (H - 5) + '" text-anchor="end" class="vz-ax">×2 spend</text>';
    pts.forEach(function (p) { g += '<rect class="vz-hit" x="' + (x(p[0]) - 12) + '" y="' + P.t + '" width="24" height="' + (H - P.t - P.b) + '" data-tip="' + esc("<b>" + esc(CH(c)) + "</b><div>spend ×" + p[0] + " (" + eurS(d.spend * p[0]) + "/week)</div><div>revenue " + sgn(p[1], eurS) + " a week</div>") + '"/>'; });
    out += '<svg viewBox="0 0 ' + W + " " + H + '" class="vz sm" role="img" aria-label="Response curve ' + esc(c) + '">' + g + "</svg>";
  });
  return '<div class="vz-legend"><span><i style="background:var(--s1)"></i>earns more than it costs at today\'s spend</span><span><i style="background:var(--s8)"></i>earns less (marginal ROAS below 1)</span><span>all channels on the same scale</span></div><div class="sm-grid">' + out + "</div>";
}

function vzHist(vals, bins, o) {
  var W = 420, H = 160, P = { l: 30, r: 10, t: 10, b: 24 }, lo = o.lo, hi = o.hi, n = Array(bins).fill(0);
  vals.forEach(function (v) { n[Math.min(bins - 1, Math.max(0, Math.floor((v - lo) / (hi - lo) * bins)))]++; });
  var mx = Math.max.apply(null, n), bw = (W - P.l - P.r) / bins, g = "";
  n.forEach(function (c, i) { var h = c / mx * (H - P.t - P.b); g += '<rect x="' + (P.l + i * bw + 1) + '" y="' + (H - P.b - h) + '" width="' + (bw - 2) + '" height="' + h + '" rx="3" fill="var(--s1)" data-tip="' + esc((lo + i * (hi - lo) / bins).toFixed(2) + "–" + (lo + (i + 1) * (hi - lo) / bins).toFixed(2) + ": <b>" + c + "</b> " + esc(o.unit)) + '"/>'; });
  [lo, (lo + hi) / 2, hi].forEach(function (t) { g += '<text x="' + (P.l + (t - lo) / (hi - lo) * (W - P.l - P.r)) + '" y="' + (H - 6) + '" text-anchor="middle" class="vz-ax">' + t.toFixed(1) + "</text>"; });
  return '<svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="' + esc(o.label) + '">' + g + "</svg>";
}

function vzRain(rows) {
  return '<div class="rain-grid">' + rows.map(function (r) {
    var mx = 12, bars = r.days.map(function (d, i) { var h = Math.min(1, d[1] / mx) * 34; return '<rect x="' + (i * 9) + '" y="' + (38 - h) + '" width="7" height="' + Math.max(1, h) + '" rx="2" fill="' + (d[1] >= 2 ? "var(--s1)" : "var(--muted-fill)") + '" data-tip="' + esc("<b>" + esc(r.market) + " · " + d[0] + "</b><div>" + d[1].toFixed(1) + " mm" + (d[1] >= 2 ? " · rainy day" : "") + "</div>") + '"/>'; }).join("");
    var wet = r.days.filter(function (d) { return d[1] >= 2; }).length;
    return '<div class="rain"><div><b>' + esc(r.market) + "</b><span>" + wet + " rainy days</span></div><svg viewBox=\"0 0 126 40\" class=\"vz\" role=\"img\" aria-label=\"14-day rain forecast " + esc(r.market) + '">' + bars + "</svg></div>";
  }).join("") + "</div>";
}

function vzSpark(rows, key, color) {
  if (!rows || rows.length < 3) return "";
  var v = rows.slice(-26).map(function (r) { return r[key] || 0; }), mx = Math.max.apply(null, v), mn = Math.min.apply(null, v), W = 160, H = 36;
  var pts = v.map(function (a, i) { return (i * W / (v.length - 1)).toFixed(1) + "," + (H - 3 - (a - mn) / ((mx - mn) || 1) * (H - 6)).toFixed(1); }).join(" ");
  return '<svg class="spark" viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none" aria-hidden="true"><polyline fill="none" stroke="' + (color || "var(--s1)") + '" stroke-width="1.8" points="' + pts + '"/></svg>';
}

// ---------- the dashboard ----------
var AGENT_LABEL = { growth_lead: "Growth lead", benchmark_analyst: "Benchmark analyst", demand_strategist: "Demand strategist", customer_voice_analyst: "Customer voice analyst", media_budget_planner: "Media & budget planner", stakeholder_comms: "Stakeholder comms" };
var CH = function (c) { return c.replace("meta_", "Meta ").replace("google_", "Google ").replace(/_/g, " "); };

function entKpis(E, mk) {
  var w = E.weekly[mk] || E.weekly.all, n = w.length, sum = function (a, b, k) { return w.slice(a, b).reduce(function (s, r) { return s + (r[k] || 0); }, 0); };
  var cur = function (k) { return sum(n - 4, n, k); }, prev = function (k) { return sum(n - 8, n - 4, k); }, ly = function (k) { return sum(n - 56, n - 52, k); };
  var tiles = [["Revenue, last 4 weeks", cur("revenue"), prev("revenue"), ly("revenue"), eurS, "revenue", "var(--s1)"],
    ["Marketing spend", cur("spend"), prev("spend"), ly("spend"), eurS, "spend", "var(--s2)", null],
    ["MER (revenue ÷ marketing)", cur("revenue") / cur("spend"), prev("revenue") / prev("spend"), ly("revenue") / ly("spend"), function (v) { return v.toFixed(2) + "×"; }, "mer", "var(--s3)"],
    ["Blended CAC", cur("spend") / cur("new_customers"), prev("spend") / prev("new_customers"), ly("spend") / ly("new_customers"), function (v) { return "€" + v.toFixed(2); }, "cac", "var(--s7)", true],
    ["Gross profit after marketing", cur("profit"), prev("profit"), ly("profit"), eurS, "profit", "var(--s3)"]];
  return '<div class="kpi-row">' + tiles.map(function (t) {
    var ch = (t[1] / t[2] - 1) * 100, y = t[3] ? (t[1] / t[3] - 1) * 100 : null, good = t[7] ? ch <= 0 : ch >= 0;
    var cls = t[7] === null || Math.abs(ch) < 1 ? "flat" : good ? "up" : "down";
    return '<div class="card glass kpi2"><div class="l">' + t[0] + '</div><div class="n">' + t[4](t[1]) + '</div><div class="d"><span class="' + cls + '">' + (ch >= 0 ? "▲ " : "▼ ") + Math.abs(ch).toFixed(1) + '%</span> vs 4 weeks before' + (y != null && isFinite(y) ? ' · <span class="muted">' + pctS(y) + " vs last year</span>" : "") + "</div>" + vzSpark(w, t[5], t[6]) + "</div>";
  }).join("") + "</div>";
}

function renderEnterprise(v) {
  vzTip();
  var E = v.ent, I = E.impact, ch = I.change, cp = I.change_pct, mk = window.__gosMarket || "all";
  var nav = [["overview", "Overview"], ["decisions", "Decisions"], ["team", "Agent team"], ["markets", "Markets"], ["demand", "Demand"], ["benchmarks", "Benchmarks"], ["budget", "Budget & channels"], ["voice", "Customer voice"], ["technical", "Model quality"], ["assumptions", "Assumptions"]];
  var markets = ["all"].concat(E.market_map.map(function (m) { return m.market; }));
  var w = E.weekly[mk] || E.weekly.all, mer = E.targets.mer || 8;
  var h = '<div class="ent">';
  h += '<aside class="side glass"><div class="side-h">Agent team · 12 markets</div>' + nav.map(function (n) { return '<a href="#s-' + n[0] + '">' + n[1] + "</a>"; }).join("") +
    '<label class="side-f">Market<select id="mk">' + markets.map(function (m) { return "<option" + (m === mk ? " selected" : "") + ' value="' + esc(m) + '">' + (m === "all" ? "All markets" : esc(m)) + "</option>"; }).join("") + "</select></label>" +
    '<p class="side-note">' + esc(v.label) + "</p></aside><div class=\"ent-main\">";
  // OVERVIEW
  h += '<section id="s-overview" class="sec"><div class="sec-h"><h2>Overview</h2><p>' + esc(v.blurb) + "</p></div>" + entKpis(E, mk);
  h += '<div class="g2"><div class="card glass"><h3>Revenue per week</h3><p class="sub">' + (mk === "all" ? "All markets" : esc(mk)) + ", with the same weeks last year</p>" +
    vzLine("rev", w.map(function (r, i) { return { week: r.week, revenue: r.revenue, ly: i >= 52 ? w[i - 52].revenue : null }; }).slice(-30), "week", [{ key: "revenue", label: "this year", color: "var(--s1)", area: true }, { key: "ly", label: "last year", color: "var(--text-2)", dash: true }], { fmt: eurS }) + "</div>";
  h += '<div class="card glass"><h3>MER per week against target</h3><p class="sub">Revenue ÷ marketing spend; the dashed line is the ' + mer + "× target</p>" +
    vzLine("mer", w.slice(-30), "week", [{ key: "mer", label: "MER", color: "var(--s3)" }], { target: mer, zero: false, fmt: function (x) { return x.toFixed(1) + "×"; } }) + "</div></div>";
  h += '<div class="g2"><div class="card glass"><h3>Where revenue comes from</h3><p class="sub">Organic (search, social, direct), owned (email, SMS) and paid, per week</p>' +
    vzStack(w.slice(-30), "week", [{ key: "organic", label: "organic", color: "var(--s1)" }, { key: "owned", label: "owned", color: "var(--s3)" }, { key: "paid", label: "paid", color: "var(--s2)" }], { fmt: eurS }) + "</div>";
  h += '<div class="card glass"><h3>Marketing spend per week</h3><p class="sub">Across 8 paid channels</p>' + vzLine("spend", w.slice(-30), "week", [{ key: "spend", label: "spend", color: "var(--s2)", area: true }], { fmt: eurS }) + "</div></div></section>";
  // DECISIONS
  h += '<section id="s-decisions" class="sec"><div class="sec-h"><h2>Decisions and their impact</h2><p>' + esc(E.headline) + "</p></div>";
  h += '<div class="impact-hero card glass"><div><span class="l">Next quarter, all decisions approved</span><div class="big pos">' + sgn(ch.gross_profit, eurS) + ' <small>gross profit</small></div><div class="mid">' + sgn(ch.revenue, eurS) + " revenue (" + pctS(cp.revenue) + ") · spend " + pctS(cp.spend) + " · MER " + I.as_is.mer.toFixed(2) + " → " + I.with_decisions.mer.toFixed(2) + '</div><p class="sub">' + esc(I.note) + " Baseline: " + esc(I.baseline || "as-is") + ".</p>" + deckHowToRead(E) + "</div>" +
    '<div class="team-cost"><div><b>$' + E.team_cost_usd.toFixed(2) + '</b><span>agent team, this run</span></div><div><b>' + Math.round(E.team_seconds / 60) + ' min</b><span>to decisions</span></div><div><b>~' + E.time.hours_per_week + ' h</b><span>team work a week (estimate)</span></div></div></div>';
  h += '<div class="g2"><div class="card glass"><h3>Gross profit by decision</h3><p class="sub">Each decision alone over the quarter, then the effect of running them together (overlaps, guardrail deferrals)</p>' + vzWaterfall(E.waterfall) + "</div>";
  var roles = Object.keys(E.routing_by_role);
  h += '<div class="card glass"><h3>Who approves what</h3><p class="sub">Decisions routed by risk tier to the role that owns them</p>' +
    vzBars(roles.map(function (r) { var x = E.routing_by_role[r]; return { label: r, value: x.low + x.medium + x.high, tip: "<b>" + esc(r) + "</b><div>low " + x.low + " · medium " + x.medium + " · high " + x.high + "</div>" }; }), { fmt: function (x) { return x + (x === 1 ? " decision" : " decisions"); }, labelW: 200 }) +
    '<h3 style="margin-top:16px">What each role receives</h3><nav class="seg glass" id="roles" role="tablist">' + E.briefs.map(function (b, i) { return '<button type="button" data-i="' + i + '" aria-selected="' + (i === 0) + '">' + esc(b.role) + "</button>"; }).join("") + '</nav><p id="rolebody" class="lead"></p></div></div>';
  h += deckShell(E) + "</section>";
  // TEAM
  h += '<section id="s-team" class="sec"><div class="sec-h"><h2>The agent team</h2><p>Six Claude agents with one job each, on one shared tool layer that any MCP client can also use. Operations is a rule-based executor, not a model.</p></div>';
  h += '<div class="card glass">' + teamDiagram() + "</div>";
  var ag = E.agents;
  h += '<div class="g3"><div class="card glass"><h3>Time per agent</h3><p class="sub">Specialists run in parallel inside the lead\'s run</p>' + vzBars(ag.map(function (a) { return { label: AGENT_LABEL[a.role] || a.role, value: a.seconds }; }), { fmt: function (x) { return Math.round(x) + " s"; }, labelW: 170, w: 440 }) + "</div>" +
    '<div class="card glass"><h3>Cost per agent</h3><p class="sub">Claude Opus 5.5, this run</p>' + vzBars(ag.map(function (a) { return { label: AGENT_LABEL[a.role] || a.role, value: a.cost_usd, color: "var(--s7)" }; }), { fmt: function (x) { return "$" + x.toFixed(2); }, labelW: 170, w: 440 }) + "</div>" +
    '<div class="card glass"><h3>Tool calls per agent</h3><p class="sub">Queries and engine calls made to reach their findings</p>' + vzBars(ag.map(function (a) { return { label: AGENT_LABEL[a.role] || a.role, value: a.tool_calls, color: "var(--s3)" }; }), { fmt: function (x) { return x + ""; }, labelW: 170, w: 440 }) + "</div></div>";
  h += '<div class="card glass">' + Object.keys(E.specialists).map(function (k) {
    return E.specialists[k].map(function (r) {
      return '<details class="more"><summary><b>' + esc(AGENT_LABEL[k]) + "</b>: " + esc(r.summary) + '</summary><ul class="flist">' + r.findings.map(function (f) { return '<li><span class="chip ' + (f.confidence === "high" ? "good" : f.confidence === "medium" ? "warn" : "muted") + '">' + esc(f.confidence) + "</span> <b>" + esc(f.market) + (f.line && f.line !== "all" ? " · " + esc(f.line) : "") + ": " + esc(f.title) + "</b>" + (f.money_at_stake_eur_per_month ? ' <span class="neg">' + eurS(f.money_at_stake_eur_per_month) + "/month</span>" : "") + '<br><span class="ev">' + esc(f.evidence) + "</span></li>"; }).join("") + "</ul>" + (r.not_problems.length ? '<p class="sub"><b>Not problems:</b> ' + r.not_problems.map(esc).join(" · ") + "</p>" : "") + '<p class="sub">Tools: ' + esc(Array.from(new Set(r.tool_calls)).join(", ")) + "</p></details>";
    }).join("");
  }).join("") + "</div></section>";
  // MARKETS
  h += '<section id="s-markets" class="sec"><div class="sec-h"><h2>Markets</h2><p>Revenue and efficiency by city, last 28 days.</p></div><div class="card glass">' + vzMap(E.market_map, mer) + "</div>";
  h += '<div class="card glass"><h3>Organic vs paid by market</h3><p class="sub">Last 28 days vs the 28 before. A falling organic share with rising spend means paid is covering for something.</p><div class="tw"><table><tr><th>Market</th><th class="num">Revenue</th><th class="num">Organic</th><th class="num">Owned</th><th class="num">Paid</th><th class="num">Organic change</th><th class="num">Spend change</th><th class="num">MER</th></tr>' +
    E.organic.map(function (o) { return "<tr><td>" + esc(o.market) + '</td><td class="num">' + eurS(o.revenue) + '</td><td class="num">' + o.organic_pct + '%</td><td class="num">' + o.owned_pct + '%</td><td class="num">' + o.paid_pct + '%</td><td class="num ' + (o.organic_change_pct < -10 ? "neg" : "") + '">' + pctS(o.organic_change_pct) + '</td><td class="num">' + pctS(o.spend_change_pct) + '</td><td class="num">' + (o.mer == null ? "–" : o.mer.toFixed(1)) + "</td></tr>"; }).join("") + "</table></div></div></section>";
  // DEMAND
  var lines = E.lines, pot = {};
  (E.potential_all || E.potential).forEach(function (p) { pot[p.market + "|" + p.line] = p; });
  h += '<section id="s-demand" class="sec"><div class="sec-h"><h2>Demand engine</h2><p>How much demand each market has, how much the brand captures, and what the weather will do next. Accuracy on weeks the model never saw: <b>' + E.accuracy.mape_pct + "%</b> average error, " + E.accuracy.within_10pct_share + "% of weeks within 10%.</p></div>";
  var potRows = Array.from(new Set((E.potential_all || E.potential).map(function (p) { return p.market; })));
  h += '<div class="g2"><div class="card glass"><h3>Captured share of potential demand</h3><p class="sub">Brand orders against category search interest, compared with peers adjusted for affluence and competition. Low = demand the brand is not reaching.</p>' +
    vzHeat(potRows, lines, function (r, c) { var p = pot[r + "|" + c]; return p ? p.captured_share_of_potential_pct : null; }, { mid: 100, lo: 50, hi: 130, fmt: function (x) { return Math.round(x) + "%"; }, tip: function (vv, r, c) { var p = pot[r + "|" + c]; return p ? "captured <b>" + Math.round(p.captured_share_of_potential_pct) + "%</b> of potential<br>gap: " + eurS(p.gap_revenue) + " over " + p.weeks + " weeks" : "–"; }, cw: 86, labelW: 110, label: "Captured share heatmap" }) +
    '<div class="vz-legend"><span><i style="background:var(--div-neg)"></i>under-captured</span><span><i style="background:var(--div-mid)"></i>as peers</span><span><i style="background:var(--div-pos)"></i>above peers</span></div></div>';
  h += '<div class="card glass"><h3>Rain effect on orders</h3><p class="sub">Change in daily orders on a rainy day, with 95% range, from real weather (Open-Meteo). Top 10.</p>' +
    vzForest(E.rain.slice(0, 10).map(function (r) { return { label: r.market + " · " + r.line, est: r.rain_effect_pct, lo: r.rain_effect_range_pct[0], hi: r.rain_effect_range_pct[1] }; }), { label: "Rain effect forest plot" }) + "</div></div>";
  if (E.rain_forecast.length) h += '<div class="card glass"><h3>Next 14 days: rain forecast per city</h3><p class="sub">Real forecast. Blue bars are rainy days (≥ 2 mm), when rain-sensitive lines sell more.</p>' + vzRain(E.rain_forecast) + "</div>";
  h += "</section>";
  // BENCHMARKS
  var bm = window.__gosBench || "checkout_to_order_ios_pct", bnames = { checkout_to_order_ios_pct: "Checkout → order, iOS (%)", checkout_to_order_android_pct: "Checkout → order, Android (%)", mer: "MER", organic_share_pct: "Organic share of revenue (%)", repeat_share_pct: "Repeat (email/SMS) share (%)", revenue_per_day: "Revenue per day" };
  h += '<section id="s-benchmarks" class="sec"><div class="sec-h"><h2>Benchmark engine</h2><p>Each market against its own same weeks last year and the range of peer markets with a similar profile.</p></div><div class="card glass"><div class="seg glass" id="bm">' +
    Object.keys(bnames).map(function (k) { return '<button type="button" data-k="' + k + '" aria-selected="' + (k === bm) + '">' + bnames[k] + "</button>"; }).join("") + "</div>" +
    vzDotRange(E.bench_metrics[bm], { fmt: bm === "revenue_per_day" ? eurS : function (x) { return x == null ? "–" : x.toFixed(1); }, label: bnames[bm] }) + "</div>";
  h += '<div class="g2">' + (E.seasonal || []).map(function (b) { return '<div class="card glass note-card"><b>Not a problem: ' + esc(b.market) + "</b><p>Revenue per day " + eurS(b.value) + " vs " + eurS(b.previous_period) + " the month before looks like a fall; the same weeks last year were " + eurS(b.same_period_last_year) + ". Seasonal.</p></div>"; }).join("") +
    '<div class="card glass note-card"><b>Launch benchmark: ' + esc(E.launch_market) + "</b><p>Week " + E.launch.weeks_since_launch + " since opening: " + (E.launch.share_of_earlier_median_pct == null ? "–" : E.launch.share_of_earlier_median_pct + "%") + " of what earlier launches made at the same age.</p></div></div></section>";
  // BUDGET
  var cks = Object.keys(E.curves), cur = window.__gosCurve && E.curves[window.__gosCurve] ? window.__gosCurve : cks[0];
  h += '<section id="s-budget" class="sec"><div class="sec-h"><h2>Budget & channels</h2><p>Where the next euro earns most. From a marketing-mix model fitted on 60 weeks of budget changes, pooled across markets and shrunk toward each market\'s own data.</p></div>';
  h += '<div class="card glass"><h3>Marginal ROAS by market and channel</h3><p class="sub">Revenue from the next euro of spend. Blue earns more than it costs; red is past saturation or mostly collects buyers who would come anyway.</p>' +
    vzHeat(Object.keys(E.mroas), E.channels, function (r, c) { return E.mroas[r][c]; }, { mid: 1, lo: 0, hi: 4, fmt: function (x) { return x.toFixed(1); }, colName: CH, cw: 80, labelW: 110, label: "Marginal ROAS heatmap", tip: function (vv) { return "marginal ROAS <b>" + (vv == null ? "–" : vv.toFixed(2)) + "</b>: each extra €1 brings €" + (vv == null ? "–" : vv.toFixed(2)) + " of revenue"; } }) + "</div>";
  h += '<div class="card glass"><div class="row-h"><div><h3>Response curves</h3><p class="sub">Weekly revenue change if one channel\'s spend is scaled, everything else equal. The dot is today; the slope there is the marginal ROAS.</p></div><select id="cv">' +
    cks.map(function (k) { return "<option" + (k === cur ? " selected" : "") + ">" + esc(k.replace("|", " · ")) + "</option>"; }).join("") + "</select></div>" + vzCurves(E.curves[cur]) + '<p class="sub">Model fit for this market and line: r² ' + E.curves[cur].r2 + "</p></div>";
  h += '<div class="g2"><div class="card glass"><h3>Spend share vs revenue share by channel</h3><p class="sub">Last 28 days, first-party last-click revenue</p>' + pairedShare(E.channel_share) + "</div>";
  h += '<div class="card glass"><h3>What platforms claim vs first-party revenue</h3><p class="sub">ROAS by channel, last 28 days. The gap is double counting across platforms.</p>' + dumbbell(E.platform) + "</div></div></section>";
  // VOICE
  var vmx = E.voc_matrix, themes = vmx.themes, vrows = vmx.rows.map(function (r) { return r.market; });
  h += '<section id="s-voice" class="sec"><div class="sec-h"><h2>Customer voice engine</h2><p>' + fmt(E.voc_count) + " comments (NPS, exit survey, reviews, support tickets) in six languages, labelled by Claude Haiku. Last 28 days.</p></div>";
  h += '<div class="card glass"><h3>Complaint themes by market</h3><p class="sub">Share of each market\'s comments; darker = more frequent</p>' +
    vzHeat(vrows, themes, function (r, c) { var row = vmx.rows.find(function (x) { return x.market === r; }); return row ? row[c] : null; }, { fmt: function (x) { return x.toFixed(0); }, colName: function (c) { return c.replace(/_/g, " "); }, cw: 66, labelW: 110, label: "Theme heatmap", tip: function (vv) { return "<b>" + (vv == null ? "–" : vv.toFixed(1)) + "%</b> of comments"; } }) + "</div>";
  h += '<div class="card glass"><h3>Themes that stand out</h3><div class="tw"><table><tr><th>Market · line</th><th>Theme</th><th class="num">Share</th><th class="num">Elsewhere</th><th class="num">NPS</th></tr>' +
    E.voc.map(function (g) { return "<tr><td>" + esc(g.market) + " · " + esc(g.line) + "</td><td>" + esc(g.theme.replace(/_/g, " ")) + (g.new ? ' <span class="chip bad">new</span>' : "") + '</td><td class="num neg">' + g.share_pct + '%</td><td class="num">' + g.elsewhere_pct + '%</td><td class="num">' + (g.nps == null ? "–" : g.nps) + "</td></tr>"; }).join("") + "</table></div></div></section>";
  // TECHNICAL
  var val = E.validation;
  var corr = (function () { var n = val.length, mx = val.reduce(function (a, p) { return a + p.est; }, 0) / n, my = val.reduce(function (a, p) { return a + p.true; }, 0) / n, sxy = 0, sx = 0, sy = 0; val.forEach(function (p) { sxy += (p.est - mx) * (p.true - my); sx += (p.est - mx) * (p.est - mx); sy += (p.true - my) * (p.true - my); }); return sxy / Math.sqrt(sx * sy); })();
  h += '<section id="s-technical" class="sec"><div class="sec-h"><h2>Model quality</h2><p>Checks you can only run in a simulation, where the true answer is known, plus the model fits.</p></div><div class="g2">';
  h += '<div class="card glass"><h3>Estimated vs true marginal ROAS</h3><p class="sub">Each dot is one market × line × channel. On the dashed line the model is exactly right. Correlation r = ' + corr.toFixed(2) + ".</p>" +
    vzScatter(val.map(function (p) { return { x: p.true, y: p.est, tip: "<b>" + esc(p.market) + " · " + esc(p.line) + " · " + esc(CH(p.channel)) + "</b><div>true " + p.true.toFixed(2) + " · estimated " + (p.est == null ? "–" : p.est.toFixed(2)) + "</div>" }; }).filter(function (p) { return p.y != null; }), { diag: true, xLabel: "true marginal ROAS (simulation)", yLabel: "estimated by the mix model", label: "Estimated vs true marginal ROAS" }) + "</div>";
  h += '<div class="card glass"><h3>Mix model fit per market × line</h3><p class="sub">r² of the weekly model (share of week-to-week revenue variation explained)</p>' + vzHist(E.r2, 10, { lo: 0, hi: 1, unit: "market-lines", label: "r² histogram" }) +
    '<h3 style="margin-top:14px">Evaluations</h3><div class="tw"><table><tr><th>When</th><th>What</th><th class="num">Passed</th><th class="num">Cost</th></tr>' + DATA.evals.slice(-6).reverse().map(function (e) { return "<tr><td>" + esc(e.when.slice(0, 10)) + "</td><td>" + esc(e.scenario) + " · " + esc(e.split) + '</td><td class="num">' + e.passed + "/" + e.criteria + '</td><td class="num">$' + (e.mean_cost_usd == null ? "–" : e.mean_cost_usd) + "</td></tr>"; }).join("") + "</table></div></div></div></section>";
  // ASSUMPTIONS
  h += '<section id="s-assumptions" class="sec"><div class="sec-h"><h2>Assumptions and sources</h2></div><div class="g2"><div class="card glass"><h3>What the simulation assumes</h3><ul class="assume">' + E.assumptions.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + '</ul></div><div class="card glass"><h3>Team time the system takes over (estimate)</h3><p class="sub">' + esc(E.time.note) + '</p><ul class="assume">' + E.time.rows.map(function (r) { return "<li>" + esc(r.task) + ": <b>" + r.hours_per_week + " h</b>" + (r.basis ? " (" + esc(r.basis) + ")" : "") + "</li>"; }).join("") + '</ul><h3 style="margin-top:12px">Data sources</h3><ul class="assume">' + E.sources.map(function (s) { return s.note ? "<li>" + esc(s.note) + "</li>" : ""; }).join("") + "</ul></div></div></section>";
  h += "</div></div>";
  $("#view").innerHTML = h;
  bindEnterprise(v);
}

function pairedShare(rows) {
  var ts = rows.reduce(function (a, r) { return a + r.spend; }, 0), tr = rows.reduce(function (a, r) { return a + r.revenue; }, 0);
  var items = [];
  rows.forEach(function (r) { items.push({ label: CH(r.channel) + " · spend", value: 100 * r.spend / ts, color: "var(--s2)", tip: "<b>" + esc(CH(r.channel)) + "</b><div>spend " + eurS(r.spend) + " (" + (100 * r.spend / ts).toFixed(1) + "%)</div><div>revenue " + eurS(r.revenue) + " (" + (100 * r.revenue / tr).toFixed(1) + "%)</div>" }); items.push({ label: "revenue", value: 100 * r.revenue / tr, color: "var(--s1)", tip: "<b>" + esc(CH(r.channel)) + "</b><div>revenue " + eurS(r.revenue) + " (" + (100 * r.revenue / tr).toFixed(1) + "%)</div>" }); });
  return '<div class="vz-legend"><span><i style="background:var(--s2)"></i>share of paid spend</span><span><i style="background:var(--s1)"></i>share of paid revenue</span></div>' + vzBars(items, { fmt: function (x) { return x.toFixed(1) + "%"; }, labelW: 190, rowH: 18 });
}

function dumbbell(rows) {
  var W = 560, rowH = 26, P = { l: 150, r: 70, t: 10, b: 8 }, H = P.t + P.b + rows.length * rowH, mx = nice(Math.max.apply(null, rows.map(function (r) { return Math.max(r.platform_roas || 0, r.fp_roas || 0); })));
  var x = function (v) { return P.l + v / mx * (W - P.l - P.r); }, g = "";
  rows.forEach(function (r, i) {
    var y = P.t + i * rowH + rowH / 2;
    g += '<text x="' + (P.l - 8) + '" y="' + (y + 4) + '" text-anchor="end" class="vz-lab">' + esc(CH(r.channel)) + '</text><line x1="' + x(r.fp_roas) + '" x2="' + x(r.platform_roas) + '" y1="' + y + '" y2="' + y + '" stroke="var(--grid-strong)" stroke-width="3" stroke-linecap="round"/>';
    g += '<circle cx="' + x(r.fp_roas) + '" cy="' + y + '" r="6" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/><circle cx="' + x(r.platform_roas) + '" cy="' + y + '" r="6" fill="var(--s2)" stroke="var(--surface)" stroke-width="2"/>';
    g += '<text x="' + (W - P.r + 8) + '" y="' + (y + 4) + '" class="vz-val">×' + (r.platform_roas / r.fp_roas).toFixed(2) + "</text>";
    g += '<rect class="vz-hit" x="0" y="' + (y - rowH / 2) + '" width="' + W + '" height="' + rowH + '" data-tip="' + esc("<b>" + esc(CH(r.channel)) + "</b><div>first-party ROAS <b>" + r.fp_roas.toFixed(2) + "</b></div><div>platform claims <b>" + r.platform_roas.toFixed(2) + "</b></div><div>spend " + eurS(r.spend) + "</div>") + '"/>';
  });
  return '<div class="vz-legend"><span><i style="background:var(--s1)"></i>first-party ROAS</span><span><i style="background:var(--s2)"></i>platform-reported ROAS</span><span>×: over-claim</span></div><svg viewBox="0 0 ' + W + " " + H + '" class="vz" role="img" aria-label="Platform vs first-party ROAS">' + g + "</svg>";
}

function teamDiagram() {
  var W = 900, H = 300, box = function (x, y, w, h, t, sub, cls) { return '<g class="node ' + (cls || "") + '"><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="12"/><text x="' + (x + w / 2) + '" y="' + (y + h / 2 - (sub ? 2 : -4)) + '" text-anchor="middle" class="nt">' + t + "</text>" + (sub ? '<text x="' + (x + w / 2) + '" y="' + (y + h / 2 + 14) + '" text-anchor="middle" class="ns">' + sub + "</text>" : "") + "</g>"; };
  var line = function (x1, y1, x2, y2) { return '<path d="M' + x1 + "," + y1 + " C" + x1 + "," + ((y1 + y2) / 2) + " " + x2 + "," + ((y1 + y2) / 2) + " " + x2 + "," + y2 + '" class="edge"/>'; };
  var sp = [["Benchmark analyst", "history · peers · launches"], ["Demand strategist", "potential · weather · outlook"], ["Customer voice analyst", "surveys · NPS · reviews"], ["Media & budget planner", "mix model · mROAS · claims"]], g = "";
  sp.forEach(function (s, i) { var x = 20 + i * 220; g += line(450, 78, x + 95, 128) + line(x + 95, 188, 450, 238) ; });
  g += line(450, 78, 760, 238);
  g += box(330, 18, 240, 60, "Growth lead", "briefs · weighs · decides", "lead");
  sp.forEach(function (s, i) { g += box(20 + i * 220, 128, 190, 60, s[0], s[1]); });
  g += box(250, 238, 400, 50, "Shared engines (also an MCP server)", "benchmarks · demand · voice · mix · SQL", "eng") + box(680, 238, 200, 50, "Comms → each role", "Operations executes approvals", "ops");
  return '<svg viewBox="0 0 ' + W + " " + H + '" class="vz diagram" role="img" aria-label="Agent team architecture">' + g + "</svg>";
}

function bindEnterprise(v) {
  var E = v.ent;
  var showRole = function (i) { var el = $("#rolebody"); if (el) el.textContent = (E.briefs[i] || {}).message || ""; };
  showRole(0);
  var rs = $("#roles"); if (rs) rs.onclick = function (e) { var t = e.target.closest("button"); if (!t) return; rs.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-selected", x === t); }); showRole(+t.dataset.i); };
  $("#mk").onchange = function (e) { window.__gosMarket = e.target.value; var y = scrollY; renderEnterprise(v); scrollTo(0, y); };
  $("#bm").onclick = function (e) { var t = e.target.closest("button"); if (!t) return; window.__gosBench = t.dataset.k; var y = scrollY; renderEnterprise(v); scrollTo(0, y); };
  $("#cv").onchange = function (e) { window.__gosCurve = e.target.value.replace(" · ", "|"); var y = scrollY; renderEnterprise(v); scrollTo(0, y); };
  var decide = function (card, how, reason) {
    var out = card.querySelector(".out"), d = JSON.parse(out.dataset.ok), c = d.c || {};
    card.querySelector(".act").hidden = true; out.hidden = false; card.classList.add(how === "approve" ? "approved" : "rejected");
    out.innerHTML = how === "approve" ? '<ol class="steps"><li class="info">Replay of the recorded run: what happened when the owner approved it in the sandbox</li><li class="ok">Guardrails checked: verified role, four eyes on risky changes, budget caps, kill switch</li>' +
      (d.exec || []).map(function (e) { return '<li class="' + (e.status === "executed" ? "ok" : "no") + '">' + (e.status === "executed" ? "Executed: " : "Held by a guardrail: ") + esc(e.detail) + "</li>"; }).join("") + '<li class="ok">Quarter simulated against the baseline</li></ol>' +
      (d.sim ? '<div class="res"><div><span class="l">Revenue</span><b class="' + (c.revenue >= 0 ? "pos" : "neg") + '">' + sgn(c.revenue, eurS) + '</b></div><div><span class="l">Gross profit</span><b class="' + (c.gross_profit >= 0 ? "pos" : "neg") + '">' + sgn(c.gross_profit, eurS) + '</b></div><div><span class="l">Spend</span><b>' + sgn(c.spend, eurS) + "</b></div></div>" : '<p class="sub">Executed and tracked; its effect is not simulated (see assumptions).</p>')
      : '<ol class="steps"><li class="no">Rejected: “' + esc(reason) + '”</li><li class="ok">Nothing executed. The reason is stored and the next run reads it.</li>' + (d.sim ? '<li class="info">Not acting forgoes ' + sgn(c.gross_profit, eurS) + " gross profit this quarter (simulated).</li>" : "") + "</ol>";
  };
  $("#view").onclick = function (e) {
    var btn = e.target.closest("[data-do]"); if (!btn) return; var card = btn.closest(".dec");
    if (btn.dataset.do === "approve") return decide(card, "approve");
    if (btn.dataset.do === "reject") { var out = card.querySelector(".out"); out.hidden = false; out.innerHTML = '<div class="rej"><label>Why? The next run reads this.<select>' + ["Not now: a promotion is running", "Disagree with the evidence", "Too risky this quarter", "Already handled outside the system"].map(function (o) { return "<option>" + o + "</option>"; }).join("") + '</select></label><button class="btn" data-do="confirm-reject">Confirm rejection</button></div>'; }
    if (btn.dataset.do === "confirm-reject") decide(card, "reject", card.querySelector("select").value);
  };
  bindDeck(E);
}

// ---- Decision deck: the visitor approves or rejects the AI's decisions and the simulated quarter follows ----
// Numbers come only from saved runs (see deck.js for which run backs each state). Agent text is escaped everywhere.
var DK = { state: null, live: null };
var DK_NOTE = "In the live loop a rejection needs a reason, and nothing runs.";

function heldOut() {
  var runs = (DATA.evals || []).filter(function (e) { return e.scenario === "team-enterprise" && e.split === "heldout"; });
  return runs.length ? runs[runs.length - 1] : null;
}

function eurF(v) { return Math.round(v) === 0 ? "€0" : sgn(Math.round(v), function (x) { return "€" + fmt(x); }); }

function deckHowToRead(E) {
  var D = E.deck, ho = heldOut();
  if (!D) return "";
  return '<details class="howto"><summary>How to read this number</summary><p>' +
    (ho ? "The fairer read first: on three businesses the agents never saw, the team passed " + ho.passed + " of " + ho.criteria +
      " checks and gross profit rose " + ho.gross_profit_pct.map(function (x) { return x.toFixed(1) + "%"; }).join(", ") + " (simulated). " : "") +
    "This business and its situations were planted on purpose, so its uplift is an upper bound for a business built to contain them. Here the gain is " +
    D.share_of_gross_profit_pct.toFixed(1) + "% of the quarter's gross profit and equals " + D.share_of_spend_pct.toFixed(1) + "% of its marketing spend.</p></details>";
}

function deckShell(E) {
  var D = E.deck, ho = heldOut();
  if (!D || !D.cards) {
    console.warn("Decision deck data missing: ent.deck is absent from the data block. Rebuild with growth-os console (it needs reports/outcomes-loo-enterprise-7.json).");
    return '<div class="card glass"><h3>Decision deck data missing</h3><p class="sub">This build has no decision deck. The rest of the console is unaffected.</p></div>';
  }
  return '<div class="deck-wrap" id="deck">' +
    '<div class="card glass deck-frame"><span class="chip">Simulated</span><h3>Try it: the AI\'s decisions, a simulated quarter</h3>' +
    "<p>A synthetic 12-market business. The AI team proposed these decisions for one quarter" +
    (ho ? "; on three businesses it never saw it passed " + ho.passed + " of " + ho.criteria + " checks" : "") + ".</p>" +
    "<p>Approve or reject each one and the panel re-runs the simulated quarter.</p>" +
    (D.stale ? '<p class="warn-line">Built from stale leave-one-out runs: not for release.</p>' : "") +
    '<div class="act"><button class="btn" id="dk-all" type="button">Approve all</button><button class="btn" id="dk-none" type="button">Reject all</button><button class="btn" id="dk-reset" type="button">Reset to the AI\'s plan</button></div></div>' +
    '<div class="deck"><div class="deck-cards" id="dk-cards"></div><aside class="deck-panel glass" id="dk-panel"></aside></div>' +
    '<p class="deck-end">See what happens after Approve: <a href="https://djcrafted.com/work/growth-os/#trace">one decision traced from signal to audit line</a> · <a href="#s-technical">the held-out eval</a></p></div>';
}

function deckCard(D, c, rejectAll) {
  var on = DK.state[c.id] !== false, b = on ? null : GosDeck.beat(D, DK.state, c.id), nid = "dk-note-" + c.id;
  var money = c.priced ? '<span class="money ' + (c.alone.gross_profit >= 0 ? "pos" : "neg") + '">' + sgn(c.alone.gross_profit, eurS) + " <small>gross profit, measured alone</small></span>"
    : '<span class="money muted">Not priced in the simulation</span>';
  return '<article class="dk-card glass' + (on ? "" : " rej") + '" data-id="' + c.id + '">' +
    '<div class="dk-top"><span class="num">#' + String(c.rank).padStart(2, "0") + '</span><span class="chip">' + esc(c.role) + "</span>" +
    (c.risk === "high" ? '<span class="chip warn">In the live loop this needs a second approver</span>' : "") + "</div>" +
    '<p class="dk-act" tabindex="0" title="Show all">' + esc(c.action) + "</p>" +
    '<div class="dk-bot">' + money + '<span class="dk-seg" role="group" aria-label="Decision ' + c.rank + '">' +
    '<button type="button" class="ap" data-v="1" aria-pressed="' + on + '">✓ Approve</button>' +
    '<button type="button" class="rj" data-v="0" aria-pressed="' + !on + '"' + (on || rejectAll ? "" : ' aria-describedby="' + nid + '"') + ">✕ Reject</button></span></div>" +
    (b != null ? '<p class="dk-beat">Rejecting this beat the AI by ' + eurF(b) + " (measured).</p>" : "") +
    (!on && !rejectAll ? '<p class="dk-note" id="' + nid + '">' + DK_NOTE + "</p>" : "") + "</article>";
}

function deckPanel(D, t, rejectAll) {
  var winner = D.beat_the_ai.length > 0, label = t.measured ? "vs the AI (measured run)" : "≈ vs the AI (sum of single runs)";
  var cmp = winner ? '<span class="basis">' + label + ": <b>" + (Math.abs(t.vs_ai) < 0.5 ? "no change" : eurF(t.vs_ai)) + "</b></span>"
    : '<span class="basis">What your judgement changed: <b>' + (Math.abs(t.vs_ai) < 0.5 ? "no change" : eurF(t.vs_ai)) + "</b> vs approving everything" + (t.measured ? "" : " (≈)") + "</span>";
  var max = Math.max.apply(null, D.priced.map(function (id) { return Math.abs(D.cards.filter(function (c) { return c.id === id; })[0].alone.gross_profit); }).concat([1]));
  var bar = function (lab, v, cls) { return '<div class="dk-bar"><span class="lab">' + esc(lab) + '</span><span class="track"><i class="' + cls + '" style="width:' + Math.max(1, 100 * Math.abs(v) / max).toFixed(1) + '%"></i></span><span class="v">' + sgn(v, eurS) + "</span></div>"; };
  var rows = t.bars.slice().sort(function (a, b) { return b.change.gross_profit - a.change.gross_profit; }).map(function (x) {
    var c = D.cards.filter(function (k) { return k.id === x.id; })[0];
    return bar("#" + String(c.rank).padStart(2, "0") + " " + c.action, x.change.gross_profit, x.change.gross_profit >= 0 ? "pos" : "neg");
  }).join("");
  rows += t.interaction ? bar("Interaction between decisions", t.interaction.gross_profit, "int") : (t.family === "approx" ? '<p class="sub">Interaction: not measured for this combination.</p>' : "");
  return '<div class="l">Your quarter: gross profit after marketing</div><div class="big ' + (t.change.gross_profit >= 0 ? "pos" : "neg") + '">' + (t.measured ? "" : "≈ ") + eurF(t.change.gross_profit) + "</div>" + cmp +
    (t.measured ? "" : '<details class="howto"><summary>Why ≈?</summary><p>Decisions interact; this combination wasn\'t run, so single-decision effects are added.</p></details>') +
    '<button type="button" class="btn dk-more" id="dk-more" aria-expanded="false">Details</button><div class="dk-detail">' +
    '<div class="kv"><span>Revenue</span><b>' + (t.measured ? "" : "≈ ") + eurF(t.change.revenue) + "</b></div>" +
    '<div class="kv"><span>Marketing spend</span><b>' + (t.measured ? "" : "≈ ") + eurF(t.change.spend) + "</b></div>" +
    '<div class="kv"><span>MER</span><b>' + t.mer_before.toFixed(2) + " → " + (t.measured ? "" : "≈ ") + t.mer_after.toFixed(2) + "</b></div>" +
    '<div class="kv"><span>Approved</span><b>' + t.approved_priced + " of " + D.priced.length + " priced · " + t.approved_unpriced + " of " + (D.cards.length - D.priced.length) + " unpriced</b></div>" +
    '<div class="dk-bars">' + rows + "</div>" + (rejectAll ? '<p class="dk-note">' + DK_NOTE + "</p>" : "") +
    '<p class="sub">' + (D.cards.length - D.priced.length) + " unpriced decisions don't change these numbers. Simulated: synthetic business, measured against the team's usual process.</p></div>";
}

function deckDraw(D, rejectAll) {
  var t = GosDeck.totals(D, DK.state);
  var order = D.cards.slice().sort(function (a, b) { return (b.priced - a.priced) || ((b.alone ? b.alone.gross_profit : 0) - (a.alone ? a.alone.gross_profit : 0)) || (a.id - b.id); });
  $("#dk-cards").innerHTML = order.map(function (c) { return deckCard(D, c, rejectAll); }).join("");
  $("#dk-panel").innerHTML = deckPanel(D, t, rejectAll);
  clearTimeout(DK.live);
  DK.live = setTimeout(function () {
    var el = $("#dk-announce");
    if (el) el.textContent = "Gross profit " + (t.measured ? "" : "approximately ") + eurF(t.change.gross_profit) + ", " + (t.measured ? "measured run" : "sum of single runs");
  }, 300);
}

function bindDeck(E) {
  var D = E.deck;
  if (!D || !D.cards || !$("#dk-cards")) return;
  if (!$("#dk-announce")) { var a = document.createElement("div"); a.id = "dk-announce"; a.className = "sr-only"; a.setAttribute("aria-live", "polite"); document.body.appendChild(a); }
  DK.state = DK.state || GosDeck.aiPlan(D);
  var all = function (v, rejectAll) { D.cards.forEach(function (c) { DK.state[c.id] = v; }); deckDraw(D, rejectAll); };
  deckDraw(D, false);
  $("#dk-cards").onclick = function (e) {
    var act = e.target.closest(".dk-act"); if (act) { act.classList.toggle("open"); return; }
    var b = e.target.closest("button[data-v]"); if (!b) return;
    DK.state[+b.closest(".dk-card").dataset.id] = b.dataset.v === "1";
    deckDraw(D, false);
  };
  $("#dk-panel").onclick = function (e) {
    var m = e.target.closest("#dk-more"); if (!m) return;
    var open = $("#dk-panel").classList.toggle("open"); m.setAttribute("aria-expanded", open);
  };
  $("#dk-all").onclick = function () { all(true, false); };
  $("#dk-none").onclick = function () { all(false, true); };
  $("#dk-reset").onclick = function () { DK.state = GosDeck.aiPlan(D); deckDraw(D, false); };
}
