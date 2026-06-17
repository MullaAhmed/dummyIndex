#!/usr/bin/env pwsh
# dummyindex freshness statusline — per-prompt HOT PATH (no Python).
#
# PowerShell twin of statusline.sh. Echoes the pre-computed ``.context/``
# freshness badge that the ``plan-update`` SessionStart hook caches under
# ``.context/cache/``. Reads one tiny gitignored file on every prompt; it NEVER
# recomputes drift.
#
# Contract: print the badge if the cache exists, otherwise print nothing; exit
# 0 no matter what — never crash a user's shell, so every error is swallowed.
# The cold-path fallback (`dummyindex context statusline`) reads the same path.
#
# Wire it into settings.json:
#   { "statusLine": { "type": "command", "command": "pwsh -File C:\\path\\to\\statusline.ps1" } }
$ErrorActionPreference = 'SilentlyContinue'
try {
    $badge = Get-Content -Raw -ErrorAction SilentlyContinue '.context/cache/freshness-badge'
    if ($badge) { Write-Host -NoNewline $badge }
} catch { }
exit 0
