# 02 — Mental model

dummyindex sees a codebase as four kinds of things, layered.

## The four kinds

- **Folder** — a directory in the repo tree.
- **File** — a source file. Has a language, a size, a list of symbols.
- **Feature** — a cohesive group of symbols/files that implements one capability.
- **Flow** — an ordered call sequence inside a feature, starting at an entry point.

## How they relate

```
folder
  └── folder
       └── file
            └── symbol (class / function / method)

feature ──┬── contains many ─→ files
          └── contains many ─→ flows
                                  └── traces ─→ sequence of symbols across files
```

- Folders contain folders and files. Pure structure.
- Features cut across folders. One feature can span many directories.
- Flows are ordered. A flow has a start (entry point) and a path through symbols.
- Symbols are atomic. They live in exactly one file, on specific lines.

## Why this matters

- An agent asking "where does X live?" walks **folders → files → symbols**.
- An agent asking "how does X work?" walks **features → flows → symbols**.
- These are different questions. They need different shapes.
- One repo → one tree (structure) + one set of features (behavior).

## What's a feature vs. what's a folder

- A folder is whatever the file system says it is.
- A feature is whatever the graph + agents say it is.
- A feature **can** mirror a folder (e.g., `app/auth/` ↔ `Authentication`).
- A feature **often** doesn't (e.g., a checkout feature may span `routes/`, `services/`, `models/`).
- Folders are the input; features are the output.

## What's a flow vs. what's a function

- A function is a single symbol.
- A flow is a chain of function calls — typically starting at an HTTP route, CLI command, or background job.
- Not every function is the start of a flow.
- Not every flow is worth recording (trivial 1-step traces get discarded).

## Confidence

Two values, always:

- `EXTRACTED` — the value came from deterministic parsing (AST, graph algorithm).
- `INFERRED` — an LLM (the council) wrote or rewrote the value.

Every artifact — every node, every doc — carries a confidence stamp. The agent reading `.context/` always knows what's machine truth vs. judgment.
