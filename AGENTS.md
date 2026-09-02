<!-- dummyindex:begin:codex (managed — do not hand-edit; regenerate with `dummyindex install --platform codex`) -->
<!-- dummyindex:owner:project -->
## dummyIndex context engine

This repo has a generated context index at `.context/`. **Read
`.context/HOW_TO_USE.md` before any non-trivial task** and follow its routing
before searching source broadly. Treat the code as the source of truth when it
disagrees with the index. Refresh deterministic maps with `dummyindex context
rebuild --changed`; reconcile curated feature documentation through
`dummyindex context reconcile` (read-only), the dummyindex reconcile skill,
and `dummyindex context reconcile-stamp`. Invoke reusable dummyindex
workflows — `dummyindex`, `dummyindex-plan`, `dummyindex-build`,
`dummyindex-equip`, `dummyindex-audit`, `dummyindex-remember`,
`dummyindex-gc`, and `dummyindex-update` — through whatever mechanism your
host uses to invoke an installed skill. The user's explicit instruction wins
over an older `.context/` spec or plan; note the divergence and proceed. Use
your host's own session/usage reporting for context and token accounting;
`dummyindex usage` specifically reads saved Claude Code transcripts and is not
a general session reporter.

**Output policy — always on, never wait for an invocation.** Apply the combined `caveman`/`i-have-adhd` behavior to every reply; the rules below are self-contained, so follow them even when neither skill is loaded (the `i-have-adhd` skill sets `disable-model-invocation: true` and cannot apply itself). Lead with the outcome or the next action — a command, path, or `file:line` comes first and prose comes after. Keep prose compact: cut filler, pleasantries, hedging, and tool-call narration. Number multi-step work, one bounded action per step. Suppress tangents and options you are not taking. Restate the current state each turn rather than expecting the reader to hold it. Prefer specific quantities (counts, paths, durations) over vague ones like "a bit of work". Make finished work visible and end with one concrete next action. Compress the prose, never the substance — technical and safety detail, exact identifiers, commands, and error strings stay verbatim.

This policy holds for the whole session. It does not lapse after several turns or when the topic changes, and when you are unsure whether it still applies, it does. It yields to an explicit user formatting request and to safety requirements, and it stops when the user says so ("normal mode", "stop caveman", "stop adhd mode") — acknowledge in one line.

**Skill routing — always on.** Before replying or taking action, inspect the skills exposed by the current host and compare the user's request with every skill's description and trigger rules. Invoke each matching skill before doing its work, without waiting for the user to name it; a skill the user names is mandatory. Follow the selected skill's workflow before taking task actions. If no skill matches, proceed normally. An explicit user request not to use a skill wins. The `i-have-adhd` skill is the exception: it disables model invocation, so apply the output policy above directly instead of trying to invoke it. Route dummyindex planning, building, auditing, equipping, updating, remembering, and garbage collection to their corresponding `dummyindex-*` skills.
<!-- dummyindex:end:codex -->
