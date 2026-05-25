"""Graph export — write a networkx graph to JSON or interactive HTML.

Public surface (kept stable for the lazy `__getattr__` map in
``dummyindex/__init__.py`` and for ``context/graph.py``):

- ``to_json(G, communities, output_path)``
- ``to_html(G, communities, output_path, community_labels=None, member_counts=None)``

Constants ``COMMUNITY_COLORS`` and ``MAX_NODES_FOR_VIZ`` are re-exported
for callers that style alongside the same palette.
"""
from __future__ import annotations

from ._common import COMMUNITY_COLORS, MAX_NODES_FOR_VIZ
from .graph import to_html, to_json

__all__ = ["COMMUNITY_COLORS", "MAX_NODES_FOR_VIZ", "to_html", "to_json"]
