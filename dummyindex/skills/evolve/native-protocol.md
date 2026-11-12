# Native adaptive improvement

Use the active host's own agents. The run needs no executor script or provider setup.
This is an explicit improvement run, separate from ordinary one-rule closeout.
These instructions are for the conductor.
Each delegate performs only its one pending action, without recursively starting another improvement run.

Freeze development tasks, later held-out tasks and their independent checks before
running models. Give both arms the same task contracts, source and limits. Keep
all attempts, including failures and unavailable results.

Start the existing command with a native specification under the evolve run:

```json
{"execution":"native","model":"current","rubric":"project-artifacts-v1",
 "guidance":[{"path":".context/conventions/coding-practices.md"}],
 "cases":[{"id":"development","path":"cases/development.json","split":"validation"},
          {"id":"later","path":"cases/later.json","split":"heldout"}],
 "budget":{"actions":32,"seconds":1800}}
```

List project evaluator files in optional `grading_paths`. Their pinned contents
are supplied only to graders. Keep ordinary task-visible tests available to coders.

```text
dummyindex context evolve experiment --run improve --from-file .context/gc/evolve/improve/native-spec.json
```

The command returns one `pending` request. Use its exact `workspace`, model,
guidance identities and case, rather than the owner's checkout. A case may need
deterministic fixture preparation before its worker starts. Use only its pinned
task inputs.

Never supply evaluator code, held-out tasks or earlier conversations
to a development worker. Workspaces reduce accidental exposure. They do not add
an operating-system sandbox.

Handle the returned action once:

- **Execute:** dispatch a fresh native worker with that case and the exact
  guidance bodies. It writes real task artifacts. Record the worker's actual ID
  and observed guidance reads, not merely the role you assigned to it.
- **Grade:** use a separate fresh grader or independent deterministic checker on
  the provided artifact copy. Check functional outcomes and edit boundaries.
  The executor never grades itself. Return a result for every requested case and
  concrete diagnostic evidence. Wording or discovery is not a quality score.
- **Author:** dispatch a fresh native author with only the supplied development
  feedback, source and guidance. It returns one general or domain proposal, then
  an optional composition only after both measured results exist. Keep changes
  narrow and preserve owner guidance. Decline an unsupported proposal instead of
  inventing a lesson.

  General proposals address reusable workflow mistakes.
  Domain proposals address verified project contracts and helper use. Composition
  combines supported changes from the observed variants. Never author from
  held-out outcomes.

Save the response under the same run and pass that file to the same command:

```json
{"request_id":"EXACT_PENDING_ID","result":{"actor_id":"ACTUAL_HOST_WORKER_ID",
 "tokens":null,"cost_usd":null,"status":"completed",
 "loaded":[{"id":"EXACT_ID","version":"EXACT_VERSION","sha256":"EXACT_HASH"}]}}
```

Execution uses `status: completed` and `loaded`. A grading response uses
`status: measured`, `cases: [{id, status: pass|fail}]` and `evidence`. An author
returns `edits: {existing_guidance_path: full_replacement_text}`, `diagnosis` and
`prediction`, or `decline: true`. The CLI derives indices, stages accepted edits
and binds them to immutable feedback. Do not hand-edit its checkpoint or receipts.

Resume until `state: complete`. Repeating an accepted response is idempotent.
Conflicting responses, changed pinned inputs and late submissions are rejected.
An outstanding request is not permission to dispatch the same worker twice.
Save the request-to-worker ID mapping under the run before waiting.

On resume, attach to that original worker.
Missing dispatch records mean uncertain work, not permission for another paid attempt.
After interruption, recover the original worker/artifacts or end that attempt.
Use a new run for a deliberate fresh trial.
Correcting rejected transport metadata uses the same actor and artifacts, never
a replacement model attempt. An interrupted write remains stopped for inspection.

Snapshots are limited to 64 MB and 10,000 files. Reduce the prepared task slice
when a project exceeds those bounds rather than truncating source silently.
For a valid context graph, snapshots keep its active generation. Older immutable
shards remain in the owner's checkout. Unknown files are retained.

Keep missing token/cost telemetry `null`. A strict quality gain with regression
controls passing can qualify. Equal quality with unknown telemetry retains the
incumbent. Known spending, action counts and the original deadline survive
resumes.

The host must interrupt outstanding workers at that deadline. Python
cannot terminate workers owned by the host API. Unknown accounting cannot enforce
a dollar/token ceiling. Decline an unsupported cap before dispatch. The controller
stops further work when a requested cap lacks telemetry.

Count every author,
executor and grader activation. A grader may create normal caches, but must not
change its supplied inputs or add other artifacts while approving them.

If no development candidate strictly wins, the controller may probe one
byte-distinct quality tie, in general, domain, then composition order. It must
pass all required controls and preserve every development case the incumbent
passed. This only schedules the existing held-out pair. The incumbent stays
active.

Held-out qualification also preserves every incumbent pass, including
optional cases. Ties with unknown usage still retain the incumbent. Composition
scheduling and budgets are unchanged.

Only a separately qualified held-out winner becomes the recommendation. Applying
its returned `candidate_index` still requires the ordinary exact project gate and
recoverable promotion. An incumbent result has no candidate index to apply.
Report measured outcomes, unknown resources and limits separately. A small task
set can demonstrate improvement on those tasks. It cannot establish general
agent intelligence or learning.
