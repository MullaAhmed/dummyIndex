# Install surface concerns

- Ambiguous legacy files are intentionally preserved. A stale version stamp or
  familiar heading cannot prove their bytes are stock; an operator must review
  those survivors rather than force an ownership claim.
- Edited canonical guidance is authoritative user content. An update may retain
  it and leave a family incomplete; source warnings must remain visible even
  when CLI and stamp versions match.
- Link creation depends on host privileges and physical dotfiles layout. AUTO
  uses thin references when links are unavailable; strict `--link` reports the
  failure. Native references resolve relative to the canonical file and must be
  checked after moving a shared installation across filesystems.
- Metadata corruption must stop preparation of that family without deleting
  content. Ownership baselines protect ordinary updates; they are not a trust
  boundary against a local process that can rewrite both files and manifests.
- Per-file replacement is atomic, but a complete family is not a filesystem
  transaction. Interruption can leave a partial refresh; a repeat preparation
  reconciles known baselines, and completion/source verification exposes drift.
- Installation retains existing hook/plugin/config policies; this feature does
  not establish parity of every native host feature. Shared workflow bodies and
  explicit adapters prevent divergence in the installed workflow itself.
