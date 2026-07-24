"""Stylesheet for the `features/graph.html` scan viewer.

Inlined into the document — the viewer has to open over `file://` with no
server and no network, so there is nothing to link to.

Two ideas carry the whole design:

- **Kind is the only colour.** Eight node kinds, eight hues, nothing else
  on the page is saturated. Colour therefore *means* something instead of
  decorating, and a map stays readable at a glance.
- **Colour is never the only signal.** `external` is dashed, every kind
  carries its own glyph, and selection changes weight and opacity as well
  as hue — so the map survives being printed, projected, or read by
  someone who doesn't distinguish sky from blue.

Both themes are first-class: `prefers-color-scheme` picks the default and
the header toggle overrides it via `data-theme` on the root.
"""

from __future__ import annotations

VIEWER_CSS = r"""
*, *::before, *::after { box-sizing: border-box; }

:root {
  color-scheme: dark;
  --bg:        #0b0d11;
  --bg-panel:  #111419;
  --bg-node:   #161a21;
  --bg-hover:  #1c212a;
  --bg-inset:  #0e1116;
  --fg:        #e8ecf2;
  --fg-muted:  #8b95a5;
  --fg-faint:  #5b6472;
  --border:    #232936;
  --border-strong: #333c4d;
  --edge:      #39414f;
  --edge-hot:  #cfd8e6;
  --shadow:    0 1px 2px rgba(0,0,0,.5), 0 8px 24px rgba(0,0,0,.32);
  --shadow-sel: 0 0 0 1px var(--accent), 0 6px 28px rgba(0,0,0,.5);

  --k-entry:    #38bdf8;
  --k-cron:     #fbbf24;
  --k-agent:    #a78bfa;
  --k-model:    #f472b6;
  --k-tool:     #34d399;
  --k-service:  #8296b3;
  --k-store:    #fb923c;
  --k-external: #94a3b8;
}

:root[data-theme="light"], html:not([data-theme="dark"]) {
  /* placeholder — real light values live in the two blocks below */
}

@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    color-scheme: light;
    --bg:        #f6f7f9;
    --bg-panel:  #ffffff;
    --bg-node:   #ffffff;
    --bg-hover:  #f2f4f7;
    --bg-inset:  #f0f2f5;
    --fg:        #10141b;
    --fg-muted:  #5c6673;
    --fg-faint:  #8b95a3;
    --border:    #e0e4ea;
    --border-strong: #c4ccd6;
    --edge:      #c3cbd6;
    --edge-hot:  #2b3444;
    --shadow:    0 1px 2px rgba(16,20,27,.06), 0 6px 20px rgba(16,20,27,.07);
    --shadow-sel: 0 0 0 1px var(--accent), 0 8px 26px rgba(16,20,27,.14);

    --k-entry:    #0284c7;
    --k-cron:     #b45309;
    --k-agent:    #7c3aed;
    --k-model:    #be1e63;
    --k-tool:     #047857;
    --k-service:  #4a5c78;
    --k-store:    #c2410c;
    --k-external: #566371;
  }
}

:root[data-theme="light"] {
  color-scheme: light;
  --bg:        #f6f7f9;
  --bg-panel:  #ffffff;
  --bg-node:   #ffffff;
  --bg-hover:  #f2f4f7;
  --bg-inset:  #f0f2f5;
  --fg:        #10141b;
  --fg-muted:  #5c6673;
  --fg-faint:  #8b95a3;
  --border:    #e0e4ea;
  --border-strong: #c4ccd6;
  --edge:      #c3cbd6;
  --edge-hot:  #2b3444;
  --shadow:    0 1px 2px rgba(16,20,27,.06), 0 6px 20px rgba(16,20,27,.07);
  --shadow-sel: 0 0 0 1px var(--accent), 0 8px 26px rgba(16,20,27,.14);

  --k-entry:    #0284c7;
  --k-cron:     #b45309;
  --k-agent:    #7c3aed;
  --k-model:    #be1e63;
  --k-tool:     #047857;
  --k-service:  #4a5c78;
  --k-store:    #c2410c;
  --k-external: #566371;
}

html, body { height: 100%; margin: 0; }

body {
  background: var(--bg);
  color: var(--fg);
  font: 14px/1.5 ui-sans-serif, -apple-system, "Segoe UI", Inter, Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

code, .mono { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace; }

/* ----- header ------------------------------------------------------------ */

header {
  flex: none;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-wrap: wrap;
}

.brand { display: flex; flex-direction: column; gap: 1px; margin-right: 4px; }
.brand h1 { margin: 0; font-size: 14px; font-weight: 650; letter-spacing: -0.01em; }
.brand .tagline { font-size: 11.5px; color: var(--fg-muted); }

.stats { display: flex; gap: 6px; flex-wrap: wrap; }

.stat {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 3px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-inset);
  font-size: 11.5px;
  color: var(--fg-muted);
  white-space: nowrap;
}
.stat b { color: var(--fg); font-weight: 620; font-size: 12px; }

.spacer { flex: 1 1 auto; }

.tools { display: flex; align-items: center; gap: 8px; }

input[type="search"] {
  width: 210px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
}
input[type="search"]:focus {
  outline: none;
  border-color: var(--border-strong);
  box-shadow: 0 0 0 3px rgba(130,150,179,.14);
}
input[type="search"]::placeholder { color: var(--fg-faint); }

button {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--fg-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
button:hover { background: var(--bg-hover); color: var(--fg); }
button:focus-visible { outline: 2px solid var(--k-entry); outline-offset: 1px; }

/* ----- chip rows (topModels / topTools / topIntegrations) ----------------- */

.chiprows {
  flex: none;
  display: flex;
  gap: 18px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-wrap: wrap;
  font-size: 12px;
}
.chiprow { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.chiprow > .label {
  color: var(--fg-faint);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 600;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px 3px 4px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-inset);
}
.chip .mono-dot {
  width: 17px; height: 17px;
  border-radius: 5px;
  display: grid; place-items: center;
  font-size: 9.5px; font-weight: 700;
  background: var(--bg-hover);
  color: var(--fg-muted);
}
.chip .host { color: var(--fg-faint); font-size: 10.5px; }

/* ----- stage ------------------------------------------------------------- */

main { flex: 1 1 auto; display: flex; min-height: 0; }

#stage {
  position: relative;
  flex: 1 1 auto;
  overflow: hidden;
  cursor: grab;
  background-image: radial-gradient(circle at 1px 1px, var(--border) 1px, transparent 0);
  background-size: 26px 26px;
}
#stage.panning { cursor: grabbing; }
#stage.traced .node:not(.hot) { opacity: .22; }
#stage.traced .grouplabel { opacity: .3; }

#canvas { position: absolute; top: 0; left: 0; transform-origin: 0 0; will-change: transform; }
#wires { position: absolute; top: 0; left: 0; overflow: visible; pointer-events: none; }

/* ----- edges ------------------------------------------------------------- */

.wire { fill: none; stroke: var(--edge); stroke-width: 1.4px; }
.wire.hot { stroke: var(--edge-hot); stroke-width: 2px; }
.wire.dim { opacity: .16; }

.wirelabel {
  font-size: 10px;
  fill: var(--fg-muted);
  paint-order: stroke;
  stroke: var(--bg);
  stroke-width: 4px;
  stroke-linejoin: round;
  text-anchor: middle;
}
.wirelabel.verb { fill: var(--fg-faint); opacity: 0; transition: opacity .12s; }
#stage.traced .wirelabel.verb.hot { opacity: 1; }
.wirelabel.dim { opacity: .16; }

/* ----- nodes ------------------------------------------------------------- */

.grouplabel {
  position: absolute;
  font-size: 10px;
  font-weight: 650;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--fg-faint);
  white-space: nowrap;
  pointer-events: none;
}

.node {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--kind);
  border-radius: 9px;
  background: var(--bg-node);
  box-shadow: var(--shadow);
  cursor: pointer;
  transition: opacity .12s, transform .12s, box-shadow .12s;
  --accent: var(--kind);
}
.node:hover { background: var(--bg-hover); transform: translateY(-1px); }
.node.selected { box-shadow: var(--shadow-sel); background: var(--bg-hover); }
.node.k-external { border-style: dashed; border-left-style: solid; }

.node.searchhide { opacity: .1; pointer-events: none; }
.node .glyph { flex: none; color: var(--kind); display: grid; place-items: center; }
.node .glyph svg { display: block; }

.node .text { min-width: 0; flex: 1 1 auto; display: flex; flex-direction: column; gap: 1px; }
.node .label {
  font-size: 12.5px;
  font-weight: 580;
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.node .sub {
  font-size: 10.5px;
  color: var(--fg-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* ----- detail panel ------------------------------------------------------ */

aside {
  flex: none;
  width: 320px;
  border-left: 1px solid var(--border);
  background: var(--bg-panel);
  overflow-y: auto;
  padding: 16px;
}
aside .empty { color: var(--fg-faint); font-size: 12.5px; line-height: 1.65; }
aside h2 {
  margin: 0 0 2px;
  font-size: 15px;
  font-weight: 640;
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}
aside .kindtag {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 10px; font-weight: 660; text-transform: uppercase; letter-spacing: .07em;
  color: var(--kind);
  margin-bottom: 12px;
}
aside .detail-text { font-size: 12.5px; line-height: 1.6; color: var(--fg); margin: 0 0 14px; }
aside .ref {
  display: block;
  font-size: 11.5px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-inset);
  color: var(--fg-muted);
  overflow-wrap: anywhere;
  margin-bottom: 14px;
  user-select: all;
}
aside h3 {
  margin: 0 0 6px;
  font-size: 10px; font-weight: 650; letter-spacing: .07em; text-transform: uppercase;
  color: var(--fg-faint);
}
aside ul { list-style: none; margin: 0 0 14px; padding: 0; display: grid; gap: 3px; }
aside li button {
  width: 100%;
  text-align: left;
  display: flex;
  align-items: baseline;
  gap: 7px;
  padding: 5px 8px;
  font-size: 12px;
  color: var(--fg);
  background: transparent;
  border-color: transparent;
}
aside li button:hover { background: var(--bg-hover); border-color: var(--border); }
aside li .verb {
  flex: none;
  font-size: 9.5px; text-transform: uppercase; letter-spacing: .06em;
  color: var(--fg-faint);
  min-width: 46px;
}
aside li .edgenote { color: var(--fg-muted); font-size: 11px; }

/* ----- legend + banner --------------------------------------------------- */

.legend {
  position: absolute;
  left: 14px; bottom: 14px;
  display: flex; gap: 4px; flex-wrap: wrap;
  max-width: calc(100% - 28px);
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: color-mix(in srgb, var(--bg-panel) 88%, transparent);
  backdrop-filter: blur(8px);
}
.legend .item {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 7px 2px 5px;
  border-radius: 6px;
  font-size: 10.5px;
  color: var(--fg-muted);
  cursor: pointer;
  user-select: none;
  --accent: var(--kind);
}
.legend .item:hover { background: var(--bg-hover); color: var(--fg); }
.legend .item.off { opacity: .34; }
.legend .item .dot { width: 8px; height: 8px; border-radius: 3px; background: var(--kind); }

.banner {
  position: absolute;
  left: 50%; top: 14px;
  transform: translateX(-50%);
  max-width: min(560px, calc(100% - 28px));
  padding: 9px 13px;
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  background: color-mix(in srgb, var(--bg-panel) 92%, transparent);
  backdrop-filter: blur(8px);
  box-shadow: var(--shadow);
  font-size: 12px;
  color: var(--fg-muted);
  line-height: 1.55;
}
.banner b { color: var(--fg); font-weight: 620; }
.banner code {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--bg-inset);
  color: var(--fg);
}

/* ----- evidence (solid = EXTRACTED, dashed = INFERRED) -------------------- */

/* The class is only ever minted from the closed alphabet in `tiers.py`
   (`safeEvidence`); a scan without the field renders exactly as before. */
.node.ev-inferred { border-style: dashed; border-left-style: solid; }

/* ----- tier 2: community overview ----------------------------------------- */

#comm-wires {
  position: absolute;
  top: 0; left: 0;
  overflow: visible;
  pointer-events: none;
  display: none;
}
.node.commnode { display: none; }
#stage.mode-communities .node:not(.commnode) { display: none; }
#stage.mode-communities .grouplabel { display: none; }
#stage.mode-communities #wires { display: none; }
#stage.mode-communities .node.commnode { display: flex; }
#stage.mode-communities #comm-wires { display: block; }

aside li.member {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  font-size: 12px;
}
aside li.member .ref {
  display: inline;
  margin: 0;
  padding: 1px 6px;
  font-size: 10.5px;
}

/* ----- tier 3: focus + expand --------------------------------------------- */

.ghost {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 9px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-node) 92%, transparent);
  box-shadow: var(--shadow);
  font-size: 10.5px;
  z-index: 3;
  pointer-events: none;
}
.ghost .rel {
  flex: none;
  color: var(--fg-faint);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: .05em;
}
.ghost .gtext { min-width: 0; display: flex; flex-direction: column; }
.ghost .glabel {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ghost .gpath {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--fg-muted);
  font-size: 9.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ghostwire { stroke-dasharray: 4 3; }

.hidden { display: none !important; }

@media (max-width: 860px) {
  aside { position: absolute; right: 0; top: 0; bottom: 0; z-index: 5; box-shadow: var(--shadow); }
  aside.empty-state { display: none; }
  input[type="search"] { width: 130px; }
}
"""
