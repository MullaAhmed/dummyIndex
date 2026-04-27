<p align="center">
  <a href="https://github.com/MullaAhmed/dummyindex"><img src="https://raw.githubusercontent.com/MullaAhmed/dummyIndex/refs/heads/main/docs/logo-text.svg" width="260" alt="dummyIndex"/></a>
</p>

<p align="center">
  <a href="https://github.com/MullaAhmed"><img src="https://img.shields.io/badge/GitHub-Ahmed%20Mulla-181717?logo=github" alt="GitHub: Ahmed Mulla"/></a>
  <a href="https://www.linkedin.com/in/ahmed-mulla/"><img src="https://img.shields.io/badge/LinkedIn-Ahmed%20Mulla-0077B5?logo=linkedin" alt="LinkedIn: Ahmed Mulla"/></a>
</p>

> **Work in progress:** dummyindex is still evolving. It is built on top of Graphify's [https://github.com/safishamsi/graphify] knowledge-graph approach and extends it with agent-first workflows, richer code extraction, multimodal corpus support, persistent graph querying, assistant installation hooks, and local update tooling. The goal is to make Graphify's structural map useful during everyday AI-assisted development: not just to visualize a project once, but to help agents answer architecture questions, trace implementation paths, preserve context across sessions, and explain why parts of a codebase are connected.

**An AI coding assistant skill.** Type `/dummyindex` in Claude Code, Codex, OpenCode, Cursor, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Aider, OpenClaw, Factory Droid, Trae, Hermes, Kiro, or Google Antigravity - it reads your files, builds a knowledge graph, and gives you back structure you didn't know was there. Understand a codebase faster. Find the "why" behind architectural decisions.

Fully multimodal. Drop in code, PDFs, markdown, screenshots, diagrams, whiteboard photos, images in other languages, or video and audio files - dummyindex extracts concepts and relationships from all of it and connects them into one graph. Videos are transcribed with Whisper using a domain-aware prompt derived from your corpus. 25 languages supported via tree-sitter AST (Python, JS, TS, Go, Rust, Java, C, C++, Ruby, C#, Kotlin, Scala, PHP, Swift, Lua, Zig, PowerShell, Elixir, Objective-C, Julia, Verilog, SystemVerilog, Vue, Svelte, Dart).

> Andrej Karpathy keeps a `/raw` folder where he drops papers, tweets, screenshots, and notes. dummyindex is the answer to that problem - 71.5x fewer tokens per query vs reading the raw files, persistent across sessions, honest about what it found vs guessed.

```
/dummyindex .                        # works on any folder - your codebase, notes, papers, anything
```

```
dummyindex-out/
├── graph.html       interactive graph - open in any browser, click nodes, search, filter by community
├── GRAPH_REPORT.md  god nodes, surprising connections, suggested questions
├── graph.json       persistent graph - query weeks later without re-reading
├── structure_graph.html  top-down code structure viewer
├── structure_graph.json  folder → file → class/function tree with cross-edges
└── cache/           SHA256 cache - re-runs only process changed files
```

Add a `.dummyindexignore` file to exclude folders you don't want in the graph:

```
# .dummyindexignore
vendor/
node_modules/
dist/
*.generated.py
```

Same syntax as `.gitignore`. You can keep a single `.dummyindexignore` at your repo root — patterns work correctly even when dummyindex is run on a subfolder.

## How it works

dummyindex runs in three passes. First, a deterministic AST pass extracts structure from code files (classes, functions, imports, call graphs, docstrings, rationale comments) with no LLM needed. Second, video and audio files are transcribed locally with faster-whisper using a domain-aware prompt derived from corpus god nodes — transcripts are cached so re-runs are instant. Third, Claude subagents run in parallel over docs, papers, images, and transcripts to extract concepts, relationships, and design rationale. The results are merged into a NetworkX graph, clustered with Leiden community detection, and exported as interactive HTML, queryable JSON, and a plain-language audit report.

**Clustering is graph-topology-based — no embeddings.** Leiden finds communities by edge density. The semantic similarity edges that Claude extracts (`semantically_similar_to`, marked INFERRED) are already in the graph, so they influence community detection directly. The graph structure is the similarity signal — no separate embedding step or vector database needed.

Every relationship is tagged `EXTRACTED` (found directly in source), `INFERRED` (reasonable inference, with a confidence score), or `AMBIGUOUS` (flagged for review). You always know what was found vs guessed.

## Install

**Requires:** Python 3.10+ and one of: [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex), [OpenCode](https://opencode.ai), [Cursor](https://cursor.com), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli), [VS Code Copilot Chat](https://code.visualstudio.com/docs/copilot/overview), [Aider](https://aider.chat), [OpenClaw](https://openclaw.ai), [Factory Droid](https://factory.ai), [Trae](https://trae.ai), [Kiro](https://kiro.dev), Hermes, or [Google Antigravity](https://antigravity.google)

```bash
# Recommended — works on Mac and Linux with no PATH setup needed
uv tool install dummyindex && dummyindex install
# or with pipx
pipx install dummyindex && dummyindex install
# or plain pip
pip install dummyindex && dummyindex install
```

> **Official package:** The PyPI package is named `dummyindex` (install with `pip install dummyindex`). Other packages named `dummyindex*` on PyPI are not affiliated with this project. The only official repository is [MullaAhmed/dummyindex](https://github.com/MullaAhmed/dummyindex). The CLI and skill command are still `dummyindex`.

> **`dummyindex: command not found`?** Use `uv tool install dummyindex` (recommended) or `pipx install dummyindex` — both put the CLI in a managed location that's automatically on PATH. With plain `pip`, you may need to add `~/.local/bin` (Linux) or `~/Library/Python/3.x/bin` (Mac) to your PATH, or run `python -m dummyindex` instead. On Windows, pip scripts land in `%APPDATA%\Python\PythonXY\Scripts`.

### Platform support

| Platform | Install command |
|----------|----------------|
| Claude Code (Linux/Mac) | `dummyindex install` |
| Claude Code (Windows) | `dummyindex install` (auto-detected) or `dummyindex install --platform windows` |
| Codex | `dummyindex install --platform codex` |
| OpenCode | `dummyindex install --platform opencode` |
| GitHub Copilot CLI | `dummyindex install --platform copilot` |
| VS Code Copilot Chat | `dummyindex vscode install` |
| Aider | `dummyindex install --platform aider` |
| OpenClaw | `dummyindex install --platform claw` |
| Factory Droid | `dummyindex install --platform droid` |
| Trae | `dummyindex install --platform trae` |
| Trae CN | `dummyindex install --platform trae-cn` |
| Gemini CLI | `dummyindex install --platform gemini` |
| Hermes | `dummyindex install --platform hermes` |
| Kiro IDE/CLI | `dummyindex kiro install` |
| Cursor | `dummyindex cursor install` |
| Google Antigravity | `dummyindex antigravity install` |

Codex users also need `multi_agent = true` under `[features]` in `~/.codex/config.toml` for parallel extraction. Factory Droid uses the `Task` tool for parallel subagent dispatch. OpenClaw and Aider use sequential extraction (parallel agent support is still early on those platforms). Trae uses the Agent tool for parallel subagent dispatch and does **not** support PreToolUse hooks — AGENTS.md is the always-on mechanism. Codex supports PreToolUse hooks — `dummyindex codex install` installs one in `.codex/hooks.json` in addition to writing AGENTS.md.

Then open your AI coding assistant and type:

```
/dummyindex .
```

Note: Codex uses `$` instead of `/` for skill calling, so type `$dummyindex .` instead.

### Make your assistant always use the graph (recommended)

After building a graph, run this once in your project:

| Platform | Command |
|----------|---------|
| Claude Code | `dummyindex claude install` |
| Codex | `dummyindex codex install` |
| OpenCode | `dummyindex opencode install` |
| GitHub Copilot CLI | `dummyindex copilot install` |
| VS Code Copilot Chat | `dummyindex vscode install` |
| Aider | `dummyindex aider install` |
| OpenClaw | `dummyindex claw install` |
| Factory Droid | `dummyindex droid install` |
| Trae | `dummyindex trae install` |
| Trae CN | `dummyindex trae-cn install` |
| Cursor | `dummyindex cursor install` |
| Gemini CLI | `dummyindex gemini install` |
| Hermes | `dummyindex hermes install` |
| Kiro IDE/CLI | `dummyindex kiro install` |
| Google Antigravity | `dummyindex antigravity install` |

**Claude Code** does two things: writes a `CLAUDE.md` section telling Claude to read `dummyindex-out/GRAPH_REPORT.md` before answering architecture questions, and installs a **PreToolUse hook** (`settings.json`) that fires before every Glob and Grep call. If a knowledge graph exists, Claude sees: _"dummyindex: Knowledge graph exists. Read GRAPH_REPORT.md for god nodes and community structure before searching raw files."_ — so Claude navigates via the graph instead of grepping through every file.

**Codex** writes to `AGENTS.md` and also installs a **PreToolUse hook** in `.codex/hooks.json` that fires before every Bash tool call — same always-on mechanism as Claude Code.

**OpenCode** writes to `AGENTS.md` and also installs a **`tool.execute.before` plugin** (`.opencode/plugins/dummyindex.js` + `opencode.json` registration) that fires before bash tool calls and injects the graph reminder into tool output when the graph exists.

**Cursor** writes `.cursor/rules/dummyindex.mdc` with `alwaysApply: true` — Cursor includes it in every conversation automatically, no hook needed.

**Gemini CLI** copies the skill to `~/.gemini/skills/dummyindex/SKILL.md`, writes a `GEMINI.md` section, and installs a `BeforeTool` hook in `.gemini/settings.json` that fires before file-read tool calls — same always-on mechanism as Claude Code.

**Aider, OpenClaw, Factory Droid, Trae, and Hermes** write the same rules to `AGENTS.md` in your project root and copy the skill to the platform's global skill directory. These platforms don't support tool hooks, so AGENTS.md is the always-on mechanism.

**Kiro IDE/CLI** writes the skill to `.kiro/skills/dummyindex/SKILL.md` (invoked via `/dummyindex`) and a steering file to `.kiro/steering/dummyindex.md` with `inclusion: always` — Kiro injects this into every conversation automatically, no hook needed.

**Google Antigravity** writes `.agents/rules/dummyindex.md` (always-on rules) and `.agents/workflows/dummyindex.md` (registers `/dummyindex` as a slash command). No hook equivalent exists in Antigravity — rules are the always-on mechanism.

**GitHub Copilot CLI** copies the skill to `~/.copilot/skills/dummyindex/SKILL.md`. Run `dummyindex copilot install` to set it up.

**VS Code Copilot Chat** installs a Python-only skill (works on Windows PowerShell and macOS/Linux alike) and writes `.github/copilot-instructions.md` in your project root — VS Code reads this automatically every session, making graph context always-on without any hook mechanism. Run `dummyindex vscode install`. Note: this configures the chat panel in VS Code, not the Copilot CLI terminal tool.

Uninstall with the matching uninstall command (e.g. `dummyindex claude uninstall`).

**Always-on vs explicit trigger — what's the difference?**

The always-on hook surfaces `GRAPH_REPORT.md` — a one-page summary of god nodes, communities, and surprising connections. Your assistant reads this before searching files, so it navigates by structure instead of keyword matching. That covers most everyday questions.

`/dummyindex query`, `/dummyindex path`, and `/dummyindex explain` go deeper: they traverse the raw `graph.json` hop by hop, trace exact paths between nodes, and surface edge-level detail (relation type, confidence score, source location). Use them when you want a specific question answered from the graph rather than a general orientation.

Think of it this way: the always-on hook gives your assistant a map. The `/dummyindex` commands let it navigate the map precisely.

### Team workflows

`dummyindex-out/` is designed to be committed to git so every teammate starts with a fresh map.

**Recommended `.gitignore` additions:**
```
# keep graph outputs, skip heavy/local-only files
dummyindex-out/cache/            # optional: commit for shared extraction speed, skip to keep repo small
dummyindex-out/manifest.json     # mtime-based, invalid after git clone — always gitignore this
dummyindex-out/cost.json         # local token tracking, not useful to share
```

**Shared setup:**
1. One person runs `/dummyindex .` to build the initial graph and commits `dummyindex-out/`.
2. Everyone else pulls — their assistant reads `GRAPH_REPORT.md` immediately with no extra steps.
3. Install the post-commit hook (`dummyindex hook install`) so the graph rebuilds automatically after code changes — no LLM calls needed for code-only updates.
4. For doc/paper changes, whoever edits the files runs `/dummyindex --update` to refresh semantic nodes.

**Excluding paths** — create `.dummyindexignore` in your project root (same syntax as `.gitignore`). Files matching those patterns are skipped during detection and extraction.

```
# .dummyindexignore example
AGENTS.md          # dummyindex install files — don't extract your own instructions as knowledge
CLAUDE.md
GEMINI.md
.gemini/
.opencode/
docs/translations/ # generated content you don't want in the graph
```

## Using `graph.json` with an LLM

`graph.json` is not meant to be pasted into a prompt all at once. The useful
workflow is:

1. Start with `dummyindex-out/GRAPH_REPORT.md` for the high-level overview.
2. Use `dummyindex query` to pull a smaller subgraph for the specific question
   you want to answer.
3. Give that focused output to your assistant instead of dumping the full raw
   corpus.

For example, after running dummyindex on a project:

```bash
dummyindex query "show the auth flow" --graph dummyindex-out/graph.json
dummyindex query "what connects DigestAuth to Response?" --graph dummyindex-out/graph.json
```

The output includes node labels, edge types, confidence tags, source files, and
source locations. That makes it a good intermediate context block for an LLM:

```text
Use this graph query output to answer the question. Prefer the graph structure
over guessing, and cite the source files when possible.
```

If your assistant supports tool calling or MCP, use the graph directly instead
of pasting text. dummyindex can expose `graph.json` as an MCP server:

```bash
python -m dummyindex.runtime.serve dummyindex-out/graph.json
```

That gives the assistant structured graph access for repeated queries such as
`query_graph`, `get_node`, `get_neighbors`, and `shortest_path`.

> **WSL / Linux note:** Ubuntu ships `python3`, not `python`. Install into a project venv to avoid PEP 668 conflicts, and use the full venv path in your `.mcp.json`:
> ```bash
> python3 -m venv .venv && .venv/bin/pip install "dummyindex[mcp]"
> ```
> ```json
> { "mcpServers": { "dummyindex": { "type": "stdio", "command": ".venv/bin/python3", "args": ["-m", "dummyindex.runtime.serve", "dummyindex-out/graph.json"] } } }
> ```
> Also note: the PyPI package is `dummyindex` (double-y) — `pip install dummyindex` installs an unrelated package.

## Usage

### AI assistant command

Use these from Claude Code, Codex, OpenCode, Cursor, Gemini CLI, Copilot Chat, or another supported assistant after installing the skill:

```
/dummyindex                          # run on current directory
/dummyindex ./raw                    # run on a specific folder
/dummyindex ./raw --mode deep        # more aggressive INFERRED edge extraction
/dummyindex ./raw --update           # re-extract only changed files, merge into existing graph
/dummyindex ./raw --directed          # build directed graph (preserves edge direction: source→target)
/dummyindex ./raw --cluster-only     # rerun clustering on existing graph, no re-extraction
/dummyindex ./raw --no-viz           # skip HTML, just produce report + JSON
/dummyindex ./raw --wiki             # build agent-crawlable wiki
/dummyindex ./raw --obsidian                          # also generate Obsidian vault (opt-in)
/dummyindex ./raw --obsidian --obsidian-dir ~/vaults/myproject  # write vault to a specific directory
/dummyindex ./raw --whisper-model medium              # use a larger local Whisper model

/dummyindex add https://arxiv.org/abs/1706.03762        # fetch a paper, save, update graph through the assistant
/dummyindex add https://x.com/karpathy/status/...       # fetch a tweet
/dummyindex add <video-url>                              # download audio, transcribe, add to graph
/dummyindex add https://... --author "Name"             # tag the original author
/dummyindex add https://... --contributor "Name"        # tag who added it to the corpus

/dummyindex query "what connects attention to the optimizer?"
/dummyindex query "what connects attention to the optimizer?" --dfs   # trace a specific path
/dummyindex query "what connects attention to the optimizer?" --budget 1500  # cap at N tokens
/dummyindex path "DigestAuth" "Response"
/dummyindex explain "SwinTransformer"

/dummyindex ./raw --watch            # auto-sync graph as files change (code: instant, docs: notifies you)
/dummyindex ./raw --wiki             # build agent-crawlable wiki (index.md + article per community)
/dummyindex ./raw --svg              # export graph.svg
/dummyindex ./raw --graphml          # export graph.graphml (Gephi, yEd)
/dummyindex ./raw --neo4j            # generate cypher.txt for Neo4j
/dummyindex ./raw --neo4j-push bolt://localhost:7687    # push directly to a running Neo4j instance
/dummyindex ./raw --mcp              # start MCP stdio server
```

### Terminal CLI

Use these directly from a shell after installing the Python package:

```bash
# git hooks - platform-agnostic, rebuild graph on commit and branch switch
dummyindex hook install
dummyindex hook uninstall
dummyindex hook status

# always-on assistant instructions - platform-specific
dummyindex claude install            # CLAUDE.md + PreToolUse hook (Claude Code)
dummyindex claude uninstall
dummyindex codex install             # AGENTS.md + PreToolUse hook in .codex/hooks.json (Codex)
dummyindex opencode install          # AGENTS.md + tool.execute.before plugin (OpenCode)
dummyindex cursor install            # .cursor/rules/dummyindex.mdc (Cursor)
dummyindex cursor uninstall
dummyindex gemini install            # GEMINI.md + BeforeTool hook (Gemini CLI)
dummyindex gemini uninstall
dummyindex copilot install           # skill file (GitHub Copilot CLI)
dummyindex copilot uninstall
dummyindex aider install             # AGENTS.md (Aider)
dummyindex aider uninstall
dummyindex claw install              # AGENTS.md (OpenClaw)
dummyindex droid install             # AGENTS.md (Factory Droid)
dummyindex trae install              # AGENTS.md (Trae)
dummyindex trae uninstall
dummyindex trae-cn install           # AGENTS.md (Trae CN)
dummyindex trae-cn uninstall
dummyindex hermes install             # AGENTS.md + ~/.hermes/skills/ (Hermes)
dummyindex hermes uninstall
dummyindex kiro install               # .kiro/skills/ + .kiro/steering/dummyindex.md (Kiro IDE/CLI)
dummyindex kiro uninstall
dummyindex antigravity install       # .agents/rules + .agents/workflows (Google Antigravity)
dummyindex antigravity uninstall

# query and navigate the graph directly from the terminal (no AI assistant needed)
dummyindex query "what connects attention to the optimizer?"
dummyindex query "show the auth flow" --dfs
dummyindex query "what is CfgNode?" --budget 500
dummyindex query "..." --graph path/to/graph.json
dummyindex path "DigestAuth" "Response"       # shortest path between two nodes
dummyindex explain "SwinTransformer"           # plain-language explanation of a node

# add content from the terminal
dummyindex add https://arxiv.org/abs/1706.03762          # fetch paper, save to ./raw
dummyindex add https://... --author "Name" --contributor "Name"
dummyindex update .                                      # merge code changes into an existing graph

# save useful Q&A back into dummyindex-out/memory/
dummyindex save-result --question "..." --answer "..." --nodes NodeA NodeB

# incremental update and maintenance
dummyindex watch ./src                         # auto-rebuild on code changes
dummyindex check-update ./src                  # check if semantic re-extraction is pending (cron-safe)
dummyindex update ./src                        # re-extract code files, no LLM needed
dummyindex cluster-only ./my-project           # rerun clustering on existing graph.json
```

Works with any mix of file types:

| Type | Extensions | Extraction |
|------|-----------|------------|
| Code | `.py .js .ts .jsx .tsx .mjs .ejs .go .rs .java .c .h .cpp .hpp .cc .cxx .rb .cs .kt .kts .scala .php .blade.php .swift .lua .toc .zig .ps1 .ex .exs .m .mm .jl .vue .svelte .dart .v .sv` | AST via tree-sitter + call-graph (cross-file for all languages) + Java extends/implements + docstring/comment rationale |
| Docs | `.md .mdx .html .txt .rst` | Concepts + relationships + design rationale via Claude |
| Office | `.docx .xlsx` | Converted to markdown then extracted via Claude (requires `pip install dummyindex[office]`) |
| Papers | `.pdf` | Citation mining + concept extraction |
| Images | `.png .jpg .jpeg .webp .gif .svg` | Claude vision - screenshots, diagrams, any language |
| Video / Audio | `.mp4 .mov .mkv .webm .avi .m4v .mp3 .wav .m4a .ogg` | Transcribed locally with faster-whisper, transcript fed into Claude extraction (requires `pip install dummyindex[video]`) |
| YouTube / URLs | any video URL | Audio downloaded via yt-dlp, then same Whisper pipeline (requires `pip install dummyindex[video]`) |

## Video and audio corpus

Drop video or audio files into your corpus folder alongside your code and docs — dummyindex picks them up automatically:

```bash
pip install 'dummyindex[video]'   # one-time setup
/dummyindex ./my-corpus            # transcribes any video/audio files it finds
```

Add a YouTube video (or any public video URL) directly:

```bash
/dummyindex add <video-url>
```

yt-dlp downloads audio-only (fast, small), Whisper transcribes it locally, and the transcript is fed into the same extraction pipeline as your other docs. Transcripts are cached in `dummyindex-out/transcripts/` so re-runs skip already-transcribed files.

For better accuracy on technical content, use a larger model:

```bash
/dummyindex ./my-corpus --whisper-model medium
```

Audio never leaves your machine. All transcription runs locally.

## What you get

**God nodes** - highest-degree concepts (what everything connects through)

**Surprising connections** - ranked by composite score. Code-paper edges rank higher than code-code. Each result includes a plain-English why.

**Suggested questions** - 4-5 questions the graph is uniquely positioned to answer

**The "why"** - docstrings, inline comments (`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`), and design rationale from docs are extracted as `rationale_for` nodes. Not just what the code does - why it was written that way.

**Confidence scores** - every INFERRED edge has a `confidence_score` (0.0-1.0). You know not just what was guessed but how confident the model was. EXTRACTED edges are always 1.0.

**Semantic similarity edges** - cross-file conceptual links with no structural connection. Two functions solving the same problem without calling each other, a class in code and a concept in a paper describing the same algorithm.

**Hyperedges** - group relationships connecting 3+ nodes that pairwise edges can't express. All classes implementing a shared protocol, all functions in an auth flow, all concepts from a paper section forming one idea.

**Token benchmark** - printed automatically after every run. On a mixed corpus (Karpathy repos + papers + images): **71.5x** fewer tokens per query vs reading raw files. The first run extracts and builds the graph (this costs tokens). Every subsequent query reads the compact graph instead of raw files — that's where the savings compound. The SHA256 cache means re-runs only re-process changed files.

**Auto-sync** (`--watch`) - run in a background terminal and the graph updates itself as your codebase changes. Code file saves trigger an instant rebuild (AST only, no LLM). Doc/image changes notify you to run `--update` for the LLM re-pass.

**Git hooks** (`dummyindex hook install`) - installs post-commit and post-checkout hooks. Graph rebuilds automatically after every commit and every branch switch. If a rebuild fails, the hook exits with a non-zero code so git surfaces the error instead of silently continuing. No background process needed.

**Wiki** (`--wiki`) - Wikipedia-style markdown articles per community and god node, with an `index.md` entry point. Point any agent at `index.md` and it can navigate the knowledge base by reading files instead of parsing JSON.

**Structure graph** - `structure_graph.html` and `structure_graph.json` are generated for code corpora. They show the deterministic folder → file → class/function hierarchy plus cross-file relationships, which is usually the fastest entry point for codebase navigation.

## Worked examples

| Corpus | Files | Reduction | Output |
|--------|-------|-----------|--------|
| Karpathy repos + 5 papers + 4 images | 52 | **71.5x** | [`worked/karpathy-repos/`](worked/karpathy-repos/) |
| dummyindex source + Transformer paper | 4 | **5.4x** | [`worked/mixed-corpus/`](worked/mixed-corpus/) |
| httpx (synthetic Python library) | 6 | ~1x | [`worked/httpx/`](worked/httpx/) |

Token reduction scales with corpus size. 6 files fits in a context window anyway, so graph value there is structural clarity, not compression. At 52 files (code + papers + images) you get 71x+. Each `worked/` folder has the raw input files and the actual output (`GRAPH_REPORT.md`, `graph.json`) so you can run it yourself and verify the numbers.

## Privacy

dummyindex sends file contents to your AI coding assistant's underlying model API for semantic extraction of docs, papers, and images — Anthropic (Claude Code), OpenAI (Codex), or whichever provider your platform uses. Code files are processed locally via tree-sitter AST — no file contents leave your machine for code. Video and audio files are transcribed locally with faster-whisper — audio never leaves your machine. No telemetry, usage tracking, or analytics of any kind. The only network calls are to your platform's model API during extraction, using your own API key.

## Tech stack

NetworkX + Leiden (graspologic) + tree-sitter + vis.js. Semantic extraction via Claude (Claude Code), GPT-4 (Codex), or whichever model your platform runs. Video transcription via faster-whisper + yt-dlp (optional, `pip install dummyindex[video]`). No Neo4j required, no server, runs entirely locally.

## Package layout

The `dummyindex/` package is organized by responsibility:

- `dummyindex/pipeline/` — detection, extraction, validation, build, and export
- `dummyindex/analysis/` — clustering, reporting, benchmarking, and wiki generation
- `dummyindex/runtime/` — watch mode, MCP serving, security, hooks, ingest, and transcription
- `dummyindex/skills/` — packaged platform skill markdown installed by `dummyindex install`

Public imports such as `dummyindex.pipeline.build`, `dummyindex.pipeline.detect`, and `dummyindex.runtime.watch` remain valid for backward compatibility.

<details>
<summary>Contributing</summary>

**Worked examples** are the most trust-building contribution. Run `/dummyindex` on a real corpus, save output to `worked/{slug}/`, write an honest `review.md` evaluating what the graph got right and wrong, submit a PR.

**Extraction bugs** - open an issue with the input file, the cache entry (`dummyindex-out/cache/`), and what was missed or invented.

See [ARCHITECTURE.md](ARCHITECTURE.md) for module responsibilities and how to add a language.

</details>
