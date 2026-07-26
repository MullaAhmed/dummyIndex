"""Tier-2/tier-3 behaviour for the scan viewer (community overview + expand).

Appended after `script.VIEWER_JS` inside the same `<script>` element, so it
shares that module's top-level scope — `esc`, `wirePath`, `box`, `byId`,
`nodeEls`, `select`, `view`, `fit` and friends are all in reach without any
export machinery, keeping the document dependency-free.

Reads the second data island (`graph-extras`): community cards, cross-
community call volume, and the bounded expansion index precomputed by
`extras.py`. Both payloads are model/extraction-derived and therefore
untrusted at render time — every string that lands in HTML goes through
`esc()`, and every value that lands in a class name is folded onto a
closed alphabet first, the same discipline `safeKind` established.
"""

from __future__ import annotations

VIEWER_TIERS_JS = r"""
/* ----- extras island: tiers 2 + 3 ---------------------------------------- */

const EXTRAS = (() => {
  try {
    return JSON.parse(document.getElementById("graph-extras").textContent) || {};
  } catch { return {}; }
})();
const COMMUNITIES = Array.isArray(EXTRAS.communities) ? EXTRAS.communities : [];
const COMMUNITY_LINKS = Array.isArray(EXTRAS.communityLinks) ? EXTRAS.communityLinks : [];
const EXPANSION =
  EXTRAS.expansion && typeof EXTRAS.expansion === "object" ? EXTRAS.expansion : {};

/* `evidence` is model-authored and lands in a class name; `relation` comes
   from the extraction and lands in the ghost's verb slot. Fold both onto
   closed alphabets before they touch markup — same discipline as safeKind. */
const EVIDENCE_SET = new Set(["EXTRACTED", "INFERRED"]);
const safeEvidence = e => (EVIDENCE_SET.has(e) ? e.toLowerCase() : null);
const RELATION_SET = new Set(["calls", "uses", "contains", "imports_from", "inherits", "method"]);
const safeRelation = r => (RELATION_SET.has(r) ? r.replace("_", " ") : "related");

/* EXTRACTED renders solid (the default border), INFERRED dashed. A scan
   without the field gets no class and renders exactly as before. */
nodeEls.forEach((el, id) => {
  const ev = safeEvidence(byId.get(id).evidence);
  if (ev) el.classList.add("ev-" + ev);
});

/* ----- tier 2: community overview ----------------------------------------- */

const COMM_W = 216, COMM_H = 46, COMM_GAP_X = 150, COMM_GAP_Y = 14;
const commBox = new Map();      // slug → {x, y, w, h}
const commEls = new Map();      // slug → element
const commWireEls = [];         // {link, path}
let commSize = { w: 0, h: 0 };
let commMode = false;
let commSelected = null;
const commSvg = document.createElementNS(SVGNS, "svg");
commSvg.id = "comm-wires";

/* Largest communities first — the overview is a weight map, not an index. */
function layoutCommunities() {
  const order = COMMUNITIES
    .filter(c => c && typeof c.slug === "string")
    .sort((a, b) => (Number(b.size) || 0) - (Number(a.size) || 0) ||
                    (a.slug < b.slug ? -1 : a.slug > b.slug ? 1 : 0));
  order.forEach((c, i) => {
    commBox.set(c.slug, {
      x: PAD + Math.floor(i / MAX_COL_ROWS) * (COMM_W + COMM_GAP_X),
      y: PAD + (i % MAX_COL_ROWS) * (COMM_H + COMM_GAP_Y),
      w: COMM_W, h: COMM_H,
    });
  });
  const boxes = [...commBox.values()];
  commSize = {
    w: Math.max(0, ...boxes.map(b => b.x + b.w)) + PAD,
    h: Math.max(0, ...boxes.map(b => b.y + b.h)) + PAD,
  };
  return order;
}

function renderCommunities() {
  const order = layoutCommunities();
  commSvg.setAttribute("width", commSize.w);
  commSvg.setAttribute("height", commSize.h);
  commSvg.setAttribute("viewBox", `0 0 ${commSize.w} ${commSize.h}`);
  canvas.appendChild(commSvg);

  for (const l of COMMUNITY_LINKS) {
    const a = commBox.get(l.from), b = commBox.get(l.to);
    if (!a || !b) continue;
    const path = document.createElementNS(SVGNS, "path");
    path.setAttribute("class", "wire commwire");
    path.setAttribute("d", wirePath(a, b));
    /* Call volume → stroke weight. Coerced to a number before any math, so
       the only thing that ever reaches the style is arithmetic output. */
    const w = Math.max(1, Number(l.weight) || 1);
    path.style.strokeWidth = Math.min(5, 1 + Math.log2(1 + w)).toFixed(2) + "px";
    commSvg.appendChild(path);
    commWireEls.push({ link: l, path });
  }

  for (const c of order) {
    const b = commBox.get(c.slug);
    const el = document.createElement("div");
    el.className = "node commnode";
    el.style.cssText =
      `left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px;--kind:var(--k-service)`;
    const size = Number(c.size) || 0;
    el.innerHTML =
      '<span class="text">' +
      `<span class="label">${esc(c.slug)}</span>` +
      `<span class="sub">${esc(size + " symbols" + (c.feature ? " · " + c.feature : ""))}</span>` +
      "</span>";
    el.addEventListener("click", ev => { ev.stopPropagation(); selectCommunity(c.slug); });
    canvas.appendChild(el);
    commEls.set(c.slug, el);
  }
}
if (COMMUNITIES.length) renderCommunities();

function selectCommunity(slug) {
  commSelected = slug != null && commEls.has(slug) ? slug : null;
  commEls.forEach((el, s) => el.classList.toggle("selected", s === commSelected));
  commWireEls.forEach(w => {
    const hot = commSelected != null &&
      (w.link.from === commSelected || w.link.to === commSelected);
    w.path.classList.toggle("hot", hot);
    w.path.classList.toggle("dim", commSelected != null && !hot);
  });
  if (commSelected == null) {
    if (commMode) renderEmptyPanel();
    return;
  }
  const card = COMMUNITIES.find(c => c && c.slug === commSelected);
  if (card) renderCommunityPanel(card);
}

function renderCommunityPanel(c) {
  aside.classList.remove("empty-state");
  const members = Array.isArray(c.members) ? c.members : [];
  const rows = members.map(m => {
    const member = m && typeof m === "object" ? m : {};
    return '<li class="member"><span>' + esc(member.label) + "</span>" +
      (member.path ? '<code class="ref">' + esc(member.path) + "</code>" : "") +
      "</li>";
  }).join("");
  aside.innerHTML =
    '<div style="--kind:var(--k-service)">' +
    "<h2>" + esc(c.slug) + "</h2>" +
    '<div class="kindtag">community · ' + esc(Number(c.size) || members.length) +
      " symbols" + (c.feature ? " · " + esc(c.feature) : "") + "</div>" +
    (c.summary ? '<p class="detail-text">' + esc(c.summary) + "</p>" : "") +
    (rows ? "<h3>Top symbols</h3><ul>" + rows + "</ul>" : "") +
    "</div>";
}

const tiersBtn = document.getElementById("tiers");
/* No communities artifact → the toggle never appears and tier 2 stays off. */
if (COMMUNITIES.length) tiersBtn.classList.remove("hidden");

function setMode(on) {
  commMode = !!on && COMMUNITIES.length > 0;
  stage.classList.toggle("mode-communities", commMode);
  tiersBtn.textContent = commMode ? "Map" : "Communities";
  select(null);
  view.w = commMode ? commSize.w : size.w;
  view.h = commMode ? commSize.h : size.h;
  userMoved = false;
  fit();
}

tiersBtn.addEventListener("click", () => setMode(!commMode));
document.addEventListener("keydown", ev => {
  if ((ev.key === "c" || ev.key === "C") && document.activeElement !== search &&
      COMMUNITIES.length) setMode(!commMode);
});

/* ----- tier 3: focus + expand --------------------------------------------- */

const GHOST_W = 190, GHOST_H = 34, GHOST_GAP = 8, GHOST_DX = 44;
let ghostEls = [], ghostWires = [];

function collapseExpansion() {
  for (const el of ghostEls) el.remove();
  for (const p of ghostWires) p.remove();
  ghostEls = []; ghostWires = [];
}

function expansionFor(node) {
  if (!node || typeof node.symbolRef !== "string") return null;
  /* Guarded lookup: a symbolRef of `__proto__` must find nothing, not the
     prototype chain. */
  if (!Object.prototype.hasOwnProperty.call(EXPANSION, node.symbolRef)) return null;
  const entries = EXPANSION[node.symbolRef];
  return Array.isArray(entries) && entries.length ? entries : null;
}

/* Reveal the precomputed top-k symbol neighborhood beside the node. Ghosts
   are read-only annotations, so they take no pointer events and vanish the
   moment the selection moves on. */
function expandNode(id) {
  collapseExpansion();
  const n = byId.get(id), b = box.get(id);
  const entries = n && b ? expansionFor(n) : null;
  if (!entries) return;
  const x = b.x + b.w + GHOST_DX;
  let y = b.y + b.h / 2 - (entries.length * (GHOST_H + GHOST_GAP) - GHOST_GAP) / 2;
  for (const raw of entries) {
    const g = raw && typeof raw === "object" ? raw : {};
    const el = document.createElement("div");
    el.className = "ghost";
    el.style.cssText = `left:${x}px;top:${y}px;width:${GHOST_W}px;height:${GHOST_H}px`;
    el.innerHTML =
      `<span class="rel">${esc(safeRelation(g.relation))}${g.dir === "in" ? " ←" : " →"}</span>` +
      `<span class="gtext"><span class="glabel">${esc(g.label)}</span>` +
      (g.path ? `<span class="gpath">${esc(g.path)}</span>` : "") +
      "</span>";
    canvas.appendChild(el);
    ghostEls.push(el);
    const p = document.createElementNS(SVGNS, "path");
    p.setAttribute("class", "wire ghostwire");
    p.setAttribute("d", wirePath(b, { x, y, w: GHOST_W, h: GHOST_H }));
    wires.appendChild(p);
    ghostWires.push(p);
    y += GHOST_H + GHOST_GAP;
  }
}

/* Selecting a curated node is what reveals its neighborhood, so expansion
   rides on `select` rather than adding a second gesture. The base binding
   is a function declaration, so rebinding the name wraps every caller —
   node clicks, panel jumps, Escape — without touching them. */
const baseSelect = select;
select = function (id) {
  baseSelect(id);
  selectCommunity(null);
  if (selected != null && !commMode) expandNode(selected);
  else collapseExpansion();
};
"""
