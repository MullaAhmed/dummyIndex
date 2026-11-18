"""``apply --source``: replace template specialist bodies with proven upstream skills.

Policy is pure (``plugins/sourcing.py``, ``generate/sourced.py``); every network
call goes through ``discover._RUNNER``, read at call time. Read-only: the caller
decides whether to write.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from typing import TextIO

from dummyindex.context.domains.equip.enums import EquipmentKind
from dummyindex.context.domains.equip.errors import SourceError
from dummyindex.context.domains.equip.generate.sourced import (
    compose_body,
    render_overlay,
    sourced_description,
    sourced_item,
)
from dummyindex.context.domains.equip.generate.specialists import templated_capabilities
from dummyindex.context.domains.equip.lifecycle.status import (
    classify_item,
    is_evolved,
    is_sourced,
    is_user_owned,
)
from dummyindex.context.domains.equip.models import (
    EquipmentItem,
    EquipmentManifest,
    StackProfile,
)
from dummyindex.context.domains.equip.plugins.marketplace import SEED_MARKETPLACES
from dummyindex.context.domains.equip.plugins.sources import (
    RepoMeta,
    Runner,
    available_tools,
    fetch_file,
    find_skills_sh,
    is_safe_repo,
    is_safe_skill,
    list_skills,
    repo_meta,
    resolve_ref,
    search_github,
)
from dummyindex.context.domains.equip.plugins.sourcing import (
    SkillCandidate,
    gate_reason,
    lf,
    matches,
    needs_approval,
    rank,
    scan_body,
    split_frontmatter,
)

from . import discover

Rendered = tuple[tuple[EquipmentItem, str, str], ...]
_SHORTLIST = 5  # SKILL.md fetches per channel per target
_MAX_SEARCHES = 3  # GitHub searches per run
_MAX_SEARCH_REPOS = 3  # repos listed per search
_TRUSTED = frozenset(s.repo for s in SEED_MARKETPLACES if s.trusted)


@dataclasses.dataclass
class _Session:
    """Per-run network cache: each repo is resolved and listed at most once."""

    runner: Runner
    out: TextIO
    _shas: dict[str, str | None] = dataclasses.field(default_factory=dict)
    _metas: dict[str, RepoMeta | None] = dataclasses.field(default_factory=dict)
    _listings: dict[str, tuple] = dataclasses.field(default_factory=dict)
    searches: int = 0
    skills_sh_down: bool = False

    def sha(self, repo: str) -> str | None:
        """Pinned HEAD sha; failures are cached too."""
        if repo not in self._shas:
            try:
                self._shas[repo] = resolve_ref(repo, runner=self.runner)
            except SourceError:
                self._shas[repo] = None
        return self._shas[repo]

    def meta(self, repo: str) -> RepoMeta | None:
        """Repo metadata; failures are cached too."""
        if repo not in self._metas:
            try:
                self._metas[repo] = repo_meta(repo, runner=self.runner)
            except SourceError:
                self._metas[repo] = None
        return self._metas[repo]

    def listing(self, repo: str) -> tuple:
        """Skills under ``skills/`` in ``repo``; a bad listing is skipped with one line."""
        if repo not in self._listings:
            try:
                self._listings[repo] = list_skills(
                    repo, runner=self.runner, root_fallback=False
                )
            except SourceError as exc:
                print(f"source: skip {repo}: {exc}", file=self.out)
                self._listings[repo] = ()
        return self._listings[repo]

    def candidate(
        self,
        name: str,
        *,
        repo: str,
        skill: str,
        channel: str,
        marketplace: str,
        installs: int | None = None,
    ) -> SkillCandidate | None:
        """Gate, fetch and re-gate one upstream SKILL.md; ``None`` when it does not qualify."""
        if not is_safe_repo(repo) or not is_safe_skill(skill):
            return None
        # The path is built here, never taken from API output.
        path = f"skills/{skill}/SKILL.md"
        c = SkillCandidate(
            repo=repo,
            skill=skill,
            path=path,
            channel=channel,
            marketplace=marketplace,
            trusted=repo in _TRUSTED,
            installs=installs,
            meta=self.meta(repo),
            ref=self.sha(repo),
        )
        reason = gate_reason(c)
        if reason != "not fetched":
            print(f"source: {name} skip {repo}/{skill}: {reason}", file=self.out)
            return None
        try:
            text = fetch_file(repo, path, ref=c.ref, runner=self.runner)
        except SourceError:
            text = None
        if text is None:
            print(f"source: {name} skip {repo}/{skill}: fetch failed", file=self.out)
            return None
        text = lf(text)
        parts = split_frontmatter(text)
        c = dataclasses.replace(c, text=text, description=parts[0] if parts else "")
        reason = gate_reason(c)
        if reason is not None:
            print(f"source: {name} skip {repo}/{skill}: {reason}", file=self.out)
            return None
        return c


def _seeds(
    s: _Session, name: str, cap: str, toolchain: tuple[str, ...]
) -> tuple[SkillCandidate, ...]:
    """Channel 1: seed marketplaces, trusted seeds first, then seed order."""
    hits = []
    for index, seed in enumerate(SEED_MARKETPLACES):
        for ref in s.listing(seed.repo):
            if matches(ref.name, "", cap):
                hits.append((index, seed, ref))
    hits.sort(key=lambda h: (not h[1].trusted, h[0], h[2].name))
    cands = [
        s.candidate(
            name, repo=seed.repo, skill=ref.name, channel="seed", marketplace=seed.name
        )
        for _, seed, ref in hits[:_SHORTLIST]
    ]
    return rank([c for c in cands if c], cap, toolchain)


def _skills_sh(
    s: _Session, name: str, cap: str, toolchain: tuple[str, ...]
) -> tuple[SkillCandidate, ...]:
    """Channel 2: skills.sh names candidates only; content is still pinned ``gh api``."""
    if s.skills_sh_down:
        return ()
    refs, reason = find_skills_sh(cap, runner=s.runner)
    if reason is not None:
        print(f"source: skills.sh skipped ({reason})", file=s.out)
        # "no results" is a normal answer; anything else means the CLI is unusable.
        if reason != "no results":
            s.skills_sh_down = True
        return ()
    ordered = sorted(refs, key=lambda r: (-(r.installs or 0), r.repo, r.skill))
    cands = [
        s.candidate(
            name,
            repo=r.repo,
            skill=r.skill,
            channel="skills.sh",
            marketplace="skills.sh",
            installs=r.installs,
        )
        for r in ordered[:_SHORTLIST]
    ]
    return rank([c for c in cands if c], cap, toolchain)


def _github(
    s: _Session, name: str, cap: str, toolchain: tuple[str, ...]
) -> tuple[SkillCandidate, ...]:
    """Channel 3: capped GitHub search, then the first few repos' ``skills/`` dirs."""
    if s.searches >= _MAX_SEARCHES:
        return ()
    s.searches += 1
    res = search_github(f"{cap} skill", runner=s.runner)
    if res.degraded:
        print(
            f"source: GitHub code search unavailable ({res.reason or 'unknown'}) "
            "— results from repo search, may differ between runs",
            file=s.out,
        )
    repos = [r for r in res.repos if is_safe_repo(r)][:_MAX_SEARCH_REPOS]
    hits = [
        (repo, ref.name)
        for repo in repos
        for ref in s.listing(repo)
        if matches(ref.name, "", cap)
    ][:_SHORTLIST]
    cands = [
        s.candidate(
            name, repo=repo, skill=skill, channel="github", marketplace="github"
        )
        for repo, skill in hits
    ]
    return rank([c for c in cands if c], cap, toolchain)


def _is_target(
    item: EquipmentItem, prior_item: EquipmentItem | None, project_root: Path
) -> bool:
    """True when a rendered specialist may be replaced by an upstream skill."""
    if item.kind is not EquipmentKind.AGENT or not item.capabilities:
        return False
    if item.dimension not in (None, "procedure"):
        return False
    if item.capabilities[0] not in templated_capabilities():
        return False
    if prior_item is None or prior_item.origin_hash is None:
        return True
    # A sourced or patched body is never re-sourced, only checked upstream.
    if is_sourced(prior_item) or is_evolved(prior_item):
        return False
    return not is_user_owned(classify_item(project_root, prior_item))


def _upstream_check(s: _Session, prior: EquipmentManifest) -> None:
    """Report-only: flag sourced items whose upstream text changed since adoption."""
    for item in prior.items:
        if not (is_sourced(item) and item.origin_repo and item.package_source):
            continue
        sha = s.sha(item.origin_repo)
        if sha is None or sha == item.origin_ref:
            continue
        try:
            text = fetch_file(
                item.origin_repo, item.package_source, ref=sha, runner=s.runner
            )
        except SourceError:
            continue
        if text is None:
            continue
        digest = hashlib.sha256(lf(text).encode("utf-8")).hexdigest()
        if digest != item.package_sha256:
            print(f"source: needs-reverify (upstream changed) {item.name}", file=s.out)


def source_rendered(
    rendered: Rendered,
    prior: EquipmentManifest,
    *,
    project_root: Path,
    profile: StackProfile,
    proj: str,
    conventions: tuple[str, ...],
    approve: bool,
    out: TextIO,
) -> tuple[Rendered, tuple[str, ...]]:
    """Swap eligible template triples for upstream-sourced ones; return ``(rendered, adopted_names)``."""
    runner = discover._RUNNER
    if not available_tools(runner=runner).gh:
        print("source: gh unavailable — templates kept", file=out)
        return rendered, ()

    s = _Session(runner=runner, out=out)
    _upstream_check(s, prior)

    prior_by_name = {i.name: i for i in prior.items}
    targets = [
        idx
        for idx, (item, _, _) in enumerate(rendered)
        if _is_target(item, prior_by_name.get(item.name), project_root)
    ]
    if not targets:
        return rendered, ()

    toolchain = tuple(
        w.lower() for w in (profile.label, *profile.frameworks, profile.formatter) if w
    )
    overlay = render_overlay(profile=profile, proj=proj, conventions=conventions)
    result = list(rendered)
    adopted: list[str] = []
    for idx in targets:
        item, rel_path, _ = rendered[idx]
        name = item.name
        cap = item.capabilities[0]
        ranked = (
            _seeds(s, name, cap, toolchain)
            or _skills_sh(s, name, cap, toolchain)
            or _github(s, name, cap, toolchain)
        )
        if not ranked:
            print(f"source: {name} no qualified candidate — template kept", file=out)
            continue
        for c in ranked:
            trusted = "yes" if c.trusted else "no"
            print(
                f"source: {name} candidate {c.repo}/{c.skill}@{c.ref[:12]} "
                f"trusted={trusted} [{', '.join(scan_body(c.text))}]",
                file=out,
            )
        top = ranked[0]
        codes = scan_body(top.text)
        label = f"{top.repo}/{top.skill}@{top.ref[:12]} [{', '.join(codes)}]"
        if needs_approval(top, codes) and not approve:
            print(f"source: {name} needs --yes: {label}", file=out)
            continue
        body = split_frontmatter(top.text)[1]
        content = compose_body(
            overlay=overlay,
            name=name,
            description=sourced_description(cap, profile.label, top.repo, top.skill),
            repo=top.repo,
            skill=top.skill,
            ref=top.ref,
            body=body,
        )
        new_item = sourced_item(
            item,
            repo=top.repo,
            skill=top.skill,
            ref=top.ref,
            path=top.path,
            upstream_text=top.text,
            marketplace=top.marketplace,
            content=content,
        )
        result[idx] = (new_item, rel_path, content)
        adopted.append(name)
        print(f"source: {name} <- {label}", file=out)
    return tuple(result), tuple(adopted)
