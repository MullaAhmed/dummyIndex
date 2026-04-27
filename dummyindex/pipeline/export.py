# write graph to HTML, JSON, SVG, GraphML, Obsidian vault, and Neo4j Cypher
from __future__ import annotations
import html as _html
import json
import math
import re
from collections import Counter
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from dummyindex.runtime.security import sanitize_label
from dummyindex.analysis.analyze import _node_community_map

def _strip_diacritics(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


COMMUNITY_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

MAX_NODES_FOR_VIZ = 5_000


def _html_styles() -> str:
    return """<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0f0f1a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; height: 100vh; overflow: hidden; }
  #graph { flex: 1; }
  #sidebar { width: 280px; background: #1a1a2e; border-left: 1px solid #2a2a4e; display: flex; flex-direction: column; overflow: hidden; }
  #search-wrap { padding: 12px; border-bottom: 1px solid #2a2a4e; }
  #search { width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  #search:focus { border-color: #4E79A7; }
  #search-results { max-height: 140px; overflow-y: auto; padding: 4px 12px; border-bottom: 1px solid #2a2a4e; display: none; }
  .search-item { padding: 4px 6px; cursor: pointer; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: #2a2a4e; }
  #info-panel { padding: 14px; border-bottom: 1px solid #2a2a4e; min-height: 140px; }
  #info-panel h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  #info-content { font-size: 13px; color: #ccc; line-height: 1.6; }
  #info-content .field { margin-bottom: 5px; }
  #info-content .field b { color: #e0e0e0; }
  #info-content .empty { color: #555; font-style: italic; }
  .neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #333; }
  .neighbor-link:hover { background: #2a2a4e; }
  #neighbors-list { max-height: 160px; overflow-y: auto; margin-top: 4px; }
  #legend-wrap { flex: 1; overflow-y: auto; padding: 12px; }
  #legend-wrap h3 { font-size: 13px; color: #aaa; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: #2a2a4e; padding-left: 4px; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: #666; font-size: 11px; }
  #stats { padding: 10px 14px; border-top: 1px solid #2a2a4e; font-size: 11px; color: #555; }
</style>"""


def _hyperedge_script(hyperedges_json: str) -> str:
    return f"""<script>
// Render hyperedges as shaded regions
const hyperedges = {hyperedges_json};
// afterDrawing passes ctx already transformed to network coordinate space.
// Draw node positions raw — no manual pan/zoom/DPR math needed.
network.on('afterDrawing', function(ctx) {{
    hyperedges.forEach(h => {{
        const positions = h.nodes
            .map(nid => network.getPositions([nid])[nid])
            .filter(p => p !== undefined);
        if (positions.length < 2) return;
        ctx.save();
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = '#6366f1';
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Centroid and expanded hull in network coordinates
        const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length;
        const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length;
        const expanded = positions.map(p => ({{
            x: cx + (p.x - cx) * 1.15,
            y: cy + (p.y - cy) * 1.15
        }}));
        ctx.moveTo(expanded[0].x, expanded[0].y);
        expanded.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 0.4;
        ctx.stroke();
        // Label
        ctx.globalAlpha = 0.8;
        ctx.fillStyle = '#4f46e5';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(h.label, cx, cy - 5);
        ctx.restore();
    }});
}});
</script>"""


def _html_script(nodes_json: str, edges_json: str, legend_json: str) -> str:
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};

// HTML-escape helper — prevents XSS when injecting graph data into innerHTML
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

// Build vis datasets
const nodesDS = new vis.DataSet(RAW_NODES.map(n => ({{
  id: n.id, label: n.label, color: n.color, size: n.size,
  font: n.font, title: n.title,
  _community: n.community, _community_name: n.community_name,
  _source_file: n.source_file, _file_type: n.file_type, _degree: n.degree,
}})));

const edgesDS = new vis.DataSet(RAW_EDGES.map((e, i) => ({{
  id: i, from: e.from, to: e.to,
  label: '',
  title: e.title,
  dashes: e.dashes,
  width: e.width,
  color: e.color,
  arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
}})));

const container = document.getElementById('graph');
const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, {{
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -60,
      centralGravity: 0.005,
      springLength: 120,
      springConstant: 0.08,
      damping: 0.4,
      avoidOverlap: 0.8,
    }},
    stabilization: {{ iterations: 200, fit: true }},
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 100,
    hideEdgesOnDrag: true,
    navigationButtons: false,
    keyboard: false,
  }},
  nodes: {{ shape: 'dot', borderWidth: 1.5 }},
  edges: {{ smooth: {{ type: 'continuous', roundness: 0.2 }}, selectionWidth: 3 }},
}});

network.once('stabilizationIterationsDone', () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
}});

function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  const neighborIds = network.getConnectedNodes(nodeId);
  const neighborItems = neighborIds.map(nid => {{
    const nb = nodesDS.get(nid);
    const color = nb ? nb.color.background : '#555';
    return `<span class="neighbor-link" style="border-left-color:${{esc(color)}}" onclick="focusNode(${{JSON.stringify(nid)}})">${{esc(nb ? nb.label : nid)}}</span>`;
  }}).join('');
  document.getElementById('info-content').innerHTML = `
    <div class="field"><b>${{esc(n.label)}}</b></div>
    <div class="field">Type: ${{esc(n._file_type || 'unknown')}}</div>
    <div class="field">Community: ${{esc(n._community_name)}}</div>
    <div class="field">Source: ${{esc(n._source_file || '-')}}</div>
    <div class="field">Degree: ${{n._degree}}</div>
    ${{neighborIds.length ? `<div class="field" style="margin-top:8px;color:#aaa;font-size:11px">Neighbors (${{neighborIds.length}})</div><div id="neighbors-list">${{neighborItems}}</div>` : ''}}
  `;
}}

function focusNode(nodeId) {{
  network.focus(nodeId, {{ scale: 1.4, animation: true }});
  network.selectNodes([nodeId]);
  showInfo(nodeId);
}}

// Track hovered node — hover detection is more reliable than click params
let hoveredNodeId = null;
network.on('hoverNode', params => {{
  hoveredNodeId = params.node;
  container.style.cursor = 'pointer';
}});
network.on('blurNode', () => {{
  hoveredNodeId = null;
  container.style.cursor = 'default';
}});
container.addEventListener('click', () => {{
  if (hoveredNodeId !== null) {{
    showInfo(hoveredNodeId);
    network.selectNodes([hoveredNodeId]);
  }}
}});
network.on('click', params => {{
  if (params.nodes.length > 0) {{
    showInfo(params.nodes[0]);
  }} else if (hoveredNodeId === null) {{
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
  }}
}});

const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = `3px solid ${{n.color.background}}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{
      network.focus(n.id, {{ scale: 1.5, animation: true }});
      network.selectNodes([n.id]);
      showInfo(n.id);
      searchResults.style.display = 'none';
      searchInput.value = '';
    }};
    searchResults.appendChild(el);
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

const hiddenCommunities = new Set();
const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = `<div class="legend-dot" style="background:${{c.color}}"></div>
    <span class="legend-label">${{c.label}}</span>
    <span class="legend-count">${{c.count}}</span>`;
  item.onclick = () => {{
    if (hiddenCommunities.has(c.cid)) {{
      hiddenCommunities.delete(c.cid);
      item.classList.remove('dimmed');
    }} else {{
      hiddenCommunities.add(c.cid);
      item.classList.add('dimmed');
    }}
    const updates = RAW_NODES
      .filter(n => n.community === c.cid)
      .map(n => ({{ id: n.id, hidden: hiddenCommunities.has(c.cid) }}));
    nodesDS.update(updates);
  }};
  legendEl.appendChild(item);
}});
</script>"""


_CONFIDENCE_SCORE_DEFAULTS = {"EXTRACTED": 1.0, "INFERRED": 0.5, "AMBIGUOUS": 0.2}


def attach_hyperedges(G: nx.Graph, hyperedges: list) -> None:
    """Store hyperedges in the graph's metadata dict.

    Idempotent: hyperedges already present (by ``id``) are not duplicated.
    Safe to call repeatedly with overlapping inputs.
    """
    existing = G.graph.get("hyperedges", [])
    seen_ids = {h["id"] for h in existing}
    for h in hyperedges:
        if h.get("id") and h["id"] not in seen_ids:
            existing.append(h)
            seen_ids.add(h["id"])
    G.graph["hyperedges"] = existing


def restore_hyperedges_from_disk(G: nx.Graph, graph_json_path: str | Path) -> int:
    """Re-attach hyperedges from a previously-written ``graph.json`` onto ``G``.

    Each pipeline step (Step 6c flows, Step 6d features) builds its own ``G``
    from the extraction cache, so prior hyperedges aren't on the new graph
    object. Calling this before ``to_json`` preserves them — otherwise each
    step overwrites the previous step's hyperedges in ``graph.json``.

    Returns the number of hyperedges restored. No-op if file is missing.
    """
    from pathlib import Path as _Path
    p = _Path(graph_json_path)
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    prior = data.get("hyperedges") or []
    if prior:
        attach_hyperedges(G, prior)
    return len(prior)


def to_json(G: nx.Graph, communities: dict[int, list[str]], output_path: str) -> None:
    node_community = _node_community_map(communities)
    try:
        data = json_graph.node_link_data(G, edges="links")
    except TypeError:
        data = json_graph.node_link_data(G)
    for node in data["nodes"]:
        node["community"] = node_community.get(node["id"])
        node["norm_label"] = _strip_diacritics(node.get("label", "")).lower()
    for link in data["links"]:
        if "confidence_score" not in link:
            conf = link.get("confidence", "EXTRACTED")
            link["confidence_score"] = _CONFIDENCE_SCORE_DEFAULTS.get(conf, 1.0)
    data["hyperedges"] = getattr(G, "graph", {}).get("hyperedges", [])
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def prune_dangling_edges(graph_data: dict) -> tuple[dict, int]:
    """Remove edges whose source or target node is not in the node set.

    Returns the cleaned graph_data dict and the number of pruned edges.
    """
    node_ids = {n["id"] for n in graph_data["nodes"]}
    links_key = "links" if "links" in graph_data else "edges"
    before = len(graph_data[links_key])
    graph_data[links_key] = [
        e for e in graph_data[links_key]
        if e["source"] in node_ids and e["target"] in node_ids
    ]
    return graph_data, before - len(graph_data[links_key])


def _cypher_escape(s: str) -> str:
    """Escape a string for safe embedding in a Cypher single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def to_cypher(G: nx.Graph, output_path: str) -> None:
    lines = ["// Neo4j Cypher import - generated by /dummyindex", ""]
    for node_id, data in G.nodes(data=True):
        label = _cypher_escape(data.get("label", node_id))
        node_id_esc = _cypher_escape(node_id)
        _ft = re.sub(r"[^A-Za-z0-9_]", "", data.get("file_type", "unknown").capitalize())
        ftype = (_ft if _ft and _ft[0].isalpha() else "Entity")
        lines.append(f"MERGE (n:{ftype} {{id: '{node_id_esc}', label: '{label}'}});")
    lines.append("")
    for u, v, data in G.edges(data=True):
        rel = re.sub(r"[^A-Za-z0-9_]", "_", data.get("relation", "RELATES_TO").upper())
        conf = _cypher_escape(data.get("confidence", "EXTRACTED"))
        u_esc = _cypher_escape(u)
        v_esc = _cypher_escape(v)
        lines.append(
            f"MATCH (a {{id: '{u_esc}'}}), (b {{id: '{v_esc}'}}) "
            f"MERGE (a)-[:{rel} {{confidence: '{conf}'}}]->(b);"
        )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    member_counts: dict[int, int] | None = None,
) -> None:
    """Generate an interactive vis.js HTML visualization of the graph.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.
    """
    if G.number_of_nodes() > MAX_NODES_FOR_VIZ:
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz. "
            f"Use --no-viz or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1
    max_mc = (max(member_counts.values(), default=1) or 1) if member_counts else 1

    # Build nodes list for vis.js
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        if member_counts:
            mc = member_counts.get(cid, 1)
            size = 10 + 30 * (mc / max_mc)
            font_size = 12
        else:
            size = 10 + 30 * (deg / max_deg)
            # Only show label for high-degree nodes by default; others show on hover
            font_size = 12 if deg >= max_deg * 0.15 else 0
        vis_nodes.append({
            "id": node_id,
            "label": label,
            "color": {"background": color, "border": color, "highlight": {"background": "#ffffff", "border": color}},
            "size": round(size, 1),
            "font": {"size": font_size, "color": "#ffffff"},
            "title": _html.escape(label),
            "community": cid,
            "community_name": sanitize_label((community_labels or {}).get(cid, f"Community {cid}")),
            "source_file": sanitize_label(str(data.get("source_file") or "")),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        })

    # Build edges list
    vis_edges = []
    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        relation = data.get("relation", "")
        vis_edges.append({
            "from": u,
            "to": v,
            "label": relation,
            "title": _html.escape(f"{relation} [{confidence}]"),
            "dashes": confidence != "EXTRACTED",
            "width": 2 if confidence == "EXTRACTED" else 1,
            "color": {"opacity": 0.7 if confidence == "EXTRACTED" else 0.35},
            "confidence": confidence,
        })

    # Build community legend data
    legend_data = []
    for cid in sorted((community_labels or {}).keys()):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        lbl = _html.escape(sanitize_label((community_labels or {}).get(cid, f"Community {cid}")))
        n = member_counts.get(cid, len(communities.get(cid, []))) if member_counts else len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "label": lbl, "count": n})

    # Escape </script> sequences so embedded JSON cannot break out of the script tag
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("</", "<\\/")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    title = _html.escape(sanitize_label(str(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>dummyindex - {title}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
{_html_styles()}
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel">
    <h3>Node Info</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
{_html_script(nodes_json, edges_json, legend_json)}
{_hyperedge_script(hyperedges_json)}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")


# Keep backward-compatible alias - skill.md calls generate_html
generate_html = to_html


def to_obsidian(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_dir: str,
    community_labels: dict[int, str] | None = None,
    cohesion: dict[int, float] | None = None,
) -> int:
    """Export graph as an Obsidian vault - one .md file per node with [[wikilinks]],
    plus one _COMMUNITY_name.md overview note per community (sorted to top by underscore prefix).

    Open the output directory as a vault in Obsidian to get an interactive
    graph view with community colors and full-text search over node metadata.

    Returns the number of node notes + community notes written.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    node_community = _node_community_map(communities)

    # Map node_id → safe filename so wikilinks stay consistent.
    # Deduplicate: if two nodes produce the same filename, append a numeric suffix.
    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        # Strip trailing .md/.mdx/.markdown so "CLAUDE.md" doesn't become "CLAUDE.md.md"
        cleaned = re.sub(r"\.(md|mdx|markdown)$", "", cleaned, flags=re.IGNORECASE)
        return cleaned or "unnamed"

    node_filename: dict[str, str] = {}
    seen_names: dict[str, int] = {}
    for node_id, data in G.nodes(data=True):
        base = safe_name(data.get("label", node_id))
        if base in seen_names:
            seen_names[base] += 1
            node_filename[node_id] = f"{base}_{seen_names[base]}"
        else:
            seen_names[base] = 0
            node_filename[node_id] = base

    # Helper: compute dominant confidence for a node across all its edges
    def _dominant_confidence(node_id: str) -> str:
        confs = []
        for u, v, edata in G.edges(node_id, data=True):
            confs.append(edata.get("confidence", "EXTRACTED"))
        if not confs:
            return "EXTRACTED"
        return Counter(confs).most_common(1)[0][0]

    # Map file_type → dummyindex tag
    _FTYPE_TAG = {
        "code": "dummyindex/code",
        "document": "dummyindex/document",
        "paper": "dummyindex/paper",
        "image": "dummyindex/image",
    }

    # Write one .md file per node
    for node_id, data in G.nodes(data=True):
        label = data.get("label", node_id)
        cid = node_community.get(node_id)
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )

        # Build tags for this node
        ftype = data.get("file_type", "")
        ftype_tag = _FTYPE_TAG.get(ftype, f"dummyindex/{ftype}" if ftype else "dummyindex/document")
        dom_conf = _dominant_confidence(node_id)
        conf_tag = f"dummyindex/{dom_conf}"
        comm_tag = f"community/{community_name.replace(' ', '_')}"
        node_tags = [ftype_tag, conf_tag, comm_tag]

        lines: list[str] = []

        # YAML frontmatter - readable in Obsidian's properties panel
        lines += [
            "---",
            f'source_file: "{data.get("source_file", "")}"',
            f'type: "{ftype}"',
            f'community: "{community_name}"',
        ]
        if data.get("source_location"):
            lines.append(f'location: "{data["source_location"]}"')
        # Add tags list to frontmatter
        lines.append("tags:")
        for tag in node_tags:
            lines.append(f"  - {tag}")
        lines += ["---", "", f"# {label}", ""]

        # Outgoing edges as wikilinks
        neighbors = list(G.neighbors(node_id))
        if neighbors:
            lines.append("## Connections")
            for neighbor in sorted(neighbors, key=lambda n: G.nodes[n].get("label", n)):
                edge_data = G.edges[node_id, neighbor]
                neighbor_label = node_filename[neighbor]
                relation = edge_data.get("relation", "")
                confidence = edge_data.get("confidence", "EXTRACTED")
                lines.append(f"- [[{neighbor_label}]] - `{relation}` [{confidence}]")
            lines.append("")

        # Inline tags at bottom of note body (for Obsidian tag panel)
        inline_tags = " ".join(f"#{t}" for t in node_tags)
        lines.append(inline_tags)

        fname = node_filename[node_id] + ".md"
        (out / fname).write_text("\n".join(lines), encoding="utf-8")

    # Write one _COMMUNITY_name.md overview note per community
    # Build inter-community edge counts for "Connections to other communities"
    inter_community_edges: dict[int, dict[int, int]] = {}
    for cid in communities:
        inter_community_edges[cid] = {}
    for u, v in G.edges():
        cu = node_community.get(u)
        cv = node_community.get(v)
        if cu is not None and cv is not None and cu != cv:
            inter_community_edges.setdefault(cu, {})
            inter_community_edges.setdefault(cv, {})
            inter_community_edges[cu][cv] = inter_community_edges[cu].get(cv, 0) + 1
            inter_community_edges[cv][cu] = inter_community_edges[cv].get(cu, 0) + 1

    # Precompute per-node community reach (number of distinct communities a node connects to)
    def _community_reach(node_id: str) -> int:
        neighbor_cids = {
            node_community[nb]
            for nb in G.neighbors(node_id)
            if nb in node_community and node_community[nb] != node_community.get(node_id)
        }
        return len(neighbor_cids)

    community_notes_written = 0
    for cid, members in communities.items():
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )
        n_members = len(members)
        coh_value = cohesion.get(cid) if cohesion else None

        lines: list[str] = []

        # YAML frontmatter
        lines.append("---")
        lines.append("type: community")
        if coh_value is not None:
            lines.append(f"cohesion: {coh_value:.2f}")
        lines.append(f"members: {n_members}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {community_name}")
        lines.append("")

        # Cohesion + member count summary
        if coh_value is not None:
            cohesion_desc = (
                "tightly connected" if coh_value >= 0.7
                else "moderately connected" if coh_value >= 0.4
                else "loosely connected"
            )
            lines.append(f"**Cohesion:** {coh_value:.2f} - {cohesion_desc}")
        lines.append(f"**Members:** {n_members} nodes")
        lines.append("")

        # Members section
        lines.append("## Members")
        for node_id in sorted(members, key=lambda n: G.nodes[n].get("label", n)):
            data = G.nodes[node_id]
            node_label = node_filename[node_id]
            ftype = data.get("file_type", "")
            source = data.get("source_file", "")
            entry = f"- [[{node_label}]]"
            if ftype:
                entry += f" - {ftype}"
            if source:
                entry += f" - {source}"
            lines.append(entry)
        lines.append("")

        # Dataview live query (improvement 2)
        comm_tag_name = community_name.replace(" ", "_")
        lines.append("## Live Query (requires Dataview plugin)")
        lines.append("")
        lines.append("```dataview")
        lines.append(f"TABLE source_file, type FROM #community/{comm_tag_name}")
        lines.append("SORT file.name ASC")
        lines.append("```")
        lines.append("")

        # Connections to other communities
        cross = inter_community_edges.get(cid, {})
        if cross:
            lines.append("## Connections to other communities")
            for other_cid, edge_count in sorted(cross.items(), key=lambda x: -x[1]):
                other_name = (
                    community_labels.get(other_cid, f"Community {other_cid}")
                    if community_labels and other_cid is not None
                    else f"Community {other_cid}"
                )
                other_safe = safe_name(other_name)
                lines.append(f"- {edge_count} edge{'s' if edge_count != 1 else ''} to [[_COMMUNITY_{other_safe}]]")
            lines.append("")

        # Top bridge nodes - highest degree nodes that connect to other communities
        bridge_nodes = [
            (node_id, G.degree(node_id), _community_reach(node_id))
            for node_id in members
            if _community_reach(node_id) > 0
        ]
        bridge_nodes.sort(key=lambda x: (-x[2], -x[1]))
        top_bridges = bridge_nodes[:5]
        if top_bridges:
            lines.append("## Top bridge nodes")
            for node_id, degree, reach in top_bridges:
                node_label = node_filename[node_id]
                lines.append(
                    f"- [[{node_label}]] - degree {degree}, connects to {reach} "
                    f"{'community' if reach == 1 else 'communities'}"
                )

        community_safe = safe_name(community_name)
        fname = f"_COMMUNITY_{community_safe}.md"
        (out / fname).write_text("\n".join(lines), encoding="utf-8")
        community_notes_written += 1

    # Improvement 4: write .obsidian/graph.json to color nodes by community in graph view
    obsidian_dir = out / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    graph_config = {
        "colorGroups": [
            {
                "query": f"tag:#community/{label.replace(' ', '_')}",
                "color": {"a": 1, "rgb": int(COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)].lstrip('#'), 16)}
            }
            for cid, label in sorted((community_labels or {}).items())
        ]
    }
    (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2), encoding="utf-8")

    return G.number_of_nodes() + community_notes_written


def to_canvas(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    node_filenames: dict[str, str] | None = None,
) -> None:
    """Export graph as an Obsidian Canvas file - communities as groups, nodes as cards.

    Generates a structured layout: communities arranged in a grid, nodes within
    each community arranged in rows. Edges shown between connected nodes.
    Opens in Obsidian as an infinite canvas with community groupings visible.
    """
    # Obsidian canvas color codes (cycle through for communities)
    CANVAS_COLORS = ["1", "2", "3", "4", "5", "6"]  # red, orange, yellow, green, cyan, purple

    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        cleaned = re.sub(r"\.(md|mdx|markdown)$", "", cleaned, flags=re.IGNORECASE)
        return cleaned or "unnamed"

    # Build node_filenames if not provided (same dedup logic as to_obsidian)
    if node_filenames is None:
        node_filenames = {}
        seen_names: dict[str, int] = {}
        for node_id, data in G.nodes(data=True):
            base = safe_name(data.get("label", node_id))
            if base in seen_names:
                seen_names[base] += 1
                node_filenames[node_id] = f"{base}_{seen_names[base]}"
            else:
                seen_names[base] = 0
                node_filenames[node_id] = base

    num_communities = len(communities)
    cols = math.ceil(math.sqrt(num_communities)) if num_communities > 0 else 1
    rows = math.ceil(num_communities / cols) if num_communities > 0 else 1

    canvas_nodes: list[dict] = []
    canvas_edges: list[dict] = []

    # Lay out communities in a grid
    gap = 80
    group_x_offsets: list[int] = []
    group_y_offsets: list[int] = []

    # Precompute group sizes so we can calculate offsets
    sorted_cids = sorted(communities.keys())
    group_sizes: dict[int, tuple[int, int]] = {}
    for cid in sorted_cids:
        members = communities[cid]
        n = len(members)
        w = max(600, 220 * math.ceil(math.sqrt(n)) if n > 0 else 600)
        h = max(400, 100 * math.ceil(n / 3) + 120 if n > 0 else 400)
        group_sizes[cid] = (w, h)

    # Compute cumulative row heights and col widths for grid placement
    # Each grid cell uses the max width/height in its col/row
    col_widths: list[int] = []
    row_heights: list[int] = []
    for col_idx in range(cols):
        max_w = 0
        for row_idx in range(rows):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                w, _ = group_sizes[cid]
                max_w = max(max_w, w)
        col_widths.append(max_w)

    for row_idx in range(rows):
        max_h = 0
        for col_idx in range(cols):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                _, h = group_sizes[cid]
                max_h = max(max_h, h)
        row_heights.append(max_h)

    # Map from cid → (group_x, group_y, group_w, group_h)
    group_layout: dict[int, tuple[int, int, int, int]] = {}
    for idx, cid in enumerate(sorted_cids):
        col_idx = idx % cols
        row_idx = idx // cols
        gx = sum(col_widths[:col_idx]) + col_idx * gap
        gy = sum(row_heights[:row_idx]) + row_idx * gap
        gw, gh = group_sizes[cid]
        group_layout[cid] = (gx, gy, gw, gh)

    # Build set of all node_ids in canvas for edge filtering
    all_canvas_nodes: set[str] = set()
    for members in communities.values():
        all_canvas_nodes.update(members)

    # Generate group and node canvas entries
    for idx, cid in enumerate(sorted_cids):
        members = communities[cid]
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )
        gx, gy, gw, gh = group_layout[cid]
        canvas_color = CANVAS_COLORS[idx % len(CANVAS_COLORS)]

        # Group node
        canvas_nodes.append({
            "id": f"g{cid}",
            "type": "group",
            "label": community_name,
            "x": gx,
            "y": gy,
            "width": gw,
            "height": gh,
            "color": canvas_color,
        })

        # Node cards inside the group - rows of 3
        sorted_members = sorted(members, key=lambda n: G.nodes[n].get("label", n))
        for m_idx, node_id in enumerate(sorted_members):
            col = m_idx % 3
            row = m_idx // 3
            nx_x = gx + 20 + col * (180 + 20)
            nx_y = gy + 80 + row * (60 + 20)
            fname = node_filenames.get(node_id, safe_name(G.nodes[node_id].get("label", node_id)))
            canvas_nodes.append({
                "id": f"n_{node_id}",
                "type": "file",
                "file": f"{fname}.md",
                "x": nx_x,
                "y": nx_y,
                "width": 180,
                "height": 60,
            })

    # Generate edges - only between nodes both in canvas, cap at 200 highest-weight
    all_edges_weighted: list[tuple[float, str, str, str]] = []
    for u, v, edata in G.edges(data=True):
        if u in all_canvas_nodes and v in all_canvas_nodes:
            weight = edata.get("weight", 1.0)
            relation = edata.get("relation", "")
            conf = edata.get("confidence", "EXTRACTED")
            label = f"{relation} [{conf}]" if relation else f"[{conf}]"
            all_edges_weighted.append((weight, u, v, label))

    all_edges_weighted.sort(key=lambda x: -x[0])
    for weight, u, v, label in all_edges_weighted[:200]:
        canvas_edges.append({
            "id": f"e_{u}_{v}",
            "fromNode": f"n_{u}",
            "toNode": f"n_{v}",
            "label": label,
        })

    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    Path(output_path).write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")


def push_to_neo4j(
    G: nx.Graph,
    uri: str,
    user: str,
    password: str,
    communities: dict[int, list[str]] | None = None,
) -> dict[str, int]:
    """Push graph directly to a running Neo4j instance via the Python driver.

    Requires: pip install neo4j

    Uses MERGE so re-running is safe - nodes and edges are upserted, not duplicated.
    Returns a dict with counts of nodes and edges pushed.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError as e:
        raise ImportError(
            "neo4j driver not installed. Run: pip install neo4j"
        ) from e

    node_community = _node_community_map(communities) if communities else {}

    def _safe_rel(relation: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"

    def _safe_label(label: str) -> str:
        """Sanitize a Neo4j node label to prevent Cypher injection."""
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
        return sanitized if sanitized else "Entity"

    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes_pushed = 0
    edges_pushed = 0

    with driver.session() as session:
        for node_id, data in G.nodes(data=True):
            props = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}
            props["id"] = node_id
            cid = node_community.get(node_id)
            if cid is not None:
                props["community"] = cid
            ftype = _safe_label(data.get("file_type", "Entity").capitalize())
            session.run(
                f"MERGE (n:{ftype} {{id: $id}}) SET n += $props",
                id=node_id,
                props=props,
            )
            nodes_pushed += 1

        for u, v, data in G.edges(data=True):
            rel = _safe_rel(data.get("relation", "RELATED_TO"))
            props = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}
            session.run(
                f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
                src=u,
                tgt=v,
                props=props,
            )
            edges_pushed += 1

    driver.close()
    return {"nodes": nodes_pushed, "edges": edges_pushed}


def to_graphml(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
) -> None:
    """Export graph as GraphML - opens in Gephi, yEd, and any GraphML-compatible tool.

    Community IDs are written as a node attribute so Gephi can colour by community.
    Edge confidence (EXTRACTED/INFERRED/AMBIGUOUS) is preserved as an edge attribute.
    """
    H = G.copy()
    node_community = _node_community_map(communities)
    for node_id in H.nodes():
        H.nodes[node_id]["community"] = node_community.get(node_id, -1)
    nx.write_graphml(H, output_path)


def to_svg(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    figsize: tuple[int, int] = (20, 14),
) -> None:
    """Export graph as an SVG file using matplotlib + spring layout.

    Lightweight and embeddable - works in Obsidian notes, Notion, GitHub READMEs,
    and any markdown renderer. No JavaScript required.

    Node size scales with degree. Community colors match the HTML output.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError as e:
        raise ImportError("matplotlib not installed. Run: pip install matplotlib") from e

    node_community = _node_community_map(communities)

    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.axis("off")

    pos = nx.spring_layout(G, seed=42, k=2.0 / (G.number_of_nodes() ** 0.5 + 1))

    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1

    node_colors = [COMMUNITY_COLORS[node_community.get(n, 0) % len(COMMUNITY_COLORS)] for n in G.nodes()]
    node_sizes = [300 + 1200 * (degree.get(n, 1) / max_deg) for n in G.nodes()]

    # Draw edges - dashed for non-EXTRACTED
    for u, v, data in G.edges(data=True):
        conf = data.get("confidence", "EXTRACTED")
        style = "solid" if conf == "EXTRACTED" else "dashed"
        alpha = 0.6 if conf == "EXTRACTED" else 0.3
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        ax.plot([x0, x1], [y0, y1], color="#aaaaaa", linewidth=0.8,
                linestyle=style, alpha=alpha, zorder=1)

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                           node_size=node_sizes, alpha=0.9)
    nx.draw_networkx_labels(G, pos, ax=ax,
                            labels={n: G.nodes[n].get("label", n) for n in G.nodes()},
                            font_size=7, font_color="white")

    # Legend
    if community_labels:
        patches = [
            mpatches.Patch(
                color=COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)],
                label=f"{label} ({len(communities.get(cid, []))})",
            )
            for cid, label in sorted(community_labels.items())
        ]
        ax.legend(handles=patches, loc="upper left", framealpha=0.7,
                  facecolor="#2a2a4e", labelcolor="white", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, format="svg", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)


# ── Structure graph exports (feature 1) ─────────────────────────────────────

_STRUCTURE_KIND_COLORS = {
    "folder":   "#8b6f47",
    "file":     "#2b5876",
    "class":    "#a060c9",
    "method":   "#3ebf8f",
    "function": "#2a7d57",
    "global":   "#e08b3a",
}


def to_structure_json(structure: dict, output_path: str) -> None:
    """Serialize a structure payload produced by ``build_structure`` to JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2, sort_keys=False)


def to_structure_html(structure: dict, output_path: str) -> None:
    """Render a collapsible top-down structure graph with cross-edges overlayed.

    Layout inspired by PageIndex (hierarchy first, drill-down), but the payload
    is a real graph: hierarchy edges form the tree skeleton and cross-edges
    (calls/imports/inherits/uses/etc.) are drawn as secondary connections that
    lift to the nearest visible ancestor when descendants are collapsed.
    """
    payload_json = json.dumps(structure, ensure_ascii=False)
    title = _html.escape(structure.get("root_label") or "structure graph")
    html = _structure_html_shell(title, payload_json)
    Path(output_path).write_text(html, encoding="utf-8")


def _structure_html_shell(title: str, payload_json: str) -> str:
    colors_json = json.dumps(_STRUCTURE_KIND_COLORS)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>dummyindex structure — {title}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  :root {{
    --bg: #0f1115;
    --panel: #171a21;
    --line: #2a2f3a;
    --ink: #e6e7eb;
    --muted: #8b93a6;
    --accent: #7cc2ff;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; background: var(--bg); color: var(--ink);
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  #app {{ display: grid; grid-template-columns: 320px 1fr; height: 100vh; }}
  #sidebar {{ background: var(--panel); border-right: 1px solid var(--line);
              overflow: auto; padding: 14px; }}
  #graph {{ position: relative; }}
  #graph-canvas {{ position: absolute; inset: 0; }}
  h1 {{ font-size: 14px; text-transform: uppercase; letter-spacing: .08em;
        color: var(--muted); margin: 0 0 10px; }}
  .controls button {{ display: block; width: 100%; text-align: left;
        background: transparent; color: var(--ink); border: 1px solid var(--line);
        border-radius: 8px; padding: 8px 10px; margin-bottom: 6px; cursor: pointer;
        font-size: 13px; }}
  .controls button:hover {{ border-color: var(--accent); color: var(--accent); }}
  .controls label {{ display: flex; align-items: center; gap: 8px;
        font-size: 13px; color: var(--muted); margin-top: 10px; }}
  #search {{ width: 100%; padding: 8px 10px; background: var(--bg);
        border: 1px solid var(--line); color: var(--ink); border-radius: 8px;
        font-size: 13px; margin-bottom: 12px; }}
  #legend {{ margin-top: 18px; font-size: 12px; color: var(--muted); }}
  #legend span.dot {{ display: inline-block; width: 10px; height: 10px;
        border-radius: 50%; margin-right: 6px; vertical-align: middle; }}
  #legend li {{ list-style: none; padding: 3px 0; }}
  #stats {{ margin-top: 18px; font-size: 11px; color: var(--muted); line-height: 1.6; }}
  #node-card {{ position: absolute; right: 16px; top: 16px; width: 320px;
        background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
        padding: 14px; font-size: 13px; max-height: 70vh; overflow: auto;
        display: none; }}
  #node-card h2 {{ margin: 0 0 6px; font-size: 15px; }}
  #node-card .kind {{ display: inline-block; padding: 2px 8px; border-radius: 999px;
        font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
        color: var(--bg); margin-bottom: 10px; }}
  #node-card .section-title {{ text-transform: uppercase; letter-spacing: .08em;
        color: var(--muted); font-size: 11px; margin-top: 10px; margin-bottom: 4px; }}
  #node-card ul {{ margin: 0; padding-left: 16px; }}
</style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <h1>Structure Graph</h1>
    <input id="search" placeholder="Search labels…" type="search">
    <div class="controls">
      <button id="collapse-all">Collapse to folders</button>
      <button id="expand-files">Expand files</button>
      <button id="expand-all">Expand everything</button>
      <button id="reset-layout">Reset layout</button>
      <label><input id="toggle-cross" type="checkbox" checked> Show cross-edges</label>
    </div>
    <div id="legend">
      <div style="margin-bottom:6px">Kind</div>
      <ul id="legend-list"></ul>
    </div>
    <div id="stats"></div>
  </aside>
  <main id="graph">
    <div id="graph-canvas"></div>
    <div id="node-card"></div>
  </main>
</div>
<script>
const PAYLOAD = {payload_json};
const KIND_COLORS = {colors_json};
{_STRUCTURE_JS}
</script>
</body>
</html>"""


_STRUCTURE_JS = r"""
// Containers (folders, files) use box so the path / filename is readable inline.
// Units (classes, methods, functions, globals) use dot — a uniform fixed-size
// circle with the label rendered outside. The layout reserves a fixed collision
// radius per dot, and nodeSpacing is large enough that the external labels
// don't run into sibling dots either.
const KIND_SHAPE = {
  folder: "box",
  file: "box",
  class: "dot",
  method: "dot",
  function: "dot",
  global: "dot",
};
const UNIT_DOT_SIZE = 22;

// index payload
const nodesById = new Map(PAYLOAD.nodes.map(n => [n.id, n]));
const childrenByParent = new Map();
for (const n of PAYLOAD.nodes) childrenByParent.set(n.id, []);
for (const e of PAYLOAD.hierarchy_edges) {
  (childrenByParent.get(e.source) || []).push(e.target);
}

// precompute depth of each node in the hierarchy tree (root = 0).
// Passing this as `level` on each node pins vis-network's hierarchical
// layout, so cross-edges (calls/imports/etc.) cannot deform the tree.
const levelById = new Map();
(function computeLevels() {
  const queue = [[PAYLOAD.root_id, 0]];
  while (queue.length) {
    const [id, d] = queue.shift();
    if (levelById.has(id)) continue;
    levelById.set(id, d);
    for (const child of (childrenByParent.get(id) || [])) {
      queue.push([child, d + 1]);
    }
  }
  // any node not reachable from root (shouldn't normally happen) gets level 0
  for (const n of PAYLOAD.nodes) if (!levelById.has(n.id)) levelById.set(n.id, 0);
})();

// ancestors (root -> node, excluding node itself)
function ancestorsOf(id) {
  const chain = [];
  let cur = nodesById.get(id);
  while (cur && cur.parent) {
    chain.push(cur.parent);
    cur = nodesById.get(cur.parent);
  }
  return chain;
}

// initial expanded set: root + top-level folders
const expanded = new Set();
expanded.add(PAYLOAD.root_id);

function setExpansion(depth) {
  expanded.clear();
  expanded.add(PAYLOAD.root_id);
  if (depth < 1) { rerender(); return; }
  const queue = [[PAYLOAD.root_id, 0]];
  while (queue.length) {
    const [id, d] = queue.shift();
    if (d >= depth) continue;
    for (const child of (childrenByParent.get(id) || [])) {
      expanded.add(child);
      queue.push([child, d + 1]);
    }
  }
  rerender();
}

// a node is visible iff all ancestors are expanded
function isVisible(id) {
  const node = nodesById.get(id);
  if (!node) return false;
  if (!node.parent) return true;
  let cur = node;
  while (cur && cur.parent) {
    if (!expanded.has(cur.parent)) return false;
    cur = nodesById.get(cur.parent);
  }
  return true;
}

// nearest visible ancestor (including self)
function visibleAncestorOf(id) {
  let cur = nodesById.get(id);
  while (cur) {
    if (isVisible(cur.id)) return cur.id;
    if (!cur.parent) return null;
    cur = nodesById.get(cur.parent);
  }
  return null;
}

let showCross = true;

// Free-drag strategy: hierarchical layout runs ONCE for the initial render to
// place the tree. After that we snapshot every node's position, disable
// hierarchical layout, and use explicit x/y for every subsequent render. This
// removes the y-axis drag constraint that vis-network enforces while
// hierarchical layout is active, so nodes can be moved freely in any direction.
let initialLayoutDone = false;
const userPositions = new Map();

const HIERARCHICAL_OPTS = {
  enabled: true, direction: "UD", sortMethod: "directed",
  nodeSpacing: 280, levelSeparation: 180, treeSpacing: 320,
  blockShifting: true, edgeMinimization: true, parentCentralization: true,
};

const network = new vis.Network(document.getElementById("graph-canvas"), { nodes: [], edges: [] }, {
  layout: { hierarchical: HIERARCHICAL_OPTS },
  physics: { enabled: false },
  interaction: {
    hover: true,
    tooltipDelay: 120,
    dragNodes: true,
    dragView: true,
    zoomView: true,
    multiselect: false,
  },
  nodes: {
    borderWidth: 1,
    font: { color: "#f5f5f5", size: 13, face: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" },
    margin: 10,
    shapeProperties: { borderRadius: 6 },
    widthConstraint: { maximum: 180 },
  },
  edges: { smooth: { type: "cubicBezier" }, arrows: { to: { enabled: true, scaleFactor: 0.5 } } },
});

network.on("dragEnd", params => {
  if (!params.nodes || params.nodes.length === 0) return;
  const positions = network.getPositions(params.nodes);
  for (const id of params.nodes) {
    const p = positions[id];
    if (p) userPositions.set(id, { x: p.x, y: p.y });
  }
});

function placeNewNode(id) {
  // new node revealed after initial layout — position under parent, offset by sibling index
  const n = nodesById.get(id);
  if (!n || !n.parent) return { x: 0, y: 0 };
  const parentPos = userPositions.get(n.parent);
  if (!parentPos) return { x: 0, y: (levelById.get(id) || 0) * 180 };
  const visibleSiblings = (childrenByParent.get(n.parent) || []).filter(cid =>
    cid === id || userPositions.has(cid));
  const idx = Math.max(0, visibleSiblings.indexOf(id));
  const count = visibleSiblings.length || 1;
  return {
    x: parentPos.x + (idx - (count - 1) / 2) * 280,
    y: parentPos.y + 180,
  };
}

function rerender() {
  const visibleIds = PAYLOAD.nodes.filter(n => isVisible(n.id)).map(n => n.id);
  const visibleSet = new Set(visibleIds);

  const visNodes = visibleIds.map(id => {
    const n = nodesById.get(id);
    const color = KIND_COLORS[n.kind] || "#7cc2ff";
    const hasChildren = (childrenByParent.get(id) || []).length > 0;
    const isCollapsed = hasChildren && !expanded.has(id);
    const suffix = isCollapsed ? "  ▸" : (hasChildren ? "  ▾" : "");
    const shape = KIND_SHAPE[n.kind] || "dot";
    const isDot = shape === "dot";
    const node = {
      id,
      label: (n.label || id) + suffix,
      shape,
      color: {
        background: color,
        border: color,
        highlight: { background: color, border: "#ffffff" },
      },
      font: {
        color: "#f5f5f5",
        strokeWidth: 3,
        strokeColor: "#0f1115",
        background: isDot ? "rgba(15,17,21,0.72)" : undefined,
      },
      title: `${n.kind}: ${n.label}${n.source_file ? "\n" + n.source_file : ""}`,
    };
    if (isDot) {
      node.size = UNIT_DOT_SIZE;
      node.widthConstraint = undefined;
    }
    if (initialLayoutDone) {
      const saved = userPositions.get(id) || placeNewNode(id);
      node.x = saved.x;
      node.y = saved.y;
    } else {
      node.level = levelById.get(id) || 0;
    }
    return node;
  });

  const hierEdges = PAYLOAD.hierarchy_edges
    .filter(e => visibleSet.has(e.source) && visibleSet.has(e.target))
    .map((e, i) => ({
      id: `h_${i}`,
      from: e.source, to: e.target,
      color: { color: "#3a4256", opacity: 0.7 },
      width: 1.2,
      dashes: false,
    }));

  const crossAgg = new Map();
  if (showCross) {
    for (const e of PAYLOAD.cross_edges) {
      const src = visibleAncestorOf(e.source);
      const tgt = visibleAncestorOf(e.target);
      if (!src || !tgt || src === tgt) continue;
      const key = `${src}|${tgt}|${e.relation}`;
      const prev = crossAgg.get(key);
      if (prev) prev.count += 1;
      else crossAgg.set(key, { from: src, to: tgt, relation: e.relation, count: 1 });
    }
  }
  const crossEdges = Array.from(crossAgg.values()).map((e, i) => ({
    id: `c_${i}`,
    from: e.from, to: e.to,
    label: e.count > 1 ? `${e.relation} ×${e.count}` : e.relation,
    color: { color: "#7cc2ff", opacity: 0.75 },
    font: { color: "#cfe3ff", size: 10, strokeWidth: 3, strokeColor: "#0f1115" },
    width: Math.min(4, 1 + Math.log2(e.count + 1)),
    dashes: [4, 4],
    arrows: { to: { enabled: true, scaleFactor: 0.6 } },
  }));

  network.setData({ nodes: visNodes, edges: hierEdges.concat(crossEdges) });

  if (!initialLayoutDone) {
    // Snapshot positions the hierarchical pass just computed, then disable
    // hierarchical layout so nodes can be dragged freely on both axes.
    const computed = network.getPositions(visibleIds);
    for (const id of visibleIds) {
      const p = computed[id];
      if (p) userPositions.set(id, { x: p.x, y: p.y });
    }
    network.setOptions({ layout: { hierarchical: { enabled: false } } });
    initialLayoutDone = true;
  } else {
    // Capture positions for any newly-visible nodes so they stick on next render.
    const computed = network.getPositions(visibleIds);
    for (const id of visibleIds) {
      if (!userPositions.has(id) && computed[id]) {
        userPositions.set(id, { x: computed[id].x, y: computed[id].y });
      }
    }
  }
}

// click: toggle expansion
network.on("click", params => {
  if (params.nodes.length === 0) return;
  const id = params.nodes[0];
  const n = nodesById.get(id);
  if (!n) return;
  const hasChildren = (childrenByParent.get(id) || []).length > 0;
  if (hasChildren) {
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
    rerender();
  }
  showCard(id);
});

function showCard(id) {
  const n = nodesById.get(id);
  if (!n) return;
  const card = document.getElementById("node-card");
  const color = KIND_COLORS[n.kind] || "#7cc2ff";
  const incoming = PAYLOAD.cross_edges.filter(e => e.target === id);
  const outgoing = PAYLOAD.cross_edges.filter(e => e.source === id);
  card.innerHTML = `
    <span class="kind" style="background:${color}">${n.kind}</span>
    <h2>${escapeHtml(n.label)}</h2>
    <div style="color:var(--muted); font-size:12px">${escapeHtml(n.source_file || "")} ${n.source_location ? "· " + n.source_location : ""}</div>
    <div class="section-title">Children</div>
    <div>${(childrenByParent.get(id) || []).length}</div>
    <div class="section-title">Uses (outgoing)</div>
    <ul>${outgoing.slice(0, 20).map(e => `<li>${escapeHtml(e.relation)} → ${escapeHtml((nodesById.get(e.target) || {}).label || e.target)}</li>`).join("") || "<li><em>none</em></li>"}</ul>
    <div class="section-title">Used by (incoming)</div>
    <ul>${incoming.slice(0, 20).map(e => `<li>${escapeHtml((nodesById.get(e.source) || {}).label || e.source)} → ${escapeHtml(e.relation)}</li>`).join("") || "<li><em>none</em></li>"}</ul>
  `;
  card.style.display = "block";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

// controls
// Any control that changes the visible set to a fresh structural shape re-runs
// the hierarchical layout so newly-revealed subtrees lay out cleanly without
// overlap. Individual click-to-expand keeps user-dragged positions intact.
function relayoutFromScratch() {
  userPositions.clear();
  initialLayoutDone = false;
  network.setOptions({ layout: { hierarchical: HIERARCHICAL_OPTS } });
  rerender();
  network.fit({ animation: { duration: 300 } });
}
document.getElementById("collapse-all").onclick = () => {
  expanded.clear();
  expanded.add(PAYLOAD.root_id);
  relayoutFromScratch();
};
document.getElementById("expand-files").onclick = () => {
  expanded.clear();
  for (const n of PAYLOAD.nodes) {
    if (n.kind === "folder") expanded.add(n.id);
  }
  relayoutFromScratch();
};
document.getElementById("expand-all").onclick = () => {
  expanded.clear();
  for (const n of PAYLOAD.nodes) expanded.add(n.id);
  relayoutFromScratch();
};
document.getElementById("reset-layout").onclick = () => {
  userPositions.clear();
  initialLayoutDone = false;
  network.setOptions({ layout: { hierarchical: HIERARCHICAL_OPTS } });
  rerender();
  network.fit({ animation: { duration: 300 } });
};
document.getElementById("toggle-cross").onchange = e => {
  showCross = e.target.checked;
  rerender();
};
document.getElementById("search").oninput = e => {
  const q = e.target.value.trim().toLowerCase();
  if (!q) return;
  const match = PAYLOAD.nodes.find(n => (n.label || "").toLowerCase().includes(q));
  if (!match) return;
  for (const a of ancestorsOf(match.id)) expanded.add(a);
  rerender();
  setTimeout(() => network.focus(match.id, { animation: true, scale: 1.1 }), 50);
};

// legend + stats
const legendList = document.getElementById("legend-list");
const kindCounts = new Map();
for (const n of PAYLOAD.nodes) kindCounts.set(n.kind, (kindCounts.get(n.kind) || 0) + 1);
for (const [kind, count] of kindCounts) {
  const color = KIND_COLORS[kind] || "#7cc2ff";
  const li = document.createElement("li");
  li.innerHTML = `<span class="dot" style="background:${color}"></span>${kind} · ${count}`;
  legendList.appendChild(li);
}
document.getElementById("stats").innerHTML =
  `${PAYLOAD.nodes.length} nodes<br>${PAYLOAD.hierarchy_edges.length} hierarchy edges<br>${PAYLOAD.cross_edges.length} cross-edges`;

// initial: expand root + its immediate children (folders)
for (const c of (childrenByParent.get(PAYLOAD.root_id) || [])) expanded.add(c);
rerender();
"""


# --------------------------------------------------------------------------- #
# Flow hypergraph exports (Feature 2). Parallel to to_structure_json/html.
# --------------------------------------------------------------------------- #

# Per-flow distinct hues. The viewer cycles through these so each flow gets a
# stable color regardless of entry kind, which is what makes overlap visually
# obvious when multiple flows are rendered at once.
_FLOW_PALETTE = [
    "#7cc2ff", "#ffaa3a", "#a060c9", "#3ebf8f", "#ff6b9c",
    "#e8d34d", "#5ad6b8", "#ff8a65", "#9eb3ff", "#c9e265",
    "#ff5a8c", "#7af0ff", "#d68aff", "#ffb74d", "#80d8a3",
]


def to_flow_json(
    flows: list[dict],
    G: nx.Graph,
    output_path: str,
    *,
    overlap_index: dict[str, list[str]] | None = None,
) -> None:
    """Write ``flow_graph.json`` — full flow catalog plus the slice of
    nodes/edges referenced by any flow sequence."""
    referenced_nodes: dict[str, dict] = {}
    referenced_edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    for flow in flows:
        for nid in flow.get("nodes", []) or []:
            if nid in referenced_nodes or nid not in G.nodes:
                continue
            attrs = dict(G.nodes[nid])
            attrs["id"] = nid
            referenced_nodes[nid] = attrs
        for step in flow.get("sequence", []) or []:
            key = (step.get("source"), step.get("target"))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            referenced_edges.append({
                "source": step.get("source"),
                "target": step.get("target"),
                "relation": step.get("relation", "calls"),
                "confidence": step.get("confidence", "EXTRACTED"),
                "source_location": step.get("source_location", ""),
            })

    payload = {
        "schema_version": "1.2",
        "flows": flows,
        "nodes": [referenced_nodes[k] for k in sorted(referenced_nodes)],
        "edges": referenced_edges,
        "overlap_index": overlap_index or {},
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def to_flow_html(
    flows: list[dict],
    G: nx.Graph,
    output_path: str,
    *,
    overlap_index: dict[str, list[str]] | None = None,
) -> None:
    """Render an interactive ``flow_graph.html`` viewer.

    Three panels: flow list (left), selected flow timeline (center),
    node inspector with overlap (right). Pure static HTML + vis-network
    from CDN, no build step."""
    referenced_nodes: dict[str, dict] = {}
    for flow in flows:
        for nid in flow.get("nodes", []) or []:
            if nid in referenced_nodes or nid not in G.nodes:
                continue
            attrs = dict(G.nodes[nid])
            attrs["id"] = nid
            referenced_nodes[nid] = attrs
    payload = {
        "flows": flows,
        "nodes": [referenced_nodes[k] for k in sorted(referenced_nodes)],
        "overlap_index": overlap_index or {},
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    colors_json = json.dumps(_FLOW_PALETTE)
    title = _html.escape("Flow Hypergraph")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>dummyindex flows — {title}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  :root {{ --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --ink:#e6e7eb;
           --muted:#8b93a6; --accent:#7cc2ff; --shared:#ffaa3a; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; height:100%; background:var(--bg); color:var(--ink);
                font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  #app {{ display:grid; grid-template-columns:300px 1fr 320px; height:100vh; }}
  aside {{ background:var(--panel); border-right:1px solid var(--line); overflow:auto; padding:14px; }}
  #inspector {{ border-right:0; border-left:1px solid var(--line); }}
  h1 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em;
        color:var(--muted); margin:0 0 10px; }}
  #search {{ width:100%; padding:8px 10px; background:var(--bg); border:1px solid var(--line);
             color:var(--ink); border-radius:8px; font-size:13px; margin-bottom:10px; }}
  .flow {{ padding:10px; border:1px solid var(--line); border-radius:8px; margin-bottom:8px;
           cursor:pointer; display:flex; gap:10px; align-items:flex-start;
           transition: border-color .15s, background .15s; }}
  .flow:hover {{ border-color:var(--accent); }}
  .flow.active {{ border-color:var(--accent); background:#1f2533; }}
  .flow input[type=checkbox] {{ margin-top:3px; cursor:pointer; flex:0 0 auto; }}
  .flow-body {{ flex:1; min-width:0; }}
  .flow-color {{ width:10px; height:10px; border-radius:3px; margin-top:5px; flex:0 0 auto; }}
  .flow .name {{ font-size:13px; font-weight:600; margin-bottom:4px;
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .flow .meta {{ font-size:11px; color:var(--muted); display:flex; gap:8px; flex-wrap:wrap; }}
  .chip {{ display:inline-block; padding:2px 6px; border-radius:999px; font-size:10px;
           text-transform:uppercase; letter-spacing:.05em; color:#0f1115; font-weight:600; }}
  .toolbar-row {{ display:flex; gap:6px; margin-bottom:8px; flex-wrap:wrap; }}
  .toolbar-row button {{ flex:1; padding:6px 8px; background:var(--bg); border:1px solid var(--line);
                          color:var(--ink); border-radius:6px; cursor:pointer; font-size:11px; }}
  .toolbar-row button:hover {{ border-color:var(--accent); color:var(--accent); }}
  .toolbar-row button.on {{ border-color:var(--accent); background:#1f2533; color:var(--accent); }}
  #canvas {{ position:relative; }}
  #graph {{ position:absolute; inset:0; }}
  #legend {{ position:absolute; top:12px; left:12px; background:rgba(15,17,21,0.85);
             padding:8px 10px; border:1px solid var(--line); border-radius:6px;
             font-size:11px; color:var(--muted); max-width:260px; pointer-events:none; }}
  #legend .row {{ display:flex; align-items:center; gap:6px; margin:2px 0; }}
  #legend .swatch {{ width:10px; height:10px; border-radius:50%; }}
  .insp-section {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em;
                   color:var(--muted); margin-top:14px; margin-bottom:6px; }}
  .insp ul {{ margin:0; padding-left:16px; font-size:12px; }}
  .insp a {{ color:var(--accent); text-decoration:none; cursor:pointer; }}
  .insp a:hover {{ text-decoration:underline; }}
  .pill {{ display:inline-block; padding:1px 6px; border-radius:3px; font-size:10px;
           background:var(--bg); border:1px solid var(--line); color:var(--muted); margin-right:4px; }}
</style>
</head>
<body>
<div id="app">
  <aside>
    <h1>Flows</h1>
    <input id="search" placeholder="Search flows…" type="search">
    <div class="toolbar-row">
      <button id="btn-all">All</button>
      <button id="btn-none">None</button>
      <button id="btn-overlap" title="Show only flows with overlap">Overlap</button>
    </div>
    <div class="toolbar-row">
      <button id="layout-force" class="on">Force</button>
      <button id="layout-hier">Hier</button>
      <button id="layout-lane">Swim</button>
    </div>
    <div class="toolbar-row">
      <button id="toggle-physics" class="on">Physics on</button>
      <button id="toggle-hulls" class="on">Hulls on</button>
    </div>
    <div id="flow-list"></div>
  </aside>
  <main id="canvas">
    <div id="graph"></div>
    <div id="legend"></div>
  </main>
  <aside id="inspector" class="insp">
    <h1>Inspector</h1>
    <div id="insp-content"><em style="color:var(--muted);font-size:12px">Click a node to see details.</em></div>
  </aside>
</div>
<script>
const PAYLOAD = {payload_json};
const PALETTE = {colors_json};
{_FLOW_VIEWER_JS}
</script>
</body>
</html>"""
    Path(output_path).write_text(html, encoding="utf-8")


_FLOW_VIEWER_JS = r"""
const flows = PAYLOAD.flows || [];
const overlap = PAYLOAD.overlap_index || {};
const nodesById = new Map();
for (const n of (PAYLOAD.nodes || [])) nodesById.set(n.id, n);

// Stable per-flow color from PALETTE, indexed by flow position.
const flowColor = new Map();
for (let i = 0; i < flows.length; i++) {
  flowColor.set(flows[i].id, PALETTE[i % PALETTE.length]);
}

const flowList = document.getElementById("flow-list");
const search = document.getElementById("search");
const inspContent = document.getElementById("insp-content");
const legendEl = document.getElementById("legend");
const graphEl = document.getElementById("graph");

const selected = new Set();           // flow ids currently visible
let layout = "force";                  // "force" | "hier" | "lane"
let physicsOn = true;
let hullsOn = true;
let network = null;
let nodesDS = null;
let edgesDS = null;
let lastSelectedNode = null;

function init() {
  for (const f of flows) selected.add(f.id);  // default: ALL flows visible at once
  bindToolbar();
  renderFlowList(search.value);
  rebuild();
}

function bindToolbar() {
  document.getElementById("btn-all").onclick = () => { for (const f of flows) selected.add(f.id); renderFlowList(search.value); rebuild(); };
  document.getElementById("btn-none").onclick = () => { selected.clear(); renderFlowList(search.value); rebuild(); };
  document.getElementById("btn-overlap").onclick = () => {
    selected.clear();
    const sharedNodes = Object.entries(overlap).filter(([_, fs]) => fs.length > 1).map(([_, fs]) => fs).flat();
    for (const fid of sharedNodes) selected.add(fid);
    renderFlowList(search.value); rebuild();
  };
  document.getElementById("layout-force").onclick = () => setLayout("force");
  document.getElementById("layout-hier").onclick  = () => setLayout("hier");
  document.getElementById("layout-lane").onclick  = () => setLayout("lane");
  document.getElementById("toggle-physics").onclick = () => { physicsOn = !physicsOn;
    document.getElementById("toggle-physics").classList.toggle("on", physicsOn);
    document.getElementById("toggle-physics").textContent = "Physics " + (physicsOn ? "on" : "off");
    if (network) network.setOptions({ physics: physicsOn });
  };
  document.getElementById("toggle-hulls").onclick = () => { hullsOn = !hullsOn;
    document.getElementById("toggle-hulls").classList.toggle("on", hullsOn);
    document.getElementById("toggle-hulls").textContent = "Hulls " + (hullsOn ? "on" : "off");
    if (network) network.redraw();
  };
  search.oninput = () => renderFlowList(search.value);
}

function setLayout(name) {
  layout = name;
  for (const id of ["force","hier","lane"]) {
    document.getElementById("layout-" + id).classList.toggle("on", id === name);
  }
  rebuild();
}

function flowMatches(f, lower) {
  if (!lower) return true;
  const haystack = (f.label || "") + " " + (f.id || "") + " " + (f.entry_kind || "");
  const partLabels = (f.nodes || []).map(id => (nodesById.get(id) || {}).label || "").join(" ");
  return (haystack + " " + partLabels).toLowerCase().includes(lower);
}

function renderFlowList(filter) {
  const lower = (filter || "").toLowerCase();
  flowList.innerHTML = "";
  for (const f of flows) {
    if (!flowMatches(f, lower)) continue;
    const isOn = selected.has(f.id);
    const div = document.createElement("div");
    div.className = "flow" + (isOn ? " active" : "");
    const c = flowColor.get(f.id);
    const sharedCount = (f.nodes || []).filter(nid => (overlap[nid] || []).length > 1).length;
    div.innerHTML = `
      <input type="checkbox" ${isOn ? "checked" : ""}>
      <div class="flow-color" style="background:${c}"></div>
      <div class="flow-body">
        <div class="name" title="${escape(f.label || f.id)}">${escape(f.label || f.id)}</div>
        <div class="meta">
          <span class="chip" style="background:${c}">${f.entry_kind || "?"}</span>
          <span>${(f.nodes || []).length} nodes</span>
          ${sharedCount > 0 ? `<span class="pill" title="nodes also in another flow">∩ ${sharedCount}</span>` : ""}
          <span>${f.confidence || ""}</span>
          <span>sal ${(f.salience || 0).toFixed(2)}</span>
        </div>
      </div>
    `;
    div.onclick = (ev) => {
      const wasOn = selected.has(f.id);
      // Click on row = solo this flow (single-select feel); click on checkbox = toggle.
      if (ev.target.tagName === "INPUT") {
        if (wasOn) selected.delete(f.id); else selected.add(f.id);
      } else {
        selected.clear();
        selected.add(f.id);
      }
      renderFlowList(search.value);
      rebuild();
    };
    flowList.appendChild(div);
  }
}

function rebuild() {
  const visible = flows.filter(f => selected.has(f.id));
  const nodeIds = new Set();
  for (const f of visible) for (const nid of (f.nodes || [])) nodeIds.add(nid);

  const visNodes = [];
  for (const nid of nodeIds) {
    const n = nodesById.get(nid) || { id: nid, label: nid };
    const memberships = (overlap[nid] || []).filter(fid => selected.has(fid));
    const isShared = memberships.length > 1;
    // Pick primary color for the node = first selected flow it belongs to.
    const primaryFlowId = memberships[0] || (overlap[nid] || [])[0];
    const baseColor = primaryFlowId ? flowColor.get(primaryFlowId) : "#7cc2ff";
    const size = 12 + Math.min(20, memberships.length * 6);  // bigger when in many flows
    visNodes.push({
      id: nid,
      label: n.label || nid,
      title: `${n.label || nid}\n${n.source_file || ""}\nin ${memberships.length} flow(s)`,
      shape: "dot",
      size,
      color: {
        background: baseColor,
        border: isShared ? "#ffaa3a" : darken(baseColor, 0.4),
        highlight: { background: lighten(baseColor, 0.2), border: "#ffffff" },
      },
      borderWidth: isShared ? 3 : 1,
      font: { color: "#e6e7eb", size: 11, strokeWidth: 3, strokeColor: "#0f1115" },
      __sourceFile: n.source_file || "",
    });
  }

  const visEdges = [];
  const seenEdgeKeys = new Set();
  for (const f of visible) {
    const c = flowColor.get(f.id);
    for (const step of (f.sequence || [])) {
      const key = `${f.id}|${step.source}|${step.target}`;
      if (seenEdgeKeys.has(key)) continue;
      seenEdgeKeys.add(key);
      visEdges.push({
        from: step.source, to: step.target,
        arrows: { to: { enabled: true, scaleFactor: 0.6 } },
        color: { color: c, opacity: 0.6, highlight: c },
        width: 1.5,
        smooth: { type: "curvedCW", roundness: 0.15 },
        title: `${f.label || f.id} · ${step.confidence || ""}`,
      });
    }
  }

  // Cluster anchors: invisible per-flow pseudo-node + hidden tether edges to
  // every member. Anchors repel each other under forceAtlas2 so flows that
  // share zero nodes physically separate, eliminating false hull overlap.
  const anchorIds = new Set();
  if (layout === "force") {
    for (const f of visible) {
      const anchorId = `__anchor__${f.id}`;
      anchorIds.add(anchorId);
      visNodes.push({
        id: anchorId, label: "",
        shape: "dot", size: 1,
        color: { background: "rgba(0,0,0,0)", border: "rgba(0,0,0,0)" },
        font: { color: "rgba(0,0,0,0)" },
        physics: true, mass: 4, chosen: false,
        __anchor: true,
      });
      for (const nid of (f.nodes || [])) {
        if (!nodeIds.has(nid)) continue;
        visEdges.push({
          from: anchorId, to: nid,
          color: { color: "rgba(0,0,0,0)", opacity: 0 },
          width: 0, length: 90, smooth: false,
          arrows: { to: { enabled: false } },
          __tether: true,
        });
      }
    }
  }

  nodesDS = new vis.DataSet(visNodes);
  edgesDS = new vis.DataSet(visEdges);

  if (network) { network.destroy(); network = null; }
  network = new vis.Network(graphEl, { nodes: nodesDS, edges: edgesDS }, layoutOptions());
  network.on("selectNode", params => {
    if (params.nodes.length && !String(params.nodes[0]).startsWith("__anchor__")) {
      showInspector(params.nodes[0]);
    }
  });
  network.on("deselectNode", () => { lastSelectedNode = null; });
  network.on("beforeDrawing", ctx => { if (hullsOn) drawHulls(ctx, visible); });
  // Freeze physics once stabilized so anchored clusters don't keep spinning.
  network.once("stabilizationIterationsDone", () => {
    if (network) network.setOptions({ physics: false });
    physicsOn = false;
    const btn = document.getElementById("toggle-physics");
    if (btn) { btn.classList.remove("on"); btn.textContent = "Physics off"; }
  });

  renderLegend(visible);
}

function layoutOptions() {
  const base = {
    interaction: { hover: true, tooltipDelay: 100, dragNodes: true, multiselect: true, navigationButtons: true, keyboard: true },
    physics: physicsOn,
  };
  if (layout === "hier") {
    return Object.assign({}, base, {
      layout: { hierarchical: { direction: "UD", sortMethod: "directed", nodeSpacing: 130, levelSeparation: 120 } },
      physics: false,
    });
  }
  if (layout === "lane") {
    // Pre-position nodes by source_file (one swim lane per file). Disable physics so the lanes hold.
    setTimeout(() => {
      if (!nodesDS) return;
      const files = Array.from(new Set(nodesDS.get().map(n => n.__sourceFile || "(none)"))).sort();
      const laneHeight = 180;
      const update = [];
      for (const file of files) {
        const laneIdx = files.indexOf(file);
        const inLane = nodesDS.get().filter(n => (n.__sourceFile || "(none)") === file);
        for (let i = 0; i < inLane.length; i++) {
          update.push({ id: inLane[i].id, x: -600 + i * 140, y: -400 + laneIdx * laneHeight, fixed: { x: false, y: true } });
        }
      }
      nodesDS.update(update);
      if (network) network.fit({ animation: true });
    }, 50);
    return Object.assign({}, base, { physics: physicsOn, layout: { randomSeed: 7 } });
  }
  return Object.assign({}, base, {
    layout: { improvedLayout: true, randomSeed: 7 },
    // High damping kills rotational momentum that anchored clusters can pick up.
    physics: { enabled: physicsOn, solver: "forceAtlas2Based",
               forceAtlas2Based: { gravitationalConstant: -110, centralGravity: 0.02, springLength: 130, springConstant: 0.07, damping: 0.9 },
               stabilization: { iterations: 300, fit: true } },
  });
}

// Convex hull around each visible flow's node positions, drawn translucent on the canvas.
function drawHulls(ctx, visible) {
  if (!network) return;
  for (const f of visible) {
    const pts = [];
    for (const nid of (f.nodes || [])) {
      if (!nodesDS.get(nid)) continue;
      const p = network.getPositions([nid])[nid];
      if (p) pts.push([p.x, p.y]);
    }
    if (pts.length < 2) continue;
    const hull = convexHull(pts);
    if (hull.length < 2) continue;
    // Tighter padding so hulls don't reach into a neighboring flow's territory.
    const padded = expandHull(hull, 18);
    const c = flowColor.get(f.id);
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(padded[0][0], padded[0][1]);
    for (let i = 1; i < padded.length; i++) ctx.lineTo(padded[i][0], padded[i][1]);
    ctx.closePath();
    ctx.fillStyle = hexToRgba(c, 0.12);
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = hexToRgba(c, 0.7);
    ctx.stroke();
    // Label hull with flow name
    const cx = padded.reduce((a,p) => a + p[0], 0) / padded.length;
    const top = Math.min(...padded.map(p => p[1]));
    ctx.fillStyle = hexToRgba(c, 0.95);
    ctx.font = "bold 12px -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(f.label || f.id, cx, top - 8);
    ctx.restore();
  }
}

// Andrew's monotone chain.
function convexHull(points) {
  const pts = points.slice().sort((a,b) => a[0]-b[0] || a[1]-b[1]);
  if (pts.length <= 1) return pts;
  const cross = (o,a,b) => (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0]);
  const lower = [];
  for (const p of pts) { while (lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) lower.pop(); lower.push(p); }
  const upper = [];
  for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) upper.pop(); upper.push(p); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function expandHull(hull, pad) {
  const cx = hull.reduce((a,p) => a + p[0], 0) / hull.length;
  const cy = hull.reduce((a,p) => a + p[1], 0) / hull.length;
  return hull.map(([x,y]) => {
    const dx = x - cx, dy = y - cy;
    const len = Math.hypot(dx, dy) || 1;
    return [x + (dx/len) * pad, y + (dy/len) * pad];
  });
}

function showInspector(nid) {
  lastSelectedNode = nid;
  const n = nodesById.get(nid) || { id: nid, label: nid };
  const memberships = overlap[nid] || [];
  const items = memberships.map(fid => {
    const f = flows.find(x => x.id === fid);
    if (!f) return "";
    const c = flowColor.get(fid);
    const isOn = selected.has(fid);
    return `<li><span style="display:inline-block;width:8px;height:8px;background:${c};border-radius:2px;margin-right:6px"></span>` +
           `<a data-flow="${escape(fid)}">${escape(f.label || fid)}</a> ` +
           `<span class="pill">${isOn ? "visible" : "hidden"}</span></li>`;
  }).join("");
  inspContent.innerHTML = `
    <div style="font-size:14px;font-weight:600">${escape(n.label || nid)}</div>
    <div style="font-size:11px;color:var(--muted);word-break:break-all">${escape(n.source_file || "")}</div>
    <div class="insp-section">In ${memberships.length} flow${memberships.length === 1 ? "" : "s"}</div>
    <ul>${items || '<li style="color:var(--muted)">no flow membership</li>'}</ul>
    <div class="insp-section">Actions</div>
    <ul>
      <li><a id="solo-here">Solo this node's flows</a></li>
      <li><a id="add-others">Add all flows containing this node</a></li>
    </ul>
  `;
  for (const a of inspContent.querySelectorAll("a[data-flow]")) {
    a.onclick = (e) => { e.preventDefault(); const fid = a.dataset.flow;
      selected.clear(); selected.add(fid); renderFlowList(search.value); rebuild();
    };
  }
  const solo = inspContent.querySelector("#solo-here");
  if (solo) solo.onclick = (e) => { e.preventDefault(); selected.clear(); for (const fid of memberships) selected.add(fid); renderFlowList(search.value); rebuild(); };
  const addO = inspContent.querySelector("#add-others");
  if (addO) addO.onclick = (e) => { e.preventDefault(); for (const fid of memberships) selected.add(fid); renderFlowList(search.value); rebuild(); };
}

function renderLegend(visible) {
  if (!visible.length) { legendEl.innerHTML = '<em style="color:var(--muted)">No flows selected. Click "All" or pick from the sidebar.</em>'; return; }
  const sharedCount = Object.values(overlap).filter(fs => fs.filter(f => selected.has(f)).length > 1).length;
  let html = `<div style="margin-bottom:6px"><b>${visible.length}</b> flow${visible.length===1?"":"s"} · <b>${sharedCount}</b> shared node${sharedCount===1?"":"s"}</div>`;
  for (const f of visible.slice(0, 12)) {
    const c = flowColor.get(f.id);
    html += `<div class="row"><span class="swatch" style="background:${c}"></span><span>${escape(f.label || f.id)}</span></div>`;
  }
  if (visible.length > 12) html += `<div class="row"><span style="color:var(--muted)">+${visible.length - 12} more</span></div>`;
  legendEl.innerHTML = html;
}

// ----- color helpers -----
function hexToRgba(hex, a) {
  const h = hex.replace("#","");
  const n = parseInt(h.length === 3 ? h.split("").map(c => c+c).join("") : h, 16);
  return `rgba(${(n>>16)&255}, ${(n>>8)&255}, ${n&255}, ${a})`;
}
function lighten(hex, amt) {
  const [r,g,b] = hexToRgba(hex,1).match(/\d+/g).map(Number);
  return `rgb(${Math.min(255,r+255*amt)|0}, ${Math.min(255,g+255*amt)|0}, ${Math.min(255,b+255*amt)|0})`;
}
function darken(hex, amt) {
  const [r,g,b] = hexToRgba(hex,1).match(/\d+/g).map(Number);
  return `rgb(${Math.max(0,r*(1-amt))|0}, ${Math.max(0,g*(1-amt))|0}, ${Math.max(0,b*(1-amt))|0})`;
}
function escape(s) {
  return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

init();
"""


# --------------------------------------------------------------------------- #
# Feature hypergraph exports (Feature 3). Parallel to to_flow_*.
# --------------------------------------------------------------------------- #

_FEATURE_PALETTE = [
    "#7cc2ff", "#ffaa3a", "#a060c9", "#3ebf8f", "#ff6b9c",
    "#e8d34d", "#5ad6b8", "#ff8a65", "#9eb3ff", "#c9e265",
    "#ff5a8c", "#7af0ff", "#d68aff", "#ffb74d", "#80d8a3",
    "#ff7f7f", "#88c0d0", "#bf616a", "#a3be8c", "#ebcb8b",
]


def to_feature_json(
    features: list[dict],
    G: nx.Graph,
    output_path: str,
    *,
    feature_dependencies: list[dict] | None = None,
    overlap_matrix: dict[str, list[str]] | None = None,
    orphans: list[str] | None = None,
) -> None:
    """Write ``feature_graph.json`` — full feature catalog plus the slice
    of nodes/edges touched, plus feature-to-feature dependencies and the
    node→features overlap matrix."""
    referenced_nodes: dict[str, dict] = {}
    for feature in features:
        for nid in feature.get("nodes", []) or []:
            if nid in referenced_nodes or nid not in G.nodes:
                continue
            attrs = dict(G.nodes[nid])
            attrs["id"] = nid
            referenced_nodes[nid] = attrs

    # Slice of edges among referenced nodes — gives the viewer a calls/imports
    # backdrop without loading the full graph.
    referenced_edges: list[dict] = []
    nid_set = set(referenced_nodes)
    for u, v, data in G.edges(data=True):
        if u in nid_set and v in nid_set:
            referenced_edges.append({
                "source": u,
                "target": v,
                "relation": data.get("relation", ""),
                "confidence": data.get("confidence", "EXTRACTED"),
            })

    payload = {
        "schema_version": "1.3",
        "features": features,
        "nodes": [referenced_nodes[k] for k in sorted(referenced_nodes)],
        "edges": referenced_edges,
        "overlap_matrix": overlap_matrix or {},
        "feature_dependencies": feature_dependencies or [],
        "orphans": orphans or [],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def to_feature_html(
    features: list[dict],
    G: nx.Graph,
    output_path: str,
    *,
    feature_dependencies: list[dict] | None = None,
    overlap_matrix: dict[str, list[str]] | None = None,
    orphans: list[str] | None = None,
) -> None:
    """Render ``feature_graph.html`` — multi-feature view with hulls,
    feature-to-feature dependency arrows between hull centroids, role-grouped
    inspector, and a table mode for big feature counts."""
    referenced_nodes: dict[str, dict] = {}
    for feature in features:
        for nid in feature.get("nodes", []) or []:
            if nid in referenced_nodes or nid not in G.nodes:
                continue
            attrs = dict(G.nodes[nid])
            attrs["id"] = nid
            referenced_nodes[nid] = attrs
    payload = {
        "features": features,
        "nodes": [referenced_nodes[k] for k in sorted(referenced_nodes)],
        "overlap_matrix": overlap_matrix or {},
        "feature_dependencies": feature_dependencies or [],
        "orphans": orphans or [],
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    palette_json = json.dumps(_FEATURE_PALETTE)
    title = _html.escape("Feature Hypergraph")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>dummyindex features — {title}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  :root {{ --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --ink:#e6e7eb;
           --muted:#8b93a6; --accent:#7cc2ff; --shared:#ffaa3a; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; height:100%; background:var(--bg); color:var(--ink);
                font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  #app {{ display:grid; grid-template-columns:320px 1fr 340px; height:100vh; }}
  aside {{ background:var(--panel); border-right:1px solid var(--line); overflow:auto; padding:14px; }}
  #inspector {{ border-right:0; border-left:1px solid var(--line); }}
  h1 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin:0 0 10px; }}
  #search {{ width:100%; padding:8px 10px; background:var(--bg); border:1px solid var(--line); color:var(--ink); border-radius:8px; font-size:13px; margin-bottom:10px; }}
  .feature {{ padding:10px; border:1px solid var(--line); border-radius:8px; margin-bottom:8px;
              cursor:pointer; display:flex; gap:10px; align-items:flex-start; }}
  .feature:hover {{ border-color:var(--accent); }}
  .feature.active {{ border-color:var(--accent); background:#1f2533; }}
  .feature input[type=checkbox] {{ margin-top:3px; cursor:pointer; flex:0 0 auto; }}
  .feature-color {{ width:10px; height:10px; border-radius:3px; margin-top:5px; flex:0 0 auto; }}
  .feature-body {{ flex:1; min-width:0; }}
  .feature .name {{ font-size:13px; font-weight:600; margin-bottom:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .feature .meta {{ font-size:11px; color:var(--muted); display:flex; gap:6px; flex-wrap:wrap; }}
  .pill {{ display:inline-block; padding:1px 6px; border-radius:3px; font-size:10px; background:var(--bg); border:1px solid var(--line); color:var(--muted); }}
  .toolbar-row {{ display:flex; gap:6px; margin-bottom:8px; flex-wrap:wrap; }}
  .toolbar-row button {{ flex:1; padding:6px 8px; background:var(--bg); border:1px solid var(--line); color:var(--ink); border-radius:6px; cursor:pointer; font-size:11px; }}
  .toolbar-row button:hover {{ border-color:var(--accent); color:var(--accent); }}
  .toolbar-row button.on {{ border-color:var(--accent); background:#1f2533; color:var(--accent); }}
  #canvas {{ position:relative; }}
  #graph {{ position:absolute; inset:0; }}
  #legend {{ position:absolute; top:12px; left:12px; background:rgba(15,17,21,0.85); padding:8px 10px; border:1px solid var(--line); border-radius:6px; font-size:11px; color:var(--muted); max-width:280px; pointer-events:none; }}
  #legend .row {{ display:flex; align-items:center; gap:6px; margin:2px 0; }}
  #legend .swatch {{ width:10px; height:10px; border-radius:50%; }}
  #table {{ position:absolute; inset:0; overflow:auto; background:var(--bg); padding:18px; display:none; }}
  #table table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  #table th, #table td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
  #table th {{ color:var(--muted); font-weight:600; text-transform:uppercase; font-size:11px; letter-spacing:.05em; cursor:pointer; user-select:none; }}
  #table th:hover {{ color:var(--accent); }}
  .insp-section {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin-top:14px; margin-bottom:6px; }}
  .insp ul {{ margin:0; padding-left:16px; font-size:12px; }}
  .insp a {{ color:var(--accent); text-decoration:none; cursor:pointer; }}
  .insp a:hover {{ text-decoration:underline; }}
  .role-core {{ color:#a3be8c; }}
  .role-shared {{ color:#ffaa3a; }}
  .role-entry {{ color:#7cc2ff; }}
  .role-terminal {{ color:#bf616a; }}
  .role-rationale {{ color:#d68aff; }}
  .role-data {{ color:#ebcb8b; }}
</style>
</head>
<body>
<div id="app">
  <aside>
    <h1>Features</h1>
    <input id="search" placeholder="Search features…" type="search">
    <div class="toolbar-row">
      <button id="btn-all">All</button>
      <button id="btn-none">None</button>
      <button id="btn-shared">Shared</button>
    </div>
    <div class="toolbar-row">
      <button id="layout-force" class="on">Force</button>
      <button id="layout-role">By role</button>
    </div>
    <div class="toolbar-row">
      <button id="toggle-physics" class="on">Physics on</button>
      <button id="toggle-hulls" class="on">Hulls on</button>
      <button id="toggle-deps" class="on">Deps on</button>
    </div>
    <div class="toolbar-row">
      <button id="mode-map" class="on">Map</button>
      <button id="mode-table">Table</button>
    </div>
    <div id="feature-list"></div>
  </aside>
  <main id="canvas">
    <div id="graph"></div>
    <div id="table"></div>
    <div id="legend"></div>
  </main>
  <aside id="inspector" class="insp">
    <h1>Inspector</h1>
    <div id="insp-content"><em style="color:var(--muted);font-size:12px">Click a feature or node.</em></div>
  </aside>
</div>
<script>
const PAYLOAD = {payload_json};
const PALETTE = {palette_json};
{_FEATURE_VIEWER_JS}
</script>
</body>
</html>"""
    Path(output_path).write_text(html, encoding="utf-8")


_FEATURE_VIEWER_JS = r"""
const features = PAYLOAD.features || [];
const overlap = PAYLOAD.overlap_matrix || {};
const deps = PAYLOAD.feature_dependencies || [];
const nodesById = new Map();
for (const n of (PAYLOAD.nodes || [])) nodesById.set(n.id, n);

const featureColor = new Map();
for (let i = 0; i < features.length; i++) featureColor.set(features[i].id, PALETTE[i % PALETTE.length]);

const featureList = document.getElementById("feature-list");
const search = document.getElementById("search");
const inspContent = document.getElementById("insp-content");
const legendEl = document.getElementById("legend");
const graphEl = document.getElementById("graph");
const tableEl = document.getElementById("table");

const selected = new Set();
let layout = "force";
let physicsOn = true;
let hullsOn = true;
let depsOn = true;
let mode = "map";
let network = null;
let nodesDS = null;
let edgesDS = null;
let selectedFeatureId = null;

function init() {
  for (const f of features) selected.add(f.id);
  bindToolbar();
  renderFeatureList(search.value);
  rebuild();
}

function bindToolbar() {
  document.getElementById("btn-all").onclick = () => { for (const f of features) selected.add(f.id); renderFeatureList(search.value); rebuild(); };
  document.getElementById("btn-none").onclick = () => { selected.clear(); renderFeatureList(search.value); rebuild(); };
  document.getElementById("btn-shared").onclick = () => {
    selected.clear();
    for (const fids of Object.values(overlap)) {
      if (fids.length > 1) for (const id of fids) selected.add(id);
    }
    renderFeatureList(search.value); rebuild();
  };
  document.getElementById("layout-force").onclick = () => setLayout("force");
  document.getElementById("layout-role").onclick = () => setLayout("role");
  document.getElementById("toggle-physics").onclick = () => { physicsOn = !physicsOn;
    document.getElementById("toggle-physics").classList.toggle("on", physicsOn);
    document.getElementById("toggle-physics").textContent = "Physics " + (physicsOn ? "on" : "off");
    if (network) network.setOptions({ physics: physicsOn });
  };
  document.getElementById("toggle-hulls").onclick = () => { hullsOn = !hullsOn;
    document.getElementById("toggle-hulls").classList.toggle("on", hullsOn);
    document.getElementById("toggle-hulls").textContent = "Hulls " + (hullsOn ? "on" : "off");
    if (network) network.redraw();
  };
  document.getElementById("toggle-deps").onclick = () => { depsOn = !depsOn;
    document.getElementById("toggle-deps").classList.toggle("on", depsOn);
    document.getElementById("toggle-deps").textContent = "Deps " + (depsOn ? "on" : "off");
    if (network) network.redraw();
  };
  document.getElementById("mode-map").onclick = () => setMode("map");
  document.getElementById("mode-table").onclick = () => setMode("table");
  search.oninput = () => renderFeatureList(search.value);
}

function setLayout(name) {
  layout = name;
  for (const id of ["force","role"]) document.getElementById("layout-"+id).classList.toggle("on", id===name);
  rebuild();
}
function setMode(name) {
  mode = name;
  for (const id of ["map","table"]) document.getElementById("mode-"+id).classList.toggle("on", id===name);
  graphEl.style.display = legendEl.style.display = mode === "map" ? "" : "none";
  tableEl.style.display = mode === "table" ? "block" : "none";
  if (mode === "table") renderTable(); else rebuild();
}

function featureMatches(f, lower) {
  if (!lower) return true;
  const blob = (f.label || "") + " " + (f.id || "") + " " + (f.description || "");
  const labels = (f.nodes || []).map(id => (nodesById.get(id) || {}).label || "").join(" ");
  return (blob + " " + labels).toLowerCase().includes(lower);
}

function renderFeatureList(filter) {
  const lower = (filter || "").toLowerCase();
  featureList.innerHTML = "";
  for (const f of features) {
    if (!featureMatches(f, lower)) continue;
    const isOn = selected.has(f.id);
    const c = featureColor.get(f.id);
    const sharedCount = (f.nodes || []).filter(nid => (overlap[nid] || []).length > 1).length;
    const deps_out = deps.filter(d => d.source_feature_id === f.id).length;
    const div = document.createElement("div");
    div.className = "feature" + (isOn ? " active" : "");
    div.innerHTML = `
      <input type="checkbox" ${isOn ? "checked" : ""}>
      <div class="feature-color" style="background:${c}"></div>
      <div class="feature-body">
        <div class="name" title="${escape(f.label || f.id)}">${escape(f.label || f.id)}</div>
        <div class="meta">
          <span class="pill">${(f.nodes || []).length} nodes</span>
          ${sharedCount > 0 ? `<span class="pill" style="color:#ffaa3a">∩ ${sharedCount}</span>` : ""}
          ${deps_out > 0 ? `<span class="pill">→ ${deps_out}</span>` : ""}
          <span class="pill">${f.confidence || ""}</span>
        </div>
      </div>
    `;
    div.onclick = (ev) => {
      if (ev.target.tagName === "INPUT") {
        if (selected.has(f.id)) selected.delete(f.id); else selected.add(f.id);
      } else {
        selected.clear();
        selected.add(f.id);
        selectedFeatureId = f.id;
        showFeatureInspector(f);
      }
      renderFeatureList(search.value);
      rebuild();
    };
    featureList.appendChild(div);
  }
}

function rebuild() {
  if (mode !== "map") return;
  const visible = features.filter(f => selected.has(f.id));
  const nodeIds = new Set();
  for (const f of visible) for (const nid of (f.nodes || [])) nodeIds.add(nid);

  const visNodes = [];
  for (const nid of nodeIds) {
    const n = nodesById.get(nid) || { id: nid, label: nid };
    const memberships = (overlap[nid] || []).filter(fid => selected.has(fid));
    const isShared = memberships.length > 1;
    const primaryFid = memberships[0];
    const baseColor = primaryFid ? featureColor.get(primaryFid) : "#7cc2ff";
    const size = 12 + Math.min(20, memberships.length * 5);
    visNodes.push({
      id: nid,
      label: n.label || nid,
      title: `${n.label || nid}\n${n.source_file || ""}\nin ${memberships.length} feature(s)`,
      shape: "dot",
      size,
      color: { background: baseColor, border: isShared ? "#ffaa3a" : darken(baseColor, 0.4) },
      borderWidth: isShared ? 3 : 1,
      font: { color: "#e6e7eb", size: 11, strokeWidth: 3, strokeColor: "#0f1115" },
    });
  }

  // Edges: light underlay of `relation` edges among visible nodes (gives shape).
  const visEdges = [];
  const seen = new Set();
  for (const e of (PAYLOAD.edges || [])) {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    const key = `${e.source}|${e.target}|${e.relation}`;
    if (seen.has(key)) continue;
    seen.add(key);
    visEdges.push({
      from: e.source, to: e.target,
      arrows: { to: { enabled: true, scaleFactor: 0.4 } },
      color: { color: "#3a3f4a", opacity: 0.5 },
      width: 0.8, smooth: { type: "continuous" },
      title: e.relation,
    });
  }

  // Cluster anchors: invisible per-feature pseudo-node + hidden tether edges.
  // Anchors repel each other under forceAtlas2 so features that share zero
  // nodes physically separate, eliminating false hull overlap.
  if (layout === "force") {
    for (const f of visible) {
      const anchorId = `__anchor__${f.id}`;
      visNodes.push({
        id: anchorId, label: "",
        shape: "dot", size: 1,
        color: { background: "rgba(0,0,0,0)", border: "rgba(0,0,0,0)" },
        font: { color: "rgba(0,0,0,0)" },
        physics: true, mass: 5, chosen: false,
        __anchor: true,
      });
      for (const nid of (f.nodes || [])) {
        if (!nodeIds.has(nid)) continue;
        visEdges.push({
          from: anchorId, to: nid,
          color: { color: "rgba(0,0,0,0)", opacity: 0 },
          width: 0, length: 80, smooth: false,
          arrows: { to: { enabled: false } },
          __tether: true,
        });
      }
    }
  }

  nodesDS = new vis.DataSet(visNodes);
  edgesDS = new vis.DataSet(visEdges);
  if (network) { network.destroy(); network = null; }
  network = new vis.Network(graphEl, { nodes: nodesDS, edges: edgesDS }, layoutOptions(visible));
  network.on("selectNode", params => {
    if (params.nodes.length && !String(params.nodes[0]).startsWith("__anchor__")) {
      showNodeInspector(params.nodes[0]);
    }
  });
  network.on("beforeDrawing", ctx => {
    if (hullsOn) drawHulls(ctx, visible);
    if (depsOn) drawFeatureDeps(ctx, visible);
  });
  // Freeze physics once stabilized so the cluster doesn't keep rotating.
  // The user can still drag nodes; toggling Physics on re-enables forces.
  network.once("stabilizationIterationsDone", () => {
    if (network) network.setOptions({ physics: false });
    physicsOn = false;
    const btn = document.getElementById("toggle-physics");
    if (btn) { btn.classList.remove("on"); btn.textContent = "Physics off"; }
  });

  renderLegend(visible);
}

function layoutOptions(visible) {
  const base = {
    interaction: { hover: true, dragNodes: true, multiselect: true, navigationButtons: true, keyboard: true, tooltipDelay: 100 },
    physics: physicsOn,
  };
  if (layout === "role") {
    setTimeout(() => {
      if (!nodesDS) return;
      const update = [];
      const roles = ["entry", "core", "shared", "terminal", "rationale", "data"];
      for (const f of visible) {
        const fx = (visible.indexOf(f) - visible.length/2) * 700;
        for (const m of (f.members || [])) {
          const ri = Math.max(0, roles.indexOf(m.role));
          update.push({ id: m.node_id, x: fx + (Math.random()-0.5)*120, y: -300 + ri * 120, fixed: { y: true } });
        }
      }
      nodesDS.update(update);
      if (network) network.fit({ animation: true });
    }, 50);
    return Object.assign({}, base, { physics: physicsOn });
  }
  return Object.assign({}, base, {
    layout: { improvedLayout: true, randomSeed: 11 },
    // High damping kills rotational momentum that would otherwise have the
    // anchored clusters spinning indefinitely. centralGravity pulls the whole
    // graph toward the origin so it doesn't drift off-screen.
    physics: { enabled: physicsOn, solver: "forceAtlas2Based",
               forceAtlas2Based: { gravitationalConstant: -120, centralGravity: 0.02, springLength: 150, springConstant: 0.06, damping: 0.9 },
               stabilization: { iterations: 350, fit: true } },
  });
}

function drawHulls(ctx, visible) {
  if (!network || !nodesDS) return;
  for (const f of visible) {
    const pts = [];
    for (const nid of (f.nodes || [])) {
      if (!nodesDS.get(nid)) continue;
      const p = network.getPositions([nid])[nid];
      if (p) pts.push([p.x, p.y]);
    }
    if (pts.length < 2) continue;
    const hull = convexHull(pts);
    if (hull.length < 2) continue;
    // Tighter padding so hulls don't reach into another feature's territory.
    const padded = expandHull(hull, 22);
    const c = featureColor.get(f.id);
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(padded[0][0], padded[0][1]);
    for (let i = 1; i < padded.length; i++) ctx.lineTo(padded[i][0], padded[i][1]);
    ctx.closePath();
    ctx.fillStyle = hexToRgba(c, 0.14);
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = hexToRgba(c, 0.7);
    ctx.stroke();
    const cx = padded.reduce((a,p) => a + p[0], 0) / padded.length;
    const top = Math.min(...padded.map(p => p[1]));
    ctx.fillStyle = hexToRgba(c, 0.95);
    ctx.font = "bold 13px -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(f.label || f.id, cx, top - 10);
    ctx.restore();
  }
}

function drawFeatureDeps(ctx, visible) {
  if (!network || !nodesDS) return;
  const visIds = new Set(visible.map(f => f.id));
  // Compute hull centroid per visible feature
  const centroid = new Map();
  for (const f of visible) {
    const pts = [];
    for (const nid of (f.nodes || [])) {
      if (!nodesDS.get(nid)) continue;
      const p = network.getPositions([nid])[nid];
      if (p) pts.push(p);
    }
    if (!pts.length) continue;
    const cx = pts.reduce((a,p) => a + p.x, 0) / pts.length;
    const cy = pts.reduce((a,p) => a + p.y, 0) / pts.length;
    centroid.set(f.id, { x: cx, y: cy });
  }
  for (const d of deps) {
    if (!visIds.has(d.source_feature_id) || !visIds.has(d.target_feature_id)) continue;
    const a = centroid.get(d.source_feature_id), b = centroid.get(d.target_feature_id);
    if (!a || !b) continue;
    const c = featureColor.get(d.source_feature_id);
    ctx.save();
    ctx.strokeStyle = hexToRgba(c, 0.85);
    ctx.lineWidth = 1.5 + Math.min(4, d.weight);
    // Curve via control point offset perpendicular to segment
    const dx = b.x - a.x, dy = b.y - a.y;
    const mx = (a.x + b.x) / 2 + (-dy * 0.15);
    const my = (a.y + b.y) / 2 + (dx * 0.15);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.quadraticCurveTo(mx, my, b.x, b.y);
    ctx.stroke();
    // Arrowhead at b
    const ang = Math.atan2(b.y - my, b.x - mx);
    const ah = 12;
    ctx.beginPath();
    ctx.moveTo(b.x, b.y);
    ctx.lineTo(b.x - ah * Math.cos(ang - 0.4), b.y - ah * Math.sin(ang - 0.4));
    ctx.lineTo(b.x - ah * Math.cos(ang + 0.4), b.y - ah * Math.sin(ang + 0.4));
    ctx.closePath();
    ctx.fillStyle = hexToRgba(c, 0.85);
    ctx.fill();
    if (d.is_mutual) {
      ctx.font = "10px -apple-system";
      ctx.fillStyle = "#ffaa3a";
      ctx.fillText("⇄", mx, my);
    }
    ctx.restore();
  }
}

function convexHull(points) {
  const pts = points.slice().sort((a,b) => a[0]-b[0] || a[1]-b[1]);
  if (pts.length <= 1) return pts;
  const cross = (o,a,b) => (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0]);
  const lower = [];
  for (const p of pts) { while (lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) lower.pop(); lower.push(p); }
  const upper = [];
  for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) upper.pop(); upper.push(p); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}
function expandHull(hull, pad) {
  const cx = hull.reduce((a,p) => a + p[0], 0) / hull.length;
  const cy = hull.reduce((a,p) => a + p[1], 0) / hull.length;
  return hull.map(([x,y]) => {
    const dx = x - cx, dy = y - cy;
    const len = Math.hypot(dx, dy) || 1;
    return [x + (dx/len) * pad, y + (dy/len) * pad];
  });
}

function showFeatureInspector(f) {
  const dependsOn = deps.filter(d => d.source_feature_id === f.id);
  const dependedBy = deps.filter(d => d.target_feature_id === f.id);
  const byRole = {};
  for (const m of (f.members || [])) (byRole[m.role] = byRole[m.role] || []).push(m);
  let memberHtml = "";
  for (const role of ["entry","core","shared","terminal","rationale","data"]) {
    const list = byRole[role] || [];
    if (!list.length) continue;
    memberHtml += `<div class="insp-section role-${role}">${role} (${list.length})</div><ul>` +
      list.slice(0, 12).map(m => {
        const n = nodesById.get(m.node_id) || {};
        return `<li><span class="role-${role}">${escape(n.label || m.node_id)}</span> <span class="pill">w${m.weight}</span></li>`;
      }).join("") + (list.length > 12 ? `<li style="color:var(--muted)">+${list.length-12} more</li>` : "") + "</ul>";
  }
  inspContent.innerHTML = `
    <div style="font-size:15px;font-weight:600">${escape(f.label || f.id)}</div>
    <div style="font-size:11px;color:var(--muted)">${escape(f.id)}</div>
    ${f.description ? `<p style="font-size:12px;color:var(--ink);margin:8px 0">${escape(f.description)}</p>` : ""}
    <div class="insp-section">Members</div>
    ${memberHtml}
    <div class="insp-section">Flows (${(f.flows || []).length})</div>
    <ul>${(f.flows || []).map(fid => `<li>${escape(fid)}</li>`).join("") || '<li style="color:var(--muted)">none</li>'}</ul>
    <div class="insp-section">Communities</div>
    <ul>${(f.communities || []).map(c => `<li>community ${escape(String(c))}</li>`).join("") || '<li style="color:var(--muted)">none</li>'}</ul>
    <div class="insp-section">Depends on (${dependsOn.length})</div>
    <ul>${dependsOn.map(d => {
      const target = features.find(x => x.id === d.target_feature_id);
      return `<li><a data-feat="${escape(d.target_feature_id)}">${escape(target ? (target.label || d.target_feature_id) : d.target_feature_id)}</a> <span class="pill">w${d.weight}</span>${d.is_mutual ? ' <span class="pill" style="color:#ffaa3a">mutual</span>' : ""}</li>`;
    }).join("") || '<li style="color:var(--muted)">none</li>'}</ul>
    <div class="insp-section">Depended on by (${dependedBy.length})</div>
    <ul>${dependedBy.map(d => {
      const src = features.find(x => x.id === d.source_feature_id);
      return `<li><a data-feat="${escape(d.source_feature_id)}">${escape(src ? (src.label || d.source_feature_id) : d.source_feature_id)}</a> <span class="pill">w${d.weight}</span></li>`;
    }).join("") || '<li style="color:var(--muted)">none</li>'}</ul>
  `;
  for (const a of inspContent.querySelectorAll("a[data-feat]")) {
    a.onclick = (e) => { e.preventDefault(); const fid = a.dataset.feat; const t = features.find(x => x.id === fid); if (t) { selected.clear(); selected.add(fid); selectedFeatureId = fid; showFeatureInspector(t); renderFeatureList(search.value); rebuild(); } };
  }
}

function showNodeInspector(nid) {
  const n = nodesById.get(nid) || { id: nid, label: nid };
  const memberships = overlap[nid] || [];
  const items = memberships.map(fid => {
    const f = features.find(x => x.id === fid);
    if (!f) return "";
    const c = featureColor.get(fid);
    const role = (f.members || []).find(m => m.node_id === nid)?.role || "?";
    return `<li><span style="display:inline-block;width:8px;height:8px;background:${c};border-radius:2px;margin-right:6px"></span>` +
           `<a data-feat="${escape(fid)}">${escape(f.label || fid)}</a> <span class="pill role-${role}">${role}</span></li>`;
  }).join("");
  inspContent.innerHTML = `
    <div style="font-size:14px;font-weight:600">${escape(n.label || nid)}</div>
    <div style="font-size:11px;color:var(--muted);word-break:break-all">${escape(n.source_file || "")}</div>
    <div class="insp-section">In ${memberships.length} feature${memberships.length === 1 ? "" : "s"}</div>
    <ul>${items || '<li style="color:var(--muted)">no feature membership</li>'}</ul>
  `;
  for (const a of inspContent.querySelectorAll("a[data-feat]")) {
    a.onclick = (e) => { e.preventDefault(); const fid = a.dataset.feat; const t = features.find(x => x.id === fid); if (t) { selected.clear(); selected.add(fid); selectedFeatureId = fid; showFeatureInspector(t); renderFeatureList(search.value); rebuild(); } };
  }
}

function renderLegend(visible) {
  if (!visible.length) { legendEl.innerHTML = '<em style="color:var(--muted)">No features selected.</em>'; return; }
  const sharedCount = Object.values(overlap).filter(fs => fs.filter(f => selected.has(f)).length > 1).length;
  const visibleDeps = deps.filter(d => selected.has(d.source_feature_id) && selected.has(d.target_feature_id)).length;
  let html = `<div style="margin-bottom:6px"><b>${visible.length}</b> feature${visible.length===1?"":"s"} · <b>${sharedCount}</b> shared · <b>${visibleDeps}</b> deps</div>`;
  for (const f of visible.slice(0, 10)) {
    const c = featureColor.get(f.id);
    html += `<div class="row"><span class="swatch" style="background:${c}"></span><span>${escape(f.label || f.id)}</span></div>`;
  }
  if (visible.length > 10) html += `<div class="row"><span style="color:var(--muted)">+${visible.length - 10} more</span></div>`;
  legendEl.innerHTML = html;
}

function renderTable() {
  let rows = features.map(f => {
    const sharedCount = (f.nodes || []).filter(nid => (overlap[nid] || []).length > 1).length;
    const out = deps.filter(d => d.source_feature_id === f.id).length;
    const inn = deps.filter(d => d.target_feature_id === f.id).length;
    return { f, name: f.label || f.id, nodes: (f.nodes||[]).length, shared: sharedCount, flows: (f.flows||[]).length, communities: (f.communities||[]).length, depsOut: out, depsIn: inn, conf: f.confidence || "" };
  });
  let html = `<table><thead><tr>
    <th data-k="name">Feature</th>
    <th data-k="nodes">Nodes</th>
    <th data-k="shared">Shared ∩</th>
    <th data-k="flows">Flows</th>
    <th data-k="communities">Communities</th>
    <th data-k="depsOut">→</th>
    <th data-k="depsIn">←</th>
    <th data-k="conf">Confidence</th>
    </tr></thead><tbody>`;
  for (const r of rows) {
    const c = featureColor.get(r.f.id);
    html += `<tr>
      <td><span style="display:inline-block;width:8px;height:8px;background:${c};margin-right:6px"></span><a data-feat="${escape(r.f.id)}">${escape(r.name)}</a></td>
      <td>${r.nodes}</td><td>${r.shared}</td><td>${r.flows}</td><td>${r.communities}</td>
      <td>${r.depsOut}</td><td>${r.depsIn}</td><td>${r.conf}</td>
    </tr>`;
  }
  html += "</tbody></table>";
  tableEl.innerHTML = html;
  for (const a of tableEl.querySelectorAll("a[data-feat]")) {
    a.onclick = (e) => { e.preventDefault(); const f = features.find(x => x.id === a.dataset.feat); if (f) { selected.clear(); selected.add(f.id); selectedFeatureId = f.id; showFeatureInspector(f); setMode("map"); } };
  }
  for (const th of tableEl.querySelectorAll("th[data-k]")) {
    th.onclick = () => {
      const k = th.dataset.k;
      const desc = th.dataset.dir !== "desc";
      th.dataset.dir = desc ? "desc" : "asc";
      rows.sort((a,b) => (a[k] < b[k] ? -1 : a[k] > b[k] ? 1 : 0) * (desc ? -1 : 1));
      const tbody = tableEl.querySelector("tbody");
      tbody.innerHTML = rows.map(r => {
        const c = featureColor.get(r.f.id);
        return `<tr><td><span style="display:inline-block;width:8px;height:8px;background:${c};margin-right:6px"></span><a data-feat="${escape(r.f.id)}">${escape(r.name)}</a></td><td>${r.nodes}</td><td>${r.shared}</td><td>${r.flows}</td><td>${r.communities}</td><td>${r.depsOut}</td><td>${r.depsIn}</td><td>${r.conf}</td></tr>`;
      }).join("");
      for (const a of tbody.querySelectorAll("a[data-feat]")) {
        a.onclick = (e) => { e.preventDefault(); const f = features.find(x => x.id === a.dataset.feat); if (f) { selected.clear(); selected.add(f.id); showFeatureInspector(f); setMode("map"); } };
      }
    };
  }
}

function hexToRgba(hex, a) {
  const h = hex.replace("#","");
  const n = parseInt(h.length === 3 ? h.split("").map(c => c+c).join("") : h, 16);
  return `rgba(${(n>>16)&255}, ${(n>>8)&255}, ${n&255}, ${a})`;
}
function darken(hex, amt) {
  const [r,g,b] = hexToRgba(hex,1).match(/\d+/g).map(Number);
  return `rgb(${Math.max(0,r*(1-amt))|0}, ${Math.max(0,g*(1-amt))|0}, ${Math.max(0,b*(1-amt))|0})`;
}
function escape(s) { return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

init();
"""
