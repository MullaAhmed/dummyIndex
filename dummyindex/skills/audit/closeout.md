# Audit closeout recipe

Finalize the report and classify every workpaper. Supply one semantic
`learning_reflection` (or `null`) and a specific nonempty `discarded` reason
for every workspace file. This stdlib recipe hashes files without importing dummyindex.

Save the code as a temporary script outside the audit workspace. From project
root, pass repo-relative workspace, input JSON, and new output manifest paths:

```text
python prepare-audit-closeout.py .context/audits/<slug> audit-input.json closeout-manifest.json
```

```python
import hashlib, json, os, sys
from pathlib import Path

root = Path.cwd().resolve()
def local(raw):
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must stay inside project: {raw}")
    path = root / path
    current = root
    for component in path.relative_to(root).parts:
        current = current / component
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)(): raise ValueError(f"link or junction refused: {current}")
    if not path.resolve().is_relative_to(root): raise ValueError(f"path escapes project: {raw}")
    return path

workspace, source, output = (local(arg) for arg in sys.argv[1:4])
if len(sys.argv) != 4 or len(workspace.relative_to(root).parts) != 3 or workspace.relative_to(root).parts[:2] != (".context", "audits"):
    raise ValueError("usage: script .context/audits/<slug> input.json output.json")
if not workspace.is_dir() or source == workspace or workspace in source.parents:
    raise ValueError("workspace must exist; input must be outside it")
if output == workspace or workspace in output.parents or output.exists() or not output.parent.is_dir():
    raise ValueError("output must be a new file outside the workspace")
files = []
for base, dirs, names in os.walk(workspace, followlinks=False):
    for name in dirs + names:
        path = Path(base) / name
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)() or not path.resolve().is_relative_to(workspace.resolve()): raise ValueError(f"symbolic link or escaping entry refused: {path}")
        if path.is_file(): files.append(path)
reviewed = {p.relative_to(workspace).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
data = json.loads(source.read_text(encoding="utf-8"))
if not isinstance(data, dict) or set(data) != {"learning_reflection", "discarded"}:
    raise ValueError("input needs only learning_reflection and discarded")
reasons = data["discarded"]
if not isinstance(reasons, dict) or set(reasons) != set(reviewed) or any(not isinstance(v, str) or not v.strip() for v in reasons.values()):
    raise ValueError("give every workspace file its own nonempty review reason")
reflection = data["learning_reflection"]
if reflection is not None: reflection["expected_sha256"] = reflection["expected_sha256"].lower()
manifest = {"state": "implemented", "reviewed_files": dict(sorted(reviewed.items())), "transfers": [], "discarded": dict(sorted(reasons.items()))}
if reflection is not None: manifest["learning_reflection"] = reflection
with output.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True); stream.write("\n")
print(output)
```

Input shape; `expected_sha256` is the start hash, only lowercased:

```json
{
  "learning_reflection": {"verified": true,
    "target": ".context/conventions/coding-practices.md", "rule_id": "parser-normalization",
    "body": "Use parse_token; see src/parser.py:L1-L3 and tests/test_parser.py:L1-L4.",
    "expected_sha256": "CAPTURED_HASH", "sources": ["src/parser.py", "tests/test_parser.py"],
    "tests": ["tests/test_parser.py"], "supersedes": []},
  "discarded": {
    "catalog.json": "Reviewed catalog; no durable lesson",
    "findings/reviewer.md": "Reviewed workpaper; no separate durable finding",
    "report.md": "Final report retained for the user"
  }
}
```

With no novel lesson, use `null`. Missing/unknown dispositions, symlinks,
escaping paths, or existing output fail. After CLI rejection, re-review; never
auto-refresh hashes or reasons. A successful receipt ends report edits.
