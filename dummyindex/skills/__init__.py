"""Packaged skill markdown files used by platform installers."""

# (package subdir, installed skill name). Lives here, not in installer/, so
# context/ can name the family without importing the install layer.
SIBLING_SKILLS = (
    ("memory", "dummyindex-remember"),
    ("plan", "dummyindex-plan"),
    ("equip", "dummyindex-equip"),
    ("build", "dummyindex-build"),
    ("audit", "dummyindex-audit"),
    ("gc", "dummyindex-gc"),
    ("fleet", "dummyindex-fleet"),
    ("update", "dummyindex-update"),
    ("evolve", "dummyindex-evolve"),
)
