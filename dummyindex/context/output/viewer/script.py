"""Behaviour for the `features/graph.html` scan viewer.

Zero dependencies, on purpose. The previous viewer pulled D3 from a CDN and
`fetch()`ed `graph.json`, which meant it only worked online *and* only when
served — opening the file printed an error telling you to go start a web
server. A scan is something you glance at; anything that stands between the
double-click and the map defeats it. So: no CDN, no fetch, no build step.
The data is inlined into the document and the layout is ~40 lines of
arithmetic instead of a physics simulation.

Deterministic layout beats force-directed here for the same reason the
artifact is capped at 60 nodes: a curated map has an intended reading
order, and a simulation destroys it by scattering the nodes differently on
every load. Nodes flow left to right through four tiers — what triggers
work, what runs it, what it can call, what it stores or reaches out to —
and `group` stacks related nodes into a labelled column within its tier.
"""

from __future__ import annotations

VIEWER_JS = r"""
const SCAN = JSON.parse(document.getElementById("scan-data").textContent);
const NODES = (SCAN.graph && SCAN.graph.nodes) || [];
const EDGES = (SCAN.graph && SCAN.graph.edges) || [];

/* Which column a kind lives in: trigger → logic → capability → data. */
const TIER = {
  entry: 0, cron: 0,
  agent: 1, service: 1,
  model: 2, tool: 2,
  store: 3, external: 3,
};
const KINDS = ["entry", "cron", "agent", "service", "model", "tool", "store", "external"];

const GLYPH = {
  entry:    '<path d="M1.5 6.5h6M5 4l2.5 2.5L5 9M10.5 1.5v10"/>',
  cron:     '<circle cx="6.5" cy="6.5" r="5"/><path d="M6.5 3.6v3.1l2.1 1.5"/>',
  agent:    '<path d="M6.5 1 7.9 5.1 12 6.5 7.9 7.9 6.5 12 5.1 7.9 1 6.5 5.1 5.1z" fill="currentColor" stroke="none"/>',
  service:  '<rect x="1.5" y="2" width="10" height="3.4" rx="1.2"/><rect x="1.5" y="7.6" width="10" height="3.4" rx="1.2"/>',
  model:    '<circle cx="6.5" cy="6.5" r="2.4"/><ellipse cx="6.5" cy="6.5" rx="5.6" ry="2.5" transform="rotate(-32 6.5 6.5)"/>',
  tool:     '<path d="M9.2 1.6a3.1 3.1 0 0 0-3.7 4.1L1.7 9.5a1.25 1.25 0 1 0 1.8 1.8l3.8-3.8a3.1 3.1 0 0 0 4.1-3.7L9.6 5.9 7.2 3.5z"/>',
  store:    '<ellipse cx="6.5" cy="3.1" rx="4.9" ry="1.8"/><path d="M1.6 3.1v6.8c0 1 2.2 1.8 4.9 1.8s4.9-.8 4.9-1.8V3.1"/>',
  external: '<path d="M7 2H2.6A1.6 1.6 0 0 0 1 3.6v6.8A1.6 1.6 0 0 0 2.6 12h6.8a1.6 1.6 0 0 0 1.6-1.6V6M8.2 1.2H12v3.8M12 1.2 6.6 6.6"/>',
};

/* `kind` is model-authored and lands in a class name, a CSS custom-property
   name, and a glyph lookup. Fold it onto the closed alphabet first: an
   unknown kind then renders as a plain `service` box instead of injecting
   into `style.cssText` or silently resolving `var(--k-…)` to nothing. */
const KIND_SET = new Set(KINDS);
const safeKind = k => (KIND_SET.has(k) ? k : "service");

function glyph(kind) {
  return '<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" ' +
         'stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
         GLYPH[safeKind(kind)] + "</svg>";
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

/* ----- geometry ----------------------------------------------------------- */

const NODE_W = 196, ROW_GAP = 13, GROUP_GAP = 30, GROUP_HEAD = 19, COL_GAP = 128, PAD = 60;
/* Above this many rows a tier wraps into another column. Without it the
   seed's worst case — every node the same kind, so every node in one tier —
   renders as a single 26-deep column with every edge looping around it. */
const MAX_COL_ROWS = 12;
const nodeH = n => (n.sub ? 46 : 36);

const byId = new Map(NODES.map(n => [n.id, n]));
const box = new Map();          // node id → {x, y, w, h}
const groupLabels = [];         // {name, x, y}

/* Group nodes within a tier, preserving the order the author wrote them in —
   that order is a deliberate signal and re-sorting would erase it. */
function stack(nodes) {
  const groups = new Map();
  const loose = [];
  for (const n of nodes) {
    if (n.group) {
      if (!groups.has(n.group)) groups.set(n.group, []);
      groups.get(n.group).push(n);
    } else loose.push(n);
  }
  const blocks = [...groups.entries()].map(([name, ns]) => ({ name, nodes: ns }));
  if (loose.length) blocks.push({ name: null, nodes: loose });
  return blocks;
}

/* Pack a tier's blocks into columns of at most MAX_COL_ROWS rows. A group is
   never split across columns — it would stop being one labelled stack — so a
   group larger than the limit simply gets a column to itself. */
function wrap(blocks) {
  /* Ungrouped nodes are a pile, not a stack — nothing is claimed about them
     sitting together, so they chunk freely. A named group is a claim, so it
     stays whole even if that overshoots the limit. */
  const units = [];
  for (const b of blocks) {
    if (b.name) { units.push(b); continue; }
    for (let i = 0; i < b.nodes.length; i += MAX_COL_ROWS) {
      units.push({ name: null, nodes: b.nodes.slice(i, i + MAX_COL_ROWS) });
    }
  }

  const columns = [];
  let current = [], rows = 0;
  for (const u of units) {
    if (current.length && rows + u.nodes.length > MAX_COL_ROWS) {
      columns.push(current);
      current = []; rows = 0;
    }
    current.push(u);
    rows += u.nodes.length;
  }
  if (current.length) columns.push(current);
  return columns;
}

/* A group is meant to read as one labelled stack, so the group owns the
   column, not the kind: an "Ingestion" group holding two agents and the
   index they write to stays together instead of being torn across three
   tiers. The group's first node in author order picks the column — author
   order is reading order, and it is the only signal that says which of a
   mixed group's kinds is the one the group is *about*. */
function columnOf(node, groupTier) {
  if (node.group && groupTier.has(node.group)) return groupTier.get(node.group);
  return TIER[node.kind] != null ? TIER[node.kind] : 1;
}

function layout() {
  const groupTier = new Map();
  for (const n of NODES) {
    if (n.group && !groupTier.has(n.group)) {
      groupTier.set(n.group, TIER[n.kind] != null ? TIER[n.kind] : 1);
    }
  }

  const cols = [[], [], [], []];
  for (const n of NODES) cols[columnOf(n, groupTier)].push(n);
  const active = cols.filter(c => c.length).flatMap(nodes => wrap(stack(nodes)));

  const measured = active.map(blocks => {
    let h = 0;
    for (const b of blocks) {
      if (b.name) h += GROUP_HEAD;
      for (const n of b.nodes) h += nodeH(n) + ROW_GAP;
      h += GROUP_GAP;
    }
    return { blocks, height: h - GROUP_GAP - ROW_GAP };
  });

  const tallest = Math.max(0, ...measured.map(c => c.height));
  measured.forEach((col, i) => {
    const x = i * (NODE_W + COL_GAP);
    let y = (tallest - col.height) / 2;
    for (const b of col.blocks) {
      if (b.name) { groupLabels.push({ name: b.name, x, y: y + 4 }); y += GROUP_HEAD; }
      for (const n of b.nodes) {
        box.set(n.id, { x, y, w: NODE_W, h: nodeH(n) });
        y += nodeH(n) + ROW_GAP;
      }
      y += GROUP_GAP;
    }
  });

  /* Shift everything positive so the canvas has no negative coordinates. */
  const xs = [...box.values()];
  const minY = Math.min(0, ...xs.map(b => b.y), ...groupLabels.map(g => g.y));
  for (const b of box.values()) { b.x += PAD; b.y += PAD - minY; }
  for (const g of groupLabels) { g.x += PAD; g.y += PAD - minY; }

  return {
    w: Math.max(...xs.map(b => b.x + b.w), 0) + PAD,
    h: Math.max(...xs.map(b => b.y + b.h), 0) + PAD,
  };
}

/* A wire leaves the right edge and enters the left edge. Back-edges reverse
   that; same-column edges bulge out to the right so they don't cut through
   the nodes stacked between them. */
function wirePath(a, b) {
  const ay = a.y + a.h / 2, by = b.y + b.h / 2;
  if (Math.abs(a.x - b.x) < 1) {
    const x1 = a.x + a.w, x2 = b.x + b.w, d = 34 + Math.abs(by - ay) * 0.34;
    return `M${x1},${ay} C${x1 + d},${ay} ${x2 + d},${by} ${x2},${by}`;
  }
  const fwd = b.x > a.x;
  const x1 = fwd ? a.x + a.w : a.x;
  const x2 = fwd ? b.x : b.x + b.w;
  const d = Math.max(38, Math.abs(x2 - x1) * 0.45) * (fwd ? 1 : -1);
  return `M${x1},${ay} C${x1 + d},${ay} ${x2 - d},${by} ${x2},${by}`;
}

/* ----- render ------------------------------------------------------------- */

const stage = document.getElementById("stage");
const canvas = document.getElementById("canvas");
const wires = document.getElementById("wires");
const aside = document.getElementById("detail");
const SVGNS = "http://www.w3.org/2000/svg";

const size = layout();
/* What `fit()` fits to. Tier 1's extent by default; the community overview
   (tiers.py) swaps its own extent in when that mode is active. */
const view = { w: size.w, h: size.h };
canvas.style.width = size.w + "px";
canvas.style.height = size.h + "px";
wires.setAttribute("width", size.w);
wires.setAttribute("height", size.h);
wires.setAttribute("viewBox", `0 0 ${size.w} ${size.h}`);

for (const g of groupLabels) {
  const el = document.createElement("div");
  el.className = "grouplabel";
  el.textContent = g.name;
  el.style.left = g.x + "px";
  el.style.top = g.y + "px";
  canvas.appendChild(el);
}

/* Declared before the first click listener binds: top-level order is
   execution order, so a `let` below the binding would leave every click
   dying in the temporal dead zone if anything later in init throws — a
   rendered map that ignores all clicks. */
let selected = null;

const nodeEls = new Map();
for (const n of NODES) {
  const b = box.get(n.id);
  const el = document.createElement("div");
  const kind = safeKind(n.kind);
  el.className = `node k-${kind}`;
  el.style.cssText =
    `left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px;--kind:var(--k-${kind})`;
  el.dataset.id = n.id;
  el.innerHTML =
    `<span class="glyph">${glyph(n.kind)}</span><span class="text">` +
    `<span class="label">${esc(n.label)}</span>` +
    (n.sub ? `<span class="sub">${esc(n.sub)}</span>` : "") +
    "</span>";
  el.addEventListener("click", ev => { ev.stopPropagation(); select(n.id); });
  canvas.appendChild(el);
  nodeEls.set(n.id, el);
}

/* Only edges whose endpoints both exist get drawn. `scan-check` rejects a
   dangling edge, but a viewer that throws on one is a viewer that shows
   nothing when the map is 95% fine. */
const wireEls = [];
EDGES.forEach((e, i) => {
  const a = box.get(e.from), b = box.get(e.to);
  if (!a || !b) return;
  const path = document.createElementNS(SVGNS, "path");
  path.setAttribute("class", "wire");
  path.setAttribute("d", wirePath(a, b));
  wires.appendChild(path);

  let label = null;
  const text = e.label || e.kind;
  if (text) {
    /* Curve geometry is decoration and engines disagree about it: Firefox
       throws for paths it has not rendered and jsdom has no implementation
       at all. This runs mid-init, so trusting it turns a cosmetic failure
       into a dead viewer. Prefer the true curve midpoint, fall back to the
       straight-line midpoint of the endpoint boxes. */
    let mid = { x: (a.x + a.w / 2 + b.x + b.w / 2) / 2,
                y: (a.y + a.h / 2 + b.y + b.h / 2) / 2 };
    try {
      const len = path.getTotalLength();
      mid = path.getPointAtLength(len / 2);
    } catch { /* box midpoint stands */ }
    label = document.createElementNS(SVGNS, "text");
    label.setAttribute("class", "wirelabel" + (e.label ? "" : " verb"));
    label.setAttribute("x", mid.x);
    label.setAttribute("y", mid.y - 4);
    label.textContent = text;
    wires.appendChild(label);
  }
  wireEls.push({ edge: e, index: i, path, label });
});

/* ----- pan + zoom --------------------------------------------------------- */

let tx = 0, ty = 0, k = 1;
/* Set the moment the reader pans or zooms. After that the viewport is
   theirs: a window resize re-fits a map nobody has touched, but it must
   not throw away the corner someone deliberately navigated to. */
let userMoved = false;
const apply = () => { canvas.style.transform = `translate(${tx}px,${ty}px) scale(${k})`; };

function fit() {
  const r = stage.getBoundingClientRect();
  /* The banner floats over the top of the stage, so when it is showing the
     map has to be fitted into what is left underneath it. */
  const top = banner && !banner.classList.contains("hidden")
    ? banner.getBoundingClientRect().height + 24
    : 0;
  const usable = Math.max(120, r.height - top);
  k = Math.min(1, (r.width - 24) / view.w, (usable - 24) / view.h) || 1;
  k = Math.max(k, 0.2);
  tx = (r.width - view.w * k) / 2;
  ty = top + (usable - view.h * k) / 2;
  apply();
}

stage.addEventListener("wheel", ev => {
  ev.preventDefault();
  const r = stage.getBoundingClientRect();
  const px = ev.clientX - r.left, py = ev.clientY - r.top;
  const next = Math.min(2.6, Math.max(0.18, k * Math.exp(-ev.deltaY * 0.0016)));
  userMoved = true;
  tx = px - (px - tx) * (next / k);
  ty = py - (py - ty) * (next / k);
  k = next;
  apply();
}, { passive: false });

let drag = null;
stage.addEventListener("pointerdown", ev => {
  if (ev.button !== 0) return;
  drag = { x: ev.clientX - tx, y: ev.clientY - ty, moved: false };
  stage.classList.add("panning");
  stage.setPointerCapture(ev.pointerId);
});
stage.addEventListener("pointermove", ev => {
  if (!drag) return;
  tx = ev.clientX - drag.x; ty = ev.clientY - drag.y;
  drag.moved = true;
  userMoved = true;
  apply();
});
stage.addEventListener("pointerup", ev => {
  const wasDrag = drag && drag.moved;
  drag = null;
  stage.classList.remove("panning");
  if (!wasDrag) select(null);
});

/* ----- selection + trace -------------------------------------------------- */

function reachable(startId) {
  const nodesHot = new Set([startId]);
  const edgesHot = new Set();
  for (const dir of ["out", "in"]) {
    const queue = [startId];
    const seen = new Set([startId]);
    while (queue.length) {
      const cur = queue.shift();
      wireEls.forEach(w => {
        const near = dir === "out" ? w.edge.from : w.edge.to;
        const far = dir === "out" ? w.edge.to : w.edge.from;
        if (near !== cur || seen.has(far)) return;
        seen.add(far);
        nodesHot.add(far);
        edgesHot.add(w.index);
        queue.push(far);
      });
      /* Edges into/out of `cur` that loop back to an already-seen node still
         belong to the trace — otherwise a cycle renders with a gap in it. */
      wireEls.forEach(w => {
        if ((dir === "out" ? w.edge.from : w.edge.to) === cur) edgesHot.add(w.index);
      });
    }
  }
  return { nodesHot, edgesHot };
}

function select(id) {
  selected = id && byId.has(id) ? id : null;
  for (const [nid, el] of nodeEls) el.classList.toggle("selected", nid === selected);

  if (!selected) {
    stage.classList.remove("traced");
    nodeEls.forEach(el => el.classList.remove("hot"));
    wireEls.forEach(w => {
      w.path.classList.remove("hot", "dim");
      if (w.label) w.label.classList.remove("hot", "dim");
    });
    renderEmptyPanel();
    return;
  }

  const { nodesHot, edgesHot } = reachable(selected);
  stage.classList.add("traced");
  nodeEls.forEach((el, nid) => el.classList.toggle("hot", nodesHot.has(nid)));
  wireEls.forEach(w => {
    const hot = edgesHot.has(w.index);
    w.path.classList.toggle("hot", hot);
    w.path.classList.toggle("dim", !hot);
    if (w.label) {
      w.label.classList.toggle("hot", hot);
      w.label.classList.toggle("dim", !hot);
    }
  });
  renderPanel(byId.get(selected));
}

function renderEmptyPanel() {
  aside.classList.add("empty-state");
  aside.innerHTML =
    '<p class="empty">Click a node to trace what it reaches and what reaches it.' +
    "<br><br>Drag to pan, scroll to zoom, <b>F</b> to fit, <b>/</b> to search, " +
    "<b>Esc</b> to clear.</p>";
}

function connections(id) {
  const out = [], inc = [];
  for (const w of wireEls) {
    if (w.edge.from === id) out.push({ other: w.edge.to, edge: w.edge });
    if (w.edge.to === id) inc.push({ other: w.edge.from, edge: w.edge });
  }
  return { out, inc };
}

function connList(title, items, verbOf) {
  if (!items.length) return "";
  const rows = items.map(it => {
    const other = byId.get(it.other);
    return '<li><button data-goto="' + esc(it.other) + '">' +
      '<span class="verb">' + esc(verbOf(it.edge)) + "</span>" +
      "<span>" + esc(other ? other.label : it.other) +
      (it.edge.label ? ' <span class="edgenote">— ' + esc(it.edge.label) + "</span>" : "") +
      "</span></button></li>";
  }).join("");
  return "<h3>" + title + "</h3><ul>" + rows + "</ul>";
}

function renderPanel(n) {
  const { out, inc } = connections(n.id);
  aside.classList.remove("empty-state");
  aside.innerHTML =
    '<div style="--kind:var(--k-' + safeKind(n.kind) + ')">' +
    "<h2>" + esc(n.label) + "</h2>" +
    '<div class="kindtag">' + glyph(n.kind) + esc(n.kind) +
      (n.group ? " · " + esc(n.group) : "") +
      (n.evidence ? " · " + esc(n.evidence) : "") + "</div>" +
    (n.sub ? '<p class="detail-text mono">' + esc(n.sub) + "</p>" : "") +
    (n.detail ? '<p class="detail-text">' + esc(n.detail) + "</p>" : "") +
    (n.sourceRef ? '<code class="ref">' + esc(n.sourceRef) + "</code>" : "") +
    (n.domain ? '<code class="ref">' + esc(n.domain) + "</code>" : "") +
    connList("Reaches", out, e => e.kind || "→") +
    connList("Reached by", inc, e => e.kind || "←") +
    "</div>";
  aside.querySelectorAll("[data-goto]").forEach(b =>
    b.addEventListener("click", () => select(b.dataset.goto)));
}

/* ----- search + legend ---------------------------------------------------- */

const search = document.getElementById("search");
search.addEventListener("input", () => {
  const q = search.value.trim().toLowerCase();
  nodeEls.forEach((el, id) => {
    if (!q) return el.classList.remove("searchhide");
    const n = byId.get(id);
    const hay = [n.label, n.sub, n.detail, n.sourceRef, n.domain, n.group, n.kind]
      .filter(Boolean).join(" ").toLowerCase();
    el.classList.toggle("searchhide", !hay.includes(q));
  });
});

const hiddenKinds = new Set();
function applyKinds() {
  nodeEls.forEach((el, id) => {
    el.classList.toggle("hidden", hiddenKinds.has(byId.get(id).kind));
  });
  wireEls.forEach(w => {
    const a = byId.get(w.edge.from), b = byId.get(w.edge.to);
    const off = (a && hiddenKinds.has(a.kind)) || (b && hiddenKinds.has(b.kind));
    w.path.classList.toggle("hidden", off);
    if (w.label) w.label.classList.toggle("hidden", off);
  });
}

const legend = document.getElementById("legend");
const present = KINDS.filter(kind => NODES.some(n => n.kind === kind));
legend.innerHTML = present.map(kind =>
  '<span class="item" data-kind="' + kind + '" style="--kind:var(--k-' + kind + ')">' +
  '<span class="dot"></span>' + kind + "</span>").join("");
legend.querySelectorAll("[data-kind]").forEach(el => {
  el.addEventListener("click", () => {
    const kind = el.dataset.kind;
    hiddenKinds.has(kind) ? hiddenKinds.delete(kind) : hiddenKinds.add(kind);
    el.classList.toggle("off", hiddenKinds.has(kind));
    applyKinds();
  });
});

/* ----- header ------------------------------------------------------------- */

function monogram(text) {
  const words = String(text || "?").trim().split(/[\s\-_/.]+/).filter(Boolean);
  const pair = words.length > 1 ? words[0][0] + words[1][0] : String(text || "?").slice(0, 2);
  return pair.toUpperCase();
}

const project = SCAN.project || {};
if (project.name) {
  document.getElementById("project-name").textContent = project.name;
  document.title = project.name + " · codebase scan";
}
document.getElementById("project-tagline").textContent =
  [project.tagline, project.date].filter(Boolean).join(" · ");

const stats = SCAN.stats || {};
document.getElementById("stats").innerHTML = [
  ["agents", stats.agents], ["models", stats.models],
  ["tools", stats.tools], ["integrations", stats.integrations],
].filter(([, v]) => v)
 .concat([["nodes", NODES.length], ["edges", EDGES.length]])
 .map(([label, v]) => `<span class="stat"><b>${esc(v)}</b>${label}</span>`)
 .join("");

const chiprows = document.getElementById("chiprows");
const rowsHtml = [["topModels", "models"], ["topTools", "tools"], ["topIntegrations", "integrations"]]
  .map(([key, label]) => {
    const items = SCAN[key] || [];
    if (!items.length) return "";
    return '<div class="chiprow"><span class="label">' + label + "</span>" +
      items.map(c =>
        '<span class="chip"><span class="mono-dot">' + esc(monogram(c.label)) + "</span>" +
        esc(c.label) +
        (c.domain ? '<span class="host">' + esc(c.domain) + "</span>" : "") +
        "</span>").join("") +
      "</div>";
  }).join("");
if (rowsHtml) chiprows.innerHTML = rowsHtml; else chiprows.classList.add("hidden");

/* The seed is a real map, but it is a map of shape, not of meaning. Say so
   rather than letting someone mistake `12 files · 3 flows` for a summary. */
const banner = document.getElementById("banner");
if (!NODES.length) {
  banner.innerHTML =
    "<b>No scan yet.</b> Run <code>dummyindex ingest</code> to build the " +
    "deterministic seed, then curate it.";
  banner.classList.remove("hidden");
} else if (SCAN.confidence !== "INFERRED") {
  banner.innerHTML =
    "<b>Deterministic seed.</b> Every feature is a <code>service</code> and every " +
    "flow an <code>entry</code> — nothing here knows what the code is <i>for</i> yet. " +
    "Run <code>/dummyindex</code> (Claude) or <code>$dummyindex</code> (Codex) to " +
    "author the curated scan.";
  banner.classList.remove("hidden");
}

/* ----- theme + keys ------------------------------------------------------- */

const root = document.documentElement;
const stored = (() => { try { return localStorage.getItem("dummyindex-scan-theme"); } catch { return null; } })();
if (stored) root.setAttribute("data-theme", stored);
document.getElementById("theme").addEventListener("click", () => {
  const dark = getComputedStyle(root).colorScheme !== "light";
  const next = dark ? "light" : "dark";
  root.setAttribute("data-theme", next);
  try { localStorage.setItem("dummyindex-scan-theme", next); } catch {}
});

/* Fit is the explicit way back to the whole map, so it also hands the
   viewport back to auto-fit. */
document.getElementById("fit").addEventListener("click", () => { userMoved = false; fit(); });

document.addEventListener("keydown", ev => {
  if (ev.key === "/" && document.activeElement !== search) { ev.preventDefault(); search.focus(); }
  else if (ev.key === "Escape") { search.value = ""; search.dispatchEvent(new Event("input")); search.blur(); select(null); }
  else if ((ev.key === "f" || ev.key === "F") && document.activeElement !== search) { userMoved = false; fit(); }
});

window.addEventListener("resize", () => { if (!userMoved) fit(); });

renderEmptyPanel();
fit();
"""
