# Proposal boundaries

- The host decides which knowledge is accepted. Hashes bind the reviewed bytes;
  they do not independently prove a lesson is true or a reported test ran.
- A verification state needs evidence identities; a bare checkbox does not
  establish verification. Live checks remain pending.
- Text units are checked within their durable target, so unrelated convention
  edits do not invalidate closeout. Removing/replacing an accepted unit needs a
  supersession reason. Fixtures retain exact content identity.
- The receipt is capped at 1 MB, accepted text at 64 KiB per unit, transfers at
  100 and workspace inventory at 2000 files.
- Exit status alone hides `blocked` and `pending` learning; read the printed
  `learning:` line.
- A process interruption can leave partial writes. The pending intent protects
  the workspace; review the inventory and explicitly resume, never assume
  completion. No user workspace is deleted by closeout.
