"""Fixed word sets for the restyle (ASD-STE100 rewrite) domain."""

from __future__ import annotations

# Counted per doc; a lower count fails, a higher count warns. Contractions are
# expanded first so `don't` -> `do not` leaves the count unchanged.
NEGATION_WORDS = ("not", "no", "never", "only", "must", "cannot")

# Expanded before the generic `n't` rule, which would give "ca not" for can't.
CONTRACTION_SPECIALS = (
    ("can't", "cannot"),
    ("won't", "will not"),
    ("shan't", "shall not"),
)

# Per-run snapshot file, kept under the gitignored cache folder with the originals.
SNAPSHOT_NAME = "snapshot.json"
