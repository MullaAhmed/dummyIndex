"""Per-language extractor implementations.

Each `extract_<lang>` returns ``{"nodes": [...], "edges": [...], …}``.
The dispatch table in `dummyindex.pipeline.extract.__init__` routes a
file's suffix to the right one.
"""

from __future__ import annotations

from .blade import extract_blade
from .dart import extract_dart
from .elixir import extract_elixir
from .go import extract_go
from .julia import extract_julia
from .powershell import extract_powershell
from .rust import extract_rust
from .verilog import extract_verilog
from .wrappers import (
    extract_c,
    extract_cpp,
    extract_csharp,
    extract_java,
    extract_js,
    extract_kotlin,
    extract_lua,
    extract_php,
    extract_python,
    extract_ruby,
    extract_scala,
    extract_swift,
)
from .zig import extract_zig

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
