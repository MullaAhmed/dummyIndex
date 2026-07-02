"""Apply-time seeding of starter eval suites (``equip apply`` → ``equipment-evals/``).

Additive, never-clobber wiring for the eval stage: after ``equip apply`` writes
the toolkit, it drops a schema-valid starter ``<tool>.suite.json`` for each
generated tool that has none, so the user has a correct file to hand-author
against. Split out of ``dispatch.py`` (a CLI dispatcher stays lean, per
``conventions/folder-organization.md``) and kept out of the pure
``generate/catalog`` domain (the boundary writes files; the catalog decides
specs). Seeding is DEFENSIVE by contract: it can never break ``equip apply`` —
an unsafe tool name is skipped and any write error is swallowed.
"""

from __future__ import annotations

import json
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.equip import (
    EVALS_REL,
    EquipmentItem,
    is_lifecycle_managed,
)
from dummyindex.context.domains.equip.eval import EvalCase, suite_to_dict

from .common import safe_tool_name


def starter_suite_cases(name: str, capabilities: tuple[str, ...]) -> tuple[EvalCase, ...]:
    """Derive placeholder eval cases for a generated tool's starter suite.

    Up to the first two capabilities each yield one positive case; a single fixed
    negative decoy is always appended. When ``capabilities`` is empty a generic
    positive stands in. The prompts are intentional PLACEHOLDERS — the user hand-
    authors real, synthetic prompts (never secret-bearing); the value here is a
    schema-correct starting file, never a graded suite.
    """
    cases: list[EvalCase] = []
    for cap in capabilities[:2]:
        cases.append(
            EvalCase(
                case_id=f"{cap}-positive",
                prompt=(
                    f"<replace: a synthetic prompt that SHOULD trigger the {name} "
                    f"tool for its {cap!r} capability>"
                ),
                expects_trigger=True,
            )
        )
    if not cases:
        cases.append(
            EvalCase(
                case_id="positive",
                prompt=(
                    f"<replace: a synthetic prompt that SHOULD trigger the {name} tool>"
                ),
                expects_trigger=True,
            )
        )
    cases.append(
        EvalCase(
            case_id="decoy-negative",
            prompt="<replace: an unrelated prompt that should NOT trigger this tool>",
            expects_trigger=False,
        )
    )
    return tuple(cases)


def seed_starter_suites(context_dir: Path, items: tuple[EquipmentItem, ...]) -> None:
    """Seed a starter ``<tool>.suite.json`` per generated tool (never-clobber).

    For every lifecycle-managed item, write a schema-valid starter suite under
    ``.context/equipment-evals/`` — but ONLY when no suite already exists, so a
    hand-edited suite is never stomped. Two defenses keep this from ever breaking
    ``equip apply``: the manifest ``name`` is run through :func:`safe_tool_name`
    before it becomes a path segment (a crafted ``../`` name is skipped, never
    written outside the evals dir), and every write is wrapped so a failure on one
    tool can never propagate out of an apply that has already written its manifest.
    """
    evals_dir = context_dir / EVALS_REL
    for item in items:
        if not is_lifecycle_managed(item):
            continue
        # Sanitize before the name becomes a path segment (matches the eval CLI's
        # contract) — an unsafe manifest name is skipped, never written.
        try:
            safe_name = safe_tool_name(item.name)
        except ValueError:
            continue
        suite_path = evals_dir / f"{safe_name}.suite.json"
        if suite_path.exists():
            continue  # never-clobber a hand-authored suite
        try:
            write_text_atomic(
                suite_path,
                json.dumps(
                    suite_to_dict(starter_suite_cases(item.name, item.capabilities)),
                    indent=2,
                )
                + "\n",
            )
        except Exception:  # noqa: BLE001 — seeding must NEVER break apply (by contract)
            continue
