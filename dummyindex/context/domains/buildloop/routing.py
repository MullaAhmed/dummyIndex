"""Model routing for a proposal build — resolution + validation.

Routing is **proposal data, not config**: ``proposal.json`` may carry an
optional ``"routing"`` object — ``{"implementer": "<model>", "auditor":
"<model>", "decisions": "<model>"}`` — written by
``dummyindex context propose --route k=v`` (via the proposals store).
``dummyindex context build --route k=v`` overrides at run time.
Precedence: **invocation > proposal > unset** (an empty dict).

Values are model *family aliases* validated against the existing
:class:`~dummyindex.context.domains.config.ModelChoice` alphabet
(``current`` | ``opus`` | ``sonnet`` | ``haiku`` | ``fable``) — reuse, no
new enum. The key set is closed (:data:`ROUTING_KEYS`); unknown keys are
rejected. A hand-edited ``proposal.json`` with an unresolvable alias fails
loudly at build start (:class:`BuildLoopError`) rather than misrouting a
wave mid-build.

Wire-free per domain discipline: :func:`parse_route_flags` turns CLI
``k=v`` tokens into a validated map; :func:`resolve_routing` reads the
proposal artifact and merges override over proposal. No printing here —
the CLI renders the resolved map.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..config import ModelChoice
from .errors import BuildLoopError

# Closed routing-role alphabet — exactly the roles a build needs (write the
# code / adversarially audit it / make the judgement calls). Deliberately not
# config-schema state: absent = unrouted, and the block lives in per-proposal
# data so different builds can route differently.
ROUTING_KEYS: tuple[str, ...] = ("implementer", "auditor", "decisions")

_ROUTING_KEY_SET = frozenset(ROUTING_KEYS)

_ALLOWED_ALIASES = tuple(m.value for m in ModelChoice)

# Where resolve_routing reads by default relative to a proposal dir.
PROPOSAL_JSON_REL = "proposal.json"


def validate_routing(routing: Mapping[str, Any], *, origin: str) -> dict[str, str]:
    """Validate a raw routing mapping into ``{role: alias}`` strings.

    ``origin`` names the source in error messages (a file path or the
    ``--route`` flag). Raises ``BuildLoopError`` on a non-mapping payload,
    an unknown role key, or a value outside the :class:`ModelChoice`
    alphabet — every entry of which is legal, including ``current``
    (delegate to the active host session).
    """
    if not isinstance(routing, Mapping):
        raise BuildLoopError(
            f"{origin}: routing must be an object keyed by {', '.join(ROUTING_KEYS)}"
        )
    resolved: dict[str, str] = {}
    for key, value in routing.items():
        if key not in _ROUTING_KEY_SET:
            raise BuildLoopError(
                f"{origin}: unknown routing key {key!r} "
                f"(allowed: {', '.join(ROUTING_KEYS)})"
            )
        if not isinstance(value, str) or value not in _ALLOWED_ALIASES:
            raise BuildLoopError(
                f"{origin}: routing.{key}={value!r} is not one of: "
                f"{', '.join(_ALLOWED_ALIASES)}"
            )
        resolved[key] = value
    return resolved


def parse_route_flags(tokens: list[str]) -> dict[str, str]:
    """Parse repeatable ``--route k=v`` flag values into a validated map.

    Token parsing is CLI-side plumbing; validation is centralised here so
    ``propose --route`` and ``build --route`` reject exactly the same
    inputs. Raises ``BuildLoopError`` on a malformed token (missing ``=``
    or empty side), an unknown key, or an invalid alias.
    """
    raw: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep or not key or not value:
            raise BuildLoopError(
                f"--route expects k=v pairs (keys: {', '.join(ROUTING_KEYS)}), "
                f"got {token!r}"
            )
        raw[key] = value
    return validate_routing(raw, origin="--route")


def read_proposal_routing(proposal_json: Path) -> dict[str, str]:
    """Read + validate the ``routing`` object out of a ``proposal.json``.

    Absent file or absent/empty ``routing`` key → ``{}`` (unset). A
    malformed JSON artifact raises ``BuildLoopError``; an invalid routing
    block fails loudly with the file path as its origin.
    """
    path = Path(proposal_json)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildLoopError(f"could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("routing")
    if raw is None:
        return {}
    return validate_routing(raw, origin=str(path))


def resolve_routing(
    proposal_json: Path, cli_override: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Effective routing for a build — invocation > proposal > unset.

    Reads the proposal's ``routing`` block (validated), then overlays the
    validated CLI override. Returns a plain dict (possibly empty); callers
    render it verbatim as the effective-model disclosure.
    """
    resolved = read_proposal_routing(proposal_json)
    if cli_override:
        resolved.update(validate_routing(cli_override, origin="--route"))
    return resolved
