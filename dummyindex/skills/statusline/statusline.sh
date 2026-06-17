#!/usr/bin/env bash
# dummyindex freshness statusline — per-prompt HOT PATH (no Python).
#
# Echoes the pre-computed ``.context/`` freshness badge that the
# ``plan-update`` SessionStart hook caches under ``.context/cache/``. This is
# the fast path Claude Code's ``statusLine`` invokes on every prompt: it just
# reads one tiny gitignored file — it NEVER recomputes drift.
#
# Contract: print the badge if the cache exists, otherwise print nothing; exit
# 0 no matter what. It must never crash a user's shell, so every error is
# swallowed. The cold-path fallback (`dummyindex context statusline`) reads the
# exact same path.
#
# Wire it into ~/.claude/settings.json:
#   { "statusLine": { "type": "command", "command": "/abs/path/to/statusline.sh" } }
cat .context/cache/freshness-badge 2>/dev/null || true
