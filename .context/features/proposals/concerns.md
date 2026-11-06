# Proposal boundaries

- The host decides which knowledge is accepted. Hashes bind the reviewed bytes;
  they do not independently prove a lesson is true or a reported test ran.
- A verification state needs evidence identities; a bare checkbox does not
  establish verification. Live environments remain an independent pending step.
- Text units are checked within their durable target, so unrelated convention
  edits do not invalidate closeout. Removing/replacing an accepted unit needs an
  explicit supersession reason. Fixtures retain exact content identity.
- The receipt is capped at 1 MB, accepted text at 64 KiB per unit, transfers at
  100 and workspace inventory at 2000 files. It stores metadata, not full traces.
- A process interruption can leave partial writes. The pending intent protects
  the workspace; review the new inventory and explicitly resume rather than
  pretending the transaction completed. No user workspace is deleted by closeout.
