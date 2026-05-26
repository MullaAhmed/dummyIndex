"""Graph export — write a networkx graph to JSON.

Public surface (kept stable for the lazy `__getattr__` map in
``dummyindex/__init__.py`` and for ``context/build/graph.py``):

- ``to_json(G, communities, output_path)``
"""
from __future__ import annotations

from .graph import to_json

__all__ = ["to_json"]
