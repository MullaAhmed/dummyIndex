"""The HTML viewer that ships as `.context/features/graph.html`.

`render_viewer_html` inlines the data, so the file is self-contained: no server, CDN
or network, and opening a scan never tells a third party what a private codebase is
built from. The rendered ``VIEWER_HTML`` is byte-identical across projects but for
islands `scan-data` (tier 1) and `graph-extras` (tiers 2+3, from `extras.py`): the
only scan-derived text Python writes rather than `esc()`, so both go through `_embed`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .extras import load_viewer_extras
from .script import VIEWER_JS
from .styles import VIEWER_CSS
from .tiers import VIEWER_TIERS_JS

# Replaced by `render_viewer_html`. Valid JSON so an unrendered template still
# loads: the viewer reports "no scan data" and keeps tiers 2+3 dormant.
_SCAN_PLACEHOLDER = '{"schema_version": 0, "graph": {"nodes": [], "edges": []}}'
_EXTRAS_PLACEHOLDER = '{"communities": [], "communityLinks": [], "expansion": {}}'

VIEWER_HTML = (
    (
        """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>codebase scan</title>
<style>"""
        + VIEWER_CSS
        + """</style>
</head>
<body>
<header>
  <div class="brand">
    <h1 id="project-name">codebase scan</h1>
    <span class="tagline" id="project-tagline"></span>
  </div>
  <div class="stats" id="stats"></div>
  <span class="spacer"></span>
  <div class="tools">
    <input type="search" id="search" placeholder="filter nodes…" aria-label="Filter nodes" />
    <button id="fit" title="Fit to screen (F)">Fit</button>
    <button id="tiers" class="hidden" title="Toggle community overview (C)">Communities</button>
    <button id="theme" title="Toggle light / dark">Theme</button>
  </div>
</header>
<div class="chiprows" id="chiprows"></div>
<main>
  <div id="stage">
    <div id="canvas">
      <svg id="wires" xmlns="http://www.w3.org/2000/svg"></svg>
    </div>
    <div class="legend" id="legend"></div>
    <div class="banner hidden" id="banner"></div>
  </div>
  <aside id="detail" class="empty-state"></aside>
</main>
<script type="application/json" id="scan-data">__DUMMYINDEX_SCAN_JSON__</script>
<script type="application/json" id="graph-extras">__DUMMYINDEX_EXTRAS_JSON__</script>
<script>"""
        + VIEWER_JS
        + VIEWER_TIERS_JS
        + """</script>
</body>
</html>
"""
    )
    .replace("__DUMMYINDEX_SCAN_JSON__", _SCAN_PLACEHOLDER)
    .replace("__DUMMYINDEX_EXTRAS_JSON__", _EXTRAS_PLACEHOLDER)
)


def render_viewer_html(
    scan: dict[str, Any], *, features_dir: Path | None = None
) -> str:
    """Return the viewer with ``scan`` inlined as its data island.

    With ``features_dir``, the tier-2/tier-3 extras are derived from the
    on-disk artifacts (`graph-communities.json`, `symbol-graph.json`,
    `seed-rank.json`) and inlined as the second island; without it — or
    when the artifacts are absent — the empty placeholder stays and the
    viewer degrades to the plain curated map.
    """
    html = VIEWER_HTML.replace(_SCAN_PLACEHOLDER, _embed(scan), 1)
    if features_dir is not None:
        extras = load_viewer_extras(scan, features_dir)
        if not extras.is_empty():
            html = html.replace(_EXTRAS_PLACEHOLDER, _embed(extras.to_dict()), 1)
    return html


def _embed(scan: dict[str, Any]) -> str:
    """Serialize ``scan`` so it can sit safely inside a `<script>` element.

    An HTML parser ends a `<script>` at the first literal `</` and treats `<!--`
    as a comment start, so a `sourceRef` or `detail` containing either would
    truncate the document. JSON escapes (`<\\/`, `<\\u0021--`) keep the parsed
    payload identical while making it inert to the HTML tokenizer.
    """
    return (
        json.dumps(scan, indent=2, sort_keys=True, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("<!--", "<\\u0021--")
    )


__all__ = ["VIEWER_HTML", "render_viewer_html"]
