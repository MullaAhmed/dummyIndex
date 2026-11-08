"""The toolkit item shape and the scope-fallback rule.

An item is what the GUI renders. Its ``scope`` is the *effective* scope; when the
caller asked for ``terminal`` and the item lives in project or user host config,
the effective scope is that host scope, ``scope_warning`` is true, and
``requested_scope`` records the ask. ``mechanism`` is non-null only for
terminal-scoped items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import SCOPES

HOST_WARNINGS = {
    "project": "Project scope: other sessions in this repo are affected.",
    "user": "User scope: affects every project on this machine.",
}
FALLBACK_WARNING = (
    "Per-terminal toggles are not proven for items already in {scope} config; "
    "this item is shown at {scope} scope and other sessions are affected."
)


@dataclass(frozen=True)
class ToolkitItem:
    kind: str
    name: str
    scope: str
    enabled: bool
    mechanism: str | None = None
    terminal_id: str | None = None
    requested_scope: str | None = None
    extra_warnings: tuple[str, ...] = field(default=())

    @property
    def scope_warning(self) -> bool:
        return self.scope in ("project", "user")

    @property
    def warnings(self) -> list[str]:
        out: list[str] = []
        if self.scope in HOST_WARNINGS:
            out.append(HOST_WARNINGS[self.scope])
        if self.requested_scope == "terminal" and self.scope in HOST_WARNINGS:
            out.append(FALLBACK_WARNING.format(scope=self.scope))
        out.extend(self.extra_warnings)
        return out

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "scope": self.scope,
            "terminal_id": self.terminal_id,
            "enabled": self.enabled,
            "scope_warning": self.scope_warning,
            "warnings": self.warnings,
            "mechanism": self.mechanism,
        }
        if self.requested_scope is not None:
            data["requested_scope"] = self.requested_scope
        return data


def fall_back(item: ToolkitItem, requested: str | None) -> ToolkitItem:
    """Return ``item`` with the fallback fields set when ``requested`` is terminal.

    Only host-scoped items fall back. Terminal-owned items already sit at terminal
    scope and are returned unchanged.
    """
    if requested != "terminal" or item.scope not in SCOPES or item.scope == "terminal":
        return item
    return ToolkitItem(
        kind=item.kind,
        name=item.name,
        scope=item.scope,
        enabled=item.enabled,
        mechanism=None,
        terminal_id=None,
        requested_scope="terminal",
        extra_warnings=item.extra_warnings,
    )
