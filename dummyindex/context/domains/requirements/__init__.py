"""Required-setup manifest (``.context/config.toml``): model, TOML I/O and seeding.

Public surface:

- ``Requirements``, ``PluginRequirement``, ``SkillRequirement``, ``RequirementRow``
- ``RequirementStatus``, ``RequirementKind``, ``SkillOrigin``
- ``read_requirements``, ``render_requirements``, ``write_requirements``,
  ``set_min_version_line``, ``parse_skill_from``, ``is_valid_constraint``
- ``seed_requirements`` (pure seeding from the wired set)
- ``check_requirements`` / ``exit_code`` and the gate: ``gate_decision``,
  ``read_bypass``, ``write_bypass``, ``write_ok_marker``, ``run_gate``.
- ``RequirementsError`` and the layout constants.
"""

from __future__ import annotations

from .check import check_requirements, exit_code
from .constants import (
    BYPASS_ENV,
    BYPASS_REL,
    CONFIG_TOML_REL,
    OK_MARKER_REL,
    SCHEMA_VERSION,
)
from .enums import RequirementKind, RequirementStatus, SkillOrigin
from .errors import RequirementsError
from .gate import (
    GateDecision,
    gate_decision,
    read_bypass,
    run_gate,
    write_bypass,
    write_ok_marker,
)
from .models import PluginRequirement, RequirementRow, Requirements, SkillRequirement
from .seed import seed_requirements
from .toml_io import (
    is_valid_constraint,
    parse_skill_from,
    read_requirements,
    render_requirements,
    set_min_version_line,
    write_requirements,
)

__all__ = [
    "GateDecision",
    "check_requirements",
    "exit_code",
    "gate_decision",
    "read_bypass",
    "run_gate",
    "write_bypass",
    "write_ok_marker",
    "BYPASS_ENV",
    "BYPASS_REL",
    "CONFIG_TOML_REL",
    "OK_MARKER_REL",
    "SCHEMA_VERSION",
    "PluginRequirement",
    "Requirements",
    "RequirementKind",
    "RequirementRow",
    "RequirementStatus",
    "RequirementsError",
    "SkillOrigin",
    "SkillRequirement",
    "is_valid_constraint",
    "parse_skill_from",
    "read_requirements",
    "render_requirements",
    "seed_requirements",
    "set_min_version_line",
    "write_requirements",
]
