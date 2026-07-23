"""The HTML viewer that ships as `.context/features/graph.html`.

`render_viewer_html(scan)` inlines the scan payload into the document, so
the emitted file is genuinely self-contained: double-click it and the map
is there. No local server, no CDN, no network at all — which also means
opening a scan never tells a third party what a private codebase is built
from.

``VIEWER_HTML`` is the un-substituted template. It is a module constant
rather than a rendered string so the document is byte-identical across
every project dummyindex indexes; the *only* thing that differs between
two `graph.html` files is the JSON blob.

Split across three modules because a single-file viewer is still three
languages: `styles.VIEWER_CSS`, `script.VIEWER_JS`, and the markup here.
"""

from __future__ import annotations

import json
from typing import Any

from .script import VIEWER_JS
from .styles import VIEWER_CSS

# Replaced by `render_viewer_html`. A template that has never been rendered
# still has to parse as valid JSON, so the placeholder is a valid object —
# the viewer then reports "no scan data" instead of throwing on load.
_SCAN_PLACEHOLDER = '{"schema_version": 0, "graph": {"nodes": [], "edges": []}}'

VIEWER_HTML = (
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
<script>"""
    + VIEWER_JS
    + """</script>
</body>
</html>
"""
).replace("__DUMMYINDEX_SCAN_JSON__", _SCAN_PLACEHOLDER)


def render_viewer_html(scan: dict[str, Any]) -> str:
    """Return the viewer with ``scan`` inlined as its data island."""
    return VIEWER_HTML.replace(_SCAN_PLACEHOLDER, _embed(scan), 1)


def _embed(scan: dict[str, Any]) -> str:
    """Serialize ``scan`` so it can sit safely inside a `<script>` element.

    An HTML parser ends a `<script>` at the first literal `</` regardless of
    what the surrounding language thinks, and it treats `<!--` as the start
    of a comment. A `sourceRef` or `detail` containing either would truncate
    the document. JSON's `\\/` escape means `/`, so rewriting the sequence
    keeps the payload identical once parsed while making it inert to the
    HTML tokenizer.
    """
    return (
        json.dumps(scan, indent=2, sort_keys=True, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("<!--", "<\\u0021--")
    )


__all__ = ["VIEWER_HTML", "render_viewer_html"]
