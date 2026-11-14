"""Managed convention rule blocks parsed from authored docs."""

from __future__ import annotations

import json
import re

from dummyindex.shared.errors import EvolveError

_BLOCK = re.compile(
    r"<!-- dummyindex:rule (\{[^\n]+\}) -->\r?\n(.*?)\r?\n<!-- dummyindex:rule:end ([a-z0-9_.-]+) -->",
    re.S,
)


def rules_in(text: str) -> list[dict]:
    rules = []
    ids = set()
    for match in _BLOCK.finditer(text):
        try:
            meta = json.loads(match[1])
            if (
                not isinstance(meta, dict)
                or meta.get("id") != match[3]
                or match[3] in ids
            ):
                raise ValueError("duplicate or mismatched rule ID")
        except ValueError as exc:
            raise EvolveError(f"invalid managed convention rule: {exc}") from exc
        ids.add(match[3])
        rules.append(
            {**meta, "body": match[2], "start": match.start(), "end": match.end()}
        )
    if text.count("<!-- dummyindex:rule ") != len(rules):
        raise EvolveError(
            "malformed managed rule markers; preserve and repair document"
        )
    return rules
