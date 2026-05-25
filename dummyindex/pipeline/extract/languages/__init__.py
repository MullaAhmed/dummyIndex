"""Per-language extractor implementations.

Each `extract_<lang>` returns ``{"nodes": [...], "edges": [...], …}``.
The dispatch table in `dummyindex.pipeline.extract.__init__` routes a
file's suffix to the right one.
"""
from __future__ import annotations

from ._wrappers import (
    extract_python,
    extract_js,
    extract_java,
    extract_c,
    extract_cpp,
    extract_ruby,
    extract_csharp,
    extract_kotlin,
    extract_scala,
    extract_php,
    extract_lua,
    extract_swift,
)
from .blade import extract_blade
from .dart import extract_dart
from .verilog import extract_verilog
from .julia import extract_julia
from .go import extract_go
from .rust import extract_rust
from .zig import extract_zig
from .powershell import extract_powershell
from .objc import extract_objc
from .elixir import extract_elixir

__all__ = [
    "extract_blade",
    "extract_c",
    "extract_cpp",
    "extract_csharp",
    "extract_dart",
    "extract_elixir",
    "extract_go",
    "extract_java",
    "extract_js",
    "extract_julia",
    "extract_kotlin",
    "extract_lua",
    "extract_objc",
    "extract_php",
    "extract_powershell",
    "extract_python",
    "extract_ruby",
    "extract_rust",
    "extract_scala",
    "extract_swift",
    "extract_verilog",
    "extract_zig",
]
