---
description: Token usage for the current chat — context window now + deduplicated session totals (incl. subagents)
allowed-tools: Bash(dummyindex:*)
---

Token usage for this chat (live, read from the session transcript):

!`dummyindex usage`

Present the report above to the user as-is — it is already formatted, so do not
recompute or reformat the numbers. Note that **Context window now** is the
main-thread figure that matches `/context`; the **Session cumulative** table is
deduplicated and the **subagents** column sums any Task/subagent transcripts,
folded into **total**. For history across all projects, mention
`dummyindex usage daily | session | monthly | blocks`. If the user asked a
specific question about their usage, answer it using these numbers.
