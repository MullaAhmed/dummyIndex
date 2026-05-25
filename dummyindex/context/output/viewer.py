"""The HTML viewer that ships next to `features/graph.json`.

Single ``VIEWER_HTML`` string. Loaded by ``features.py`` and written
alongside ``graph.json`` so users can ``python3 -m http.server`` inside
``.context/features/`` and explore.

Design (v0.10 rebuild):

- **Feature-grid view (default).** A clickable card per feature, sorted
  by file_count desc. Grid scales: a repo with 200 features renders as
  a 200-card grid, no hairball. Click a card to open its detail panel.
- **Force-directed view (toggle).** The original layered graph
  (folder/file/feature/flow) — kept because for small repos it's still
  the cleanest mental model.
- **Search.** A text filter that highlights matching features in the
  grid and in the force view.
- **Detail panel.** Click a feature in either view: shows summary,
  files, flow list, member count, confidence. No round-trip to disk;
  everything is in graph.json.

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
    display: flex; align-items: center; gap: 12px;
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

  main { display: grid; grid-template-columns: 1fr 360px; height: calc(100vh - 49px); }
  #stage { position: relative; overflow: hidden; }
  aside.detail {
    border-left: 1px solid var(--border); background: var(--bg-2);
    padding: 16px; overflow-y: auto; font-size: 13px;
  }
  aside.detail .placeholder { color: var(--muted); font-size: 12px; }
  aside.detail h2 {
    margin: 0 0 4px; font-size: 14px;
  }
  aside.detail .meta {
    color: var(--muted); font-size: 11px; margin-bottom: 12px;
    text-transform: uppercase; letter-spacing: 0.06em;
  }
  aside.detail .conf {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    background: var(--bg-3); margin-right: 6px; font-size: 10px;
  }
  aside.detail section { margin-bottom: 14px; }
  aside.detail section h3 {
    font-size: 11px; text-transform: uppercase; color: var(--muted);
    margin: 0 0 6px; letter-spacing: 0.08em;
  }
  aside.detail .summary { color: var(--fg); font-size: 13px; line-height: 1.5; }
  aside.detail ul { margin: 0; padding-left: 18px; }
  aside.detail ul li { padding: 1px 0; font-size: 12px; word-break: break-all; }
  aside.detail ul li code { font-size: 11px; color: var(--muted); }

  /* Grid view */
  #grid { display: grid; gap: 10px; padding: 16px; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); align-content: start; overflow-y: auto; height: 100%; box-sizing: border-box; }
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
  .link.touches   { stroke: #2a3038; stroke-opacity: 0.35; }
  .node text { fill: #ccc; font-size: 10px; pointer-events: none; }
  .node.folder text { fill: #6b7280; font-size: 9px; }
  .node.file text   { fill: #aab; font-size: 9px; }
  .node.feature text { font-weight: 600; font-size: 12px; }
  .node.feature circle { stroke: #fff; stroke-width: 1.5; }
  .node.flow circle    { stroke: #aaa; stroke-width: 1; }
  .node.file circle    { stroke: #555; stroke-width: 1; }
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
    <div class="placeholder">Pick a feature to see members, files, and flows.</div>
  </aside>
</main>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script>
const PALETTE = ["#a3d977", "#7fb8ff", "#ff9e64", "#c678dd", "#ff6b6b", "#4ade80", "#facc15", "#22d3ee", "#fb7185", "#a78bfa", "#fdba74", "#34d399", "#f472b6", "#60a5fa"];

(async () => {
  let data;
  try {
    data = await fetch("./graph.json").then(r => r.json());
  } catch (err) {
    document.body.innerHTML = '<div class="error-box">Could not load <code>./graph.json</code> — open this file via a local server (e.g. <code>python3 -m http.server</code>) from inside <code>.context/features/</code>.</div>';
    return;
  }

  const features = data.nodes.filter(n => n.kind === "feature");
  const flowsByFeature = {};
  data.edges.filter(e => e.relation === "contains" && String(e.target).startsWith("flow-")).forEach(e => {
    (flowsByFeature[e.source] = flowsByFeature[e.source] || []).push(e.target);
  });
  const flows = data.nodes.filter(n => n.kind === "flow");
  const featureColor = {};
  features.forEach((n, i) => { featureColor[n.id] = PALETTE[i % PALETTE.length]; });

  const counts = document.getElementById("counts");
  counts.textContent = `${features.length} features · ${flows.length} flows · ${data.nodes.length} nodes`;

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
  function buildForce() {
    if (forceBuilt) return;
    forceBuilt = true;
    const width = svg.node().clientWidth || 800;
    const height = svg.node().clientHeight || 600;
    const g = svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.15, 5]).on("zoom", (e) => g.attr("transform", e.transform)));

    const linkDist = e => ({ parent: 35, contains: 50, touches: 80 }[e.relation] || 60);
    const linkStr  = e => ({ parent: 1.1, contains: 0.8, touches: 0.25 }[e.relation] || 0.5);

    sim = d3.forceSimulation(data.nodes)
      .force("link", d3.forceLink(data.edges).id(d => d.id).distance(linkDist).strength(linkStr))
      .force("charge", d3.forceManyBody().strength(d => d.kind === "feature" ? -350 : (d.kind === "flow" ? -120 : -40)))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(d => d.kind === "feature" ? 24 : (d.kind === "flow" ? 12 : (d.kind === "file" ? 8 : 14))));

    const link = g.append("g").attr("class", "links").selectAll("line")
      .data(data.edges).enter().append("line")
      .attr("class", d => "link " + (d.relation || ""));

    const node = g.append("g").selectAll("g.node")
      .data(data.nodes).enter().append("g")
      .attr("class", d => "node " + d.kind)
      .attr("data-id", d => d.id)
      .on("click", (e, d) => { if (d.kind === "feature") selectFeature(d.id); });

    node.filter(d => d.kind === "folder").append("rect")
      .attr("x", -10).attr("y", -7).attr("width", 20).attr("height", 14).attr("rx", 3);
    node.filter(d => d.kind !== "folder").append("circle")
      .attr("r", d => d.kind === "feature" ? 14 : (d.kind === "flow" ? 7 : 4))
      .attr("fill", d => {
        if (d.kind === "feature") return featureColor[d.id];
        if (d.kind === "flow") {
          // Find which feature this flow belongs to.
          const e = data.edges.find(x => x.relation === "contains" && x.target === d.id);
          return e ? (featureColor[e.source] || "#7fb8ff") : "#7fb8ff";
        }
        return "#7c8696";
      });
    node.append("text")
      .text(d => d.label)
      .attr("x", d => (d.kind === "feature" ? 18 : (d.kind === "folder" ? 14 : 8)))
      .attr("dy", "0.32em");

    node.on("mouseover", (event, d) => {
      const lines = [`${d.kind} · ${d.label}`];
      if (d.path) lines.push(d.path);
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
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

    node.call(d3.drag()
      .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag",  (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end",   (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
  }

  // ----- View toggle ------------------------------------------------------
  const toggleBtns = document.querySelectorAll(".view-toggle button");
  toggleBtns.forEach(btn => btn.addEventListener("click", () => {
    toggleBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const view = btn.dataset.view;
    if (view === "grid") {
      grid.classList.remove("hidden");
      svg.node().classList.add("hidden");
    } else {
      grid.classList.add("hidden");
      svg.node().classList.remove("hidden");
      buildForce();
    }
  }));

  // ----- Detail panel -----------------------------------------------------
  const detail = document.getElementById("detail");
  let activeId = null;
  function selectFeature(id) {
    activeId = id;
    document.querySelectorAll(".card").forEach(c => c.classList.toggle("active", c.dataset.featureId === id));
    const feat = features.find(f => f.id === id);
    if (!feat) { detail.innerHTML = '<div class="placeholder">Feature not found.</div>'; return; }
    const flowIds = flowsByFeature[id] || [];
    const flowNodes = flows.filter(f => flowIds.includes(f.id));
    const fileNodes = data.nodes.filter(n => n.kind === "file" && data.edges.some(e =>
      e.relation === "touches" && e.source === id && e.target === n.id
    ));
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
    if (fileNodes.length) {
      lines.push(`<section><h3>Files</h3><ul>` +
        fileNodes.slice(0, 30).map(f => `<li><code>${escapeHtml(f.path || f.label)}</code></li>`).join("") +
        (fileNodes.length > 30 ? `<li>… +${fileNodes.length - 30} more</li>` : "") +
        `</ul></section>`);
    }
    if (flowNodes.length) {
      lines.push(`<section><h3>Flows</h3><ul>` +
        flowNodes.map(fl => `<li>${escapeHtml(fl.label)} <code>(${fl.step_count || 0} steps)</code></li>`).join("") +
        `</ul></section>`);
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
    // Also consider file-name matches as matching the owning feature.
    data.edges.filter(e => e.relation === "touches").forEach(e => {
      const target = data.nodes.find(n => n.id === e.target);
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
