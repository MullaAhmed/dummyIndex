"""The HTML viewer that ships next to `features/graph.json`.

Single ``VIEWER_HTML`` string. Loaded by ``features.py`` and written
alongside ``graph.json`` so users can ``python3 -m http.server`` inside
``.context/features/`` and explore.

Design (post-symbols rebuild):

- **Feature-grid view (default).** A clickable card per feature, sorted
  by file_count desc. Click a card to open the detail panel.
- **Force-directed view (toggle).** Folder/file/symbol/feature/flow
  layout. Kind chips in the header toggle each layer in/out — symbols
  are hidden by default since they explode the node count.
- **Detail panel.** Click a feature: shows summary, files grouped by
  class/method with ``path:line`` citations — the surgical-update
  signal. Flows list each step with its own ``path:line``.
- **Search.** Filters features by name/file/summary; dims non-matching
  cards and feature nodes.

The graph.json schema is unchanged so this drops in on existing
``.context/features/`` folders without rebuild.
"""

from __future__ import annotations

VIEWER_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>dummyindex · features</title>
<style>
  :root {
    --bg: #0f1115;
    --bg-2: #161a20;
    --bg-3: #1f242c;
    --fg: #e6e6e6;
    --muted: #8a93a3;
    --accent: #7fb8ff;
    --border: #2a3038;
  }
  html, body { margin: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--fg); }
  header {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 10px 16px; border-bottom: 1px solid var(--border); background: var(--bg-2);
  }
  header h1 { font-size: 14px; font-weight: 600; margin: 0; letter-spacing: 0.04em; }
  header .badge {
    font-size: 11px; color: var(--muted); padding: 2px 8px;
    background: var(--bg-3); border-radius: 10px;
  }
  header .spacer { flex: 1; }
  header input[type="search"] {
    background: var(--bg-3); border: 1px solid var(--border); color: var(--fg);
    padding: 5px 10px; border-radius: 4px; font-size: 12px; width: 240px;
  }
  header input[type="search"]:focus { outline: 1px solid var(--accent); }
  header .view-toggle {
    display: flex; background: var(--bg-3); border-radius: 4px; padding: 2px;
  }
  header .view-toggle button {
    background: transparent; color: var(--muted); border: 0; padding: 4px 10px;
    border-radius: 3px; font-size: 12px; cursor: pointer;
  }
  header .view-toggle button.active { background: var(--bg); color: var(--fg); }

  /* Kind filter chips — only visible in force view. */
  #kind-filter {
    display: none; gap: 4px; align-items: center;
    padding: 4px 8px; background: var(--bg-3); border-radius: 4px;
  }
  #kind-filter.visible { display: flex; }
  #kind-filter .chip {
    font-size: 11px; padding: 3px 8px; border-radius: 10px;
    background: var(--bg); color: var(--muted);
    border: 1px solid var(--border); cursor: pointer;
    user-select: none;
  }
  #kind-filter .chip.on { color: var(--fg); border-color: var(--accent); }

  main { display: grid; grid-template-columns: 1fr 380px; height: calc(100vh - 49px); }
  #stage { position: relative; overflow: hidden; }
  aside.detail {
    border-left: 1px solid var(--border); background: var(--bg-2);
    padding: 16px; overflow-y: auto; font-size: 13px;
  }
  aside.detail .placeholder { color: var(--muted); font-size: 12px; }
  aside.detail h2 { margin: 0 0 4px; font-size: 14px; }
  aside.detail .meta {
    color: var(--muted); font-size: 11px; margin-bottom: 12px;
    text-transform: uppercase; letter-spacing: 0.06em;
  }
  aside.detail .conf {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    background: var(--bg-3); margin-right: 6px; font-size: 10px;
  }
  aside.detail section { margin-bottom: 16px; }
  aside.detail section h3 {
    font-size: 11px; text-transform: uppercase; color: var(--muted);
    margin: 0 0 6px; letter-spacing: 0.08em;
  }
  aside.detail .summary { color: var(--fg); font-size: 13px; line-height: 1.5; }
  aside.detail ul { margin: 0; padding-left: 0; list-style: none; }
  aside.detail ul li { padding: 2px 0; font-size: 12px; }
  aside.detail .file-block {
    margin-bottom: 10px; padding-left: 8px;
    border-left: 2px solid var(--border);
  }
  aside.detail .file-block .file-name {
    font-weight: 600; font-size: 12px; color: var(--fg);
    word-break: break-all; margin-bottom: 2px;
  }
  aside.detail .sym {
    display: flex; gap: 6px; align-items: baseline;
    font-size: 11px; padding-left: 8px; padding-top: 1px;
  }
  aside.detail .sym .badge {
    font-size: 9px; padding: 0 5px; border-radius: 6px;
    color: var(--muted); background: var(--bg-3);
    min-width: 36px; text-align: center;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  aside.detail .sym .badge.class    { color: #c678dd; }
  aside.detail .sym .badge.function { color: #7fb8ff; }
  aside.detail .sym .badge.method   { color: #ff9e64; }
  aside.detail .sym .name {
    color: var(--fg); word-break: break-all; flex: 1;
  }
  aside.detail .sym .loc {
    color: var(--muted); font-family: ui-monospace, monospace; font-size: 10px;
  }
  aside.detail .flow-block {
    margin-bottom: 10px; padding: 8px;
    background: var(--bg); border-radius: 4px;
  }
  aside.detail .flow-block .flow-name { font-weight: 600; font-size: 12px; margin-bottom: 4px; }
  aside.detail .flow-step {
    font-size: 11px; color: var(--muted);
    padding-left: 12px; position: relative;
  }
  aside.detail .flow-step::before {
    content: "→"; position: absolute; left: 0; color: var(--accent);
  }
  aside.detail .flow-step code {
    color: var(--fg); font-size: 11px;
  }

  /* Grid view */
  #grid { display: grid; gap: 10px; padding: 16px; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); align-content: start; overflow-y: auto; height: 100%; box-sizing: border-box; }
  .card {
    background: var(--bg-2); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px; cursor: pointer; transition: transform 0.06s, border-color 0.06s;
  }
  .card:hover { transform: translateY(-1px); border-color: var(--accent); }
  .card.active { outline: 2px solid var(--accent); }
  .card.dim { opacity: 0.25; }
  .card .name { font-weight: 600; font-size: 13px; word-break: break-word; }
  .card .sub { color: var(--muted); font-size: 10px; margin-top: 4px; }
  .card .chip { display: inline-block; font-size: 9px; padding: 1px 6px; border-radius: 8px; background: var(--bg-3); color: var(--muted); margin-right: 4px; }

  /* Force view (D3) */
  svg { width: 100%; height: 100%; display: block; }
  .link { stroke-opacity: 0.5; }
  .link.parent    { stroke: #3a4654; stroke-dasharray: 2 2; }
  .link.contains  { stroke: #4a5568; }
  .link.touches   { stroke: #2a3038; stroke-opacity: 0.25; }
  .node text { fill: #ccc; font-size: 10px; pointer-events: none; }
  .node.folder text { fill: #6b7280; font-size: 9px; }
  .node.file text   { fill: #aab; font-size: 9px; }
  .node.class text  { fill: #c678dd; font-size: 9px; font-weight: 600; }
  .node.function text, .node.method text { fill: #7fb8ff; font-size: 8px; }
  .node.feature text { font-weight: 600; font-size: 12px; }
  .node.feature circle { stroke: #fff; stroke-width: 1.5; }
  .node.flow circle    { stroke: #aaa; stroke-width: 1; }
  .node.file circle    { stroke: #555; stroke-width: 1; }
  .node.class circle   { stroke: #c678dd; stroke-width: 1.5; }
  .node.function circle, .node.method circle { stroke: #555; stroke-width: 0.8; }
  .node.folder rect    { fill: transparent; stroke: #4a5568; stroke-dasharray: 3 2; }
  .node.dimmed { opacity: 0.12; }
  .tooltip { position: absolute; pointer-events: none; padding: 6px 10px; background: rgba(0,0,0,0.92); border: 1px solid #333; border-radius: 4px; font-size: 12px; color: #fff; max-width: 320px; white-space: pre-wrap; z-index: 10; }

  .hidden { display: none !important; }
  .error-box { padding: 24px; color: #ffb4b4; font-family: ui-monospace, monospace; }
</style>
</head>
<body>
<header>
  <h1>dummyindex / features</h1>
  <span class="badge" id="counts">…</span>
  <div id="kind-filter">
    <span style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em;">show:</span>
    <span class="chip on" data-kind="folder">folders</span>
    <span class="chip on" data-kind="file">files</span>
    <span class="chip" data-kind="class">classes</span>
    <span class="chip" data-kind="function">functions</span>
    <span class="chip" data-kind="method">methods</span>
    <span class="chip on" data-kind="feature">features</span>
    <span class="chip" data-kind="flow">flows</span>
  </div>
  <span class="spacer"></span>
  <input type="search" id="search" placeholder="filter features (name, file, summary)…" />
  <div class="view-toggle">
    <button data-view="grid" class="active">Grid</button>
    <button data-view="force">Force</button>
  </div>
</header>
<main>
  <div id="stage">
    <div id="grid"></div>
    <svg id="canvas" class="hidden"></svg>
    <div class="tooltip" id="tooltip" style="display:none"></div>
  </div>
  <aside class="detail" id="detail">
    <div class="placeholder">Pick a feature to see its files, classes, methods, and flows with <code>path:line</code> citations.</div>
  </aside>
</main>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const PALETTE = ["#a3d977", "#7fb8ff", "#ff9e64", "#c678dd", "#ff6b6b", "#4ade80", "#facc15", "#22d3ee", "#fb7185", "#a78bfa", "#fdba74", "#34d399", "#f472b6", "#60a5fa"];
const SYMBOL_KINDS = new Set(["class", "function", "method"]);

(async () => {
  let data;
  try {
    data = await fetch("./graph.json").then(r => r.json());
  } catch (err) {
    document.body.innerHTML = '<div class="error-box">Could not load <code>./graph.json</code> — open this file via a local server (e.g. <code>python3 -m http.server</code>) from inside <code>.context/features/</code>.</div>';
    return;
  }

  // ----- Indexes for fast lookups ----------------------------------------
  const nodeById = new Map();
  data.nodes.forEach(n => nodeById.set(n.id, n));
  const features = data.nodes.filter(n => n.kind === "feature");
  const flows = data.nodes.filter(n => n.kind === "flow");
  const symbols = data.nodes.filter(n => SYMBOL_KINDS.has(n.kind));
  const symbolCount = { class: 0, function: 0, method: 0 };
  symbols.forEach(s => { symbolCount[s.kind] = (symbolCount[s.kind] || 0) + 1; });

  // feature.id → [file_id, ...]
  const featureFiles = {};
  // feature.id → [symbol_id, ...]
  const featureSymbols = {};
  // feature.id → [flow_id, ...]
  const flowsByFeature = {};
  // symbol_id → parent_id (file or symbol)
  const symbolParent = {};
  // file_id → [symbol_id, ...] (direct children only)
  const fileSymbols = {};
  // symbol_id → [child_symbol_id, ...]
  const symbolChildren = {};
  // flow_id → feature_id
  const flowToFeature = {};

  data.edges.forEach(e => {
    if (e.relation === "contains") {
      const src = e.source, tgt = e.target;
      if (String(tgt).startsWith("flow-")) {
        flowToFeature[tgt] = src;
        (flowsByFeature[src] = flowsByFeature[src] || []).push(tgt);
      } else if (String(tgt).startsWith("symbol::")) {
        symbolParent[tgt] = src;
        if (String(src).startsWith("file::")) {
          (fileSymbols[src] = fileSymbols[src] || []).push(tgt);
        } else if (String(src).startsWith("symbol::")) {
          (symbolChildren[src] = symbolChildren[src] || []).push(tgt);
        }
      }
    } else if (e.relation === "touches") {
      if (String(e.target).startsWith("file::")) {
        (featureFiles[e.source] = featureFiles[e.source] || []).push(e.target);
      } else if (String(e.target).startsWith("symbol::")) {
        (featureSymbols[e.source] = featureSymbols[e.source] || []).push(e.target);
      }
    }
  });

  const featureColor = {};
  features.forEach((n, i) => { featureColor[n.id] = PALETTE[i % PALETTE.length]; });

  const counts = document.getElementById("counts");
  counts.textContent =
    `${features.length} features · ${flows.length} flows · ` +
    `${symbolCount.class} classes · ${symbolCount.function + symbolCount.method} fns/methods · ` +
    `${data.nodes.length} nodes`;

  // ----- Grid view --------------------------------------------------------
  const grid = document.getElementById("grid");
  const sorted = features.slice().sort((a, b) => (b.file_count || 0) - (a.file_count || 0));
  sorted.forEach(f => {
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.featureId = f.id;
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = f.label;
    name.style.color = featureColor[f.id];
    const sub = document.createElement("div");
    sub.className = "sub";
    const chips = [
      f.file_count != null ? `<span class="chip">${f.file_count} files</span>` : "",
      f.member_count != null ? `<span class="chip">${f.member_count} symbols</span>` : "",
      (flowsByFeature[f.id] || []).length ? `<span class="chip">${(flowsByFeature[f.id] || []).length} flows</span>` : "",
      f.confidence ? `<span class="chip">${f.confidence}</span>` : "",
    ].join("");
    sub.innerHTML = chips;
    card.appendChild(name);
    card.appendChild(sub);
    if (f.summary) {
      const s = document.createElement("div");
      s.className = "sub";
      s.style.marginTop = "6px";
      s.style.color = "#bdc4d0";
      s.textContent = f.summary.length > 110 ? f.summary.slice(0, 109) + "…" : f.summary;
      card.appendChild(s);
    }
    card.addEventListener("click", () => selectFeature(f.id));
    grid.appendChild(card);
  });

  // ----- Force view (D3) --------------------------------------------------
  const svg = d3.select("#canvas");
  const tooltip = d3.select("#tooltip");
  let sim = null;
  let forceBuilt = false;
  let nodeSel = null;
  let linkSel = null;
  // Default: hide symbols (they explode the node count on large repos)
  // and hide flows (visual clutter once you can drill via detail panel).
  const visibleKinds = new Set(["folder", "file", "feature"]);

  function nodeIsVisible(n) { return visibleKinds.has(n.kind); }
  function edgeIsVisible(e) {
    const s = nodeById.get(typeof e.source === "object" ? e.source.id : e.source);
    const t = nodeById.get(typeof e.target === "object" ? e.target.id : e.target);
    return s && t && nodeIsVisible(s) && nodeIsVisible(t);
  }

  function buildForce() {
    if (forceBuilt) return;
    forceBuilt = true;
    const width = svg.node().clientWidth || 800;
    const height = svg.node().clientHeight || 600;
    const g = svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.15, 5]).on("zoom", (e) => g.attr("transform", e.transform)));

    const linkDist = e => ({ parent: 30, contains: 45, touches: 90 }[e.relation] || 60);
    const linkStr  = e => ({ parent: 1.2, contains: 0.9, touches: 0.18 }[e.relation] || 0.4);

    sim = d3.forceSimulation(data.nodes)
      .force("link", d3.forceLink(data.edges).id(d => d.id).distance(linkDist).strength(linkStr))
      .force("charge", d3.forceManyBody().strength(d => {
        if (d.kind === "feature") return -500;
        if (d.kind === "flow") return -150;
        if (d.kind === "file") return -90;
        if (d.kind === "folder") return -180;
        return -35; // symbols
      }))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(d => {
        if (d.kind === "feature") return 28;
        if (d.kind === "flow") return 12;
        if (d.kind === "file") return 9;
        if (d.kind === "folder") return 14;
        return 5;
      }));

    linkSel = g.append("g").attr("class", "links").selectAll("line")
      .data(data.edges).enter().append("line")
      .attr("class", d => "link " + (d.relation || ""));

    nodeSel = g.append("g").selectAll("g.node")
      .data(data.nodes).enter().append("g")
      .attr("class", d => "node " + d.kind)
      .attr("data-id", d => d.id)
      .on("click", (e, d) => {
        if (d.kind === "feature") selectFeature(d.id);
        else if (d.kind === "flow") selectFeature(flowToFeature[d.id]);
      });

    nodeSel.filter(d => d.kind === "folder").append("rect")
      .attr("x", -10).attr("y", -7).attr("width", 20).attr("height", 14).attr("rx", 3);
    nodeSel.filter(d => d.kind !== "folder").append("circle")
      .attr("r", d => {
        if (d.kind === "feature") return 14;
        if (d.kind === "flow") return 7;
        if (d.kind === "file") return 4;
        if (d.kind === "class") return 4;
        return 2.5; // function / method
      })
      .attr("fill", d => {
        if (d.kind === "feature") return featureColor[d.id];
        if (d.kind === "flow") {
          const owner = flowToFeature[d.id];
          return featureColor[owner] || "#7fb8ff";
        }
        if (d.kind === "class") return "#2a1a30";
        if (d.kind === "function") return "#1a2632";
        if (d.kind === "method") return "#2a1f1a";
        return "#7c8696";
      });
    nodeSel.append("text")
      .text(d => d.label)
      .attr("x", d => {
        if (d.kind === "feature") return 18;
        if (d.kind === "folder") return 14;
        if (d.kind === "class") return 7;
        return 6;
      })
      .attr("dy", "0.32em");

    nodeSel.on("mouseover", (event, d) => {
      const lines = [`${d.kind} · ${d.label}`];
      if (d.path) {
        const loc = d.range && d.range[0] ? `${d.path}:${d.range[0]}` : d.path;
        lines.push(loc);
      }
      if (d.kind === "feature") {
        if (d.summary) { lines.push(""); lines.push(d.summary); }
        lines.push(`${d.member_count || 0} symbols · ${d.file_count || 0} files · ${d.flow_count || 0} flows`);
      } else if (d.kind === "flow") {
        lines.push(`${d.step_count || 0} steps · ${d.file_count || 0} files`);
      }
      const rect = document.getElementById("stage").getBoundingClientRect();
      tooltip.style("display", "block")
        .style("left", (event.clientX - rect.left + 14) + "px")
        .style("top", (event.clientY - rect.top + 14) + "px")
        .text(lines.join("\n"));
    }).on("mouseout", () => tooltip.style("display", "none"));

    sim.on("tick", () => {
      linkSel.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
             .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      nodeSel.attr("transform", d => `translate(${d.x},${d.y})`);
    });

    nodeSel.call(d3.drag()
      .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag",  (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end",   (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

    applyKindVisibility();
  }

  function applyKindVisibility() {
    if (!nodeSel) return;
    nodeSel.style("display", d => nodeIsVisible(d) ? null : "none");
    linkSel.style("display", d => edgeIsVisible(d) ? null : "none");
    // Reheat the simulation so visible nodes can rearrange after a toggle.
    if (sim) sim.alpha(0.4).restart();
  }

  // ----- Kind filter chips -----------------------------------------------
  document.querySelectorAll("#kind-filter .chip").forEach(chip => {
    if (visibleKinds.has(chip.dataset.kind)) chip.classList.add("on");
    chip.addEventListener("click", () => {
      const k = chip.dataset.kind;
      if (visibleKinds.has(k)) { visibleKinds.delete(k); chip.classList.remove("on"); }
      else { visibleKinds.add(k); chip.classList.add("on"); }
      applyKindVisibility();
    });
  });

  // ----- View toggle ------------------------------------------------------
  const kindFilter = document.getElementById("kind-filter");
  const toggleBtns = document.querySelectorAll(".view-toggle button");
  toggleBtns.forEach(btn => btn.addEventListener("click", () => {
    toggleBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const view = btn.dataset.view;
    if (view === "grid") {
      grid.classList.remove("hidden");
      svg.node().classList.add("hidden");
      kindFilter.classList.remove("visible");
    } else {
      grid.classList.add("hidden");
      svg.node().classList.remove("hidden");
      kindFilter.classList.add("visible");
      buildForce();
    }
  }));

  // ----- Detail panel -----------------------------------------------------
  const detail = document.getElementById("detail");
  function selectFeature(id) {
    document.querySelectorAll(".card").forEach(c => c.classList.toggle("active", c.dataset.featureId === id));
    const feat = nodeById.get(id);
    if (!feat || feat.kind !== "feature") { detail.innerHTML = '<div class="placeholder">Feature not found.</div>'; return; }

    const fileIds = featureFiles[id] || [];
    const flowIds = flowsByFeature[id] || [];

    // Group this feature's touched symbols by file. featureSymbols[id] is
    // the canonical "this feature owns these symbols" set from the touches
    // edges.
    const touchedSymbolIds = new Set(featureSymbols[id] || []);
    const symbolsByFile = {};
    fileIds.forEach(fid => { symbolsByFile[fid] = []; });
    touchedSymbolIds.forEach(sid => {
      // Walk up to its containing file via symbolParent (could be nested).
      let p = symbolParent[sid];
      while (p && String(p).startsWith("symbol::")) p = symbolParent[p];
      if (p && String(p).startsWith("file::")) {
        (symbolsByFile[p] = symbolsByFile[p] || []).push(sid);
      }
    });
    // Sort each file's symbols by [kind: class before function before method, then by line].
    const kindOrder = { class: 0, function: 1, method: 2 };
    Object.values(symbolsByFile).forEach(arr => arr.sort((a, b) => {
      const sa = nodeById.get(a), sb = nodeById.get(b);
      const ka = kindOrder[sa.kind] ?? 9, kb = kindOrder[sb.kind] ?? 9;
      if (ka !== kb) return ka - kb;
      const la = (sa.range && sa.range[0]) || 0;
      const lb = (sb.range && sb.range[0]) || 0;
      return la - lb;
    }));

    const lines = [];
    lines.push(`<h2 style="color:${featureColor[id]}">${escapeHtml(feat.label)}</h2>`);
    lines.push(`<div class="meta">${escapeHtml(feat.id)}</div>`);
    if (feat.confidence) lines.push(`<span class="conf">${escapeHtml(feat.confidence)}</span>`);
    if (feat.summary) {
      lines.push(`<section><h3>Summary</h3><div class="summary">${escapeHtml(feat.summary)}</div></section>`);
    }
    lines.push(`<section><h3>At a glance</h3><div>${[
      `${feat.member_count || 0} symbols`,
      `${feat.file_count || 0} files`,
      `${flowIds.length} flows`,
    ].join(' · ')}</div></section>`);

    // Files + symbols block — the surgical-update payload.
    const filesWithSymbols = fileIds.map(fid => [fid, symbolsByFile[fid] || []])
                                    .sort((a, b) => b[1].length - a[1].length);
    if (filesWithSymbols.length) {
      lines.push(`<section><h3>Files · classes · methods</h3>`);
      filesWithSymbols.slice(0, 50).forEach(([fid, sids]) => {
        const fnode = nodeById.get(fid);
        const fpath = (fnode && fnode.path) || (fnode && fnode.label) || fid;
        lines.push(`<div class="file-block">`);
        lines.push(`<div class="file-name">${escapeHtml(fpath)}</div>`);
        if (sids.length === 0) {
          lines.push(`<div class="sym"><span class="loc">(no class/function/method nodes for this file)</span></div>`);
        } else {
          sids.slice(0, 40).forEach(sid => {
            const s = nodeById.get(sid);
            if (!s) return;
            const loc = s.range && s.range[0] ? `:${s.range[0]}` : "";
            lines.push(
              `<div class="sym">` +
                `<span class="badge ${s.kind}">${s.kind}</span>` +
                `<span class="name">${escapeHtml(s.label)}<span class="loc">${loc}</span></span>` +
              `</div>`
            );
          });
          if (sids.length > 40) {
            lines.push(`<div class="sym"><span class="loc">… +${sids.length - 40} more</span></div>`);
          }
        }
        lines.push(`</div>`);
      });
      if (filesWithSymbols.length > 50) {
        lines.push(`<div class="meta">… +${filesWithSymbols.length - 50} more files</div>`);
      }
      lines.push(`</section>`);
    }

    // Flows with their steps (path:line each).
    if (flowIds.length) {
      lines.push(`<section><h3>Flows</h3>`);
      flowIds.slice(0, 12).forEach(flid => {
        const fl = nodeById.get(flid);
        if (!fl) return;
        lines.push(`<div class="flow-block">`);
        lines.push(`<div class="flow-name">${escapeHtml(fl.label)} <code style="color:var(--muted);font-size:10px">${fl.step_count || 0} steps</code></div>`);
        // Find any "steps" payload — flows in graph.json don't include them
        // (the rich data lives in features/<feat>/flows/<flow>.json). For
        // the viewer we display the file targets touched by this flow as a
        // proxy.
        const flFileEdges = data.edges.filter(e =>
          e.relation === "touches" && e.source === flid && String(e.target).startsWith("file::")
        );
        flFileEdges.slice(0, 8).forEach(e => {
          const fn = nodeById.get(e.target);
          if (fn) {
            lines.push(`<div class="flow-step"><code>${escapeHtml(fn.path || fn.label)}</code></div>`);
          }
        });
        if (flFileEdges.length > 8) {
          lines.push(`<div class="flow-step" style="color:var(--muted)">… +${flFileEdges.length - 8} more</div>`);
        }
        lines.push(`</div>`);
      });
      if (flowIds.length > 12) {
        lines.push(`<div class="meta">… +${flowIds.length - 12} more flows</div>`);
      }
      lines.push(`</section>`);
    }

    detail.innerHTML = lines.join("");
  }

  // ----- Search -----------------------------------------------------------
  const search = document.getElementById("search");
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    if (!q) {
      document.querySelectorAll(".card").forEach(c => c.classList.remove("dim"));
      document.querySelectorAll(".node").forEach(n => n.classList.remove("dimmed"));
      return;
    }
    const matchSet = new Set();
    features.forEach(f => {
      const hay = [f.label, f.id, f.summary || ""].join(" ").toLowerCase();
      if (hay.includes(q)) matchSet.add(f.id);
    });
    // Also consider file-name and symbol-name matches as matching the
    // owning feature.
    data.edges.filter(e => e.relation === "touches").forEach(e => {
      const target = nodeById.get(e.target);
      if (target && (target.path || target.label || "").toLowerCase().includes(q)) {
        matchSet.add(e.source);
      }
    });
    document.querySelectorAll(".card").forEach(c => {
      c.classList.toggle("dim", !matchSet.has(c.dataset.featureId));
    });
    document.querySelectorAll(".node.feature").forEach(n => {
      n.classList.toggle("dimmed", !matchSet.has(n.getAttribute("data-id")));
    });
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  }
})();
</script>
</body>
</html>
"""
