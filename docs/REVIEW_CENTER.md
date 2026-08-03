# Review Center

The Review Center is the local, project-agnostic listener-review surface for
Audiobook Harness 0.7.5. It is not publication authority. When explicitly
enabled, its server-owned monitor may start bounded convergence work without
granting review approval or promotion authority.

## Configure projects

Create `review-center.json` at a workspace root:

```json
{
  "version": 1,
  "default_project": "my-book",
  "projects": [
    {
      "id": "my-book",
      "path": "projects/my-book",
      "display_name": "My Book",
      "automation": {"enabled": true, "poll_seconds": 5, "max_iterations": 8}
    },
    {"id": "second-book", "path": "projects/second-book"}
  ]
}
```

Each project must contain the normal Audiobook Harness `project.yaml` and
`production/`/`staging/` contract. Project IDs are lowercase URL-safe values.
Paths must remain below the configured workspace root.

## Start and stop

```bash
scripts/review-center start --workspace-root . --config review-center.json
scripts/review-center status --workspace-root . --config review-center.json
scripts/review-center restart --workspace-root . --config review-center.json
scripts/review-center stop --workspace-root . --config review-center.json
```

The cross-platform equivalent is:

```bash
audiobook-harness review-center start --workspace-root . --config review-center.json
audiobook-harness review-center stop --workspace-root . --config review-center.json
```

The service binds to loopback only. It uses one port for the chooser, status,
media, draft autosave, and finalization. The controller keeps a temporary PID
file and refuses to operate on a mismatched process. Startup uses an exclusive
local lease, so repeated start requests while the server is launching are
idempotent rather than creating competing processes.

## Automatic bounded repair

Automation is opt-in per project. When enabled, Review Center owns a background
monitor that starts `audiobook-harness converge PROJECT` whenever current review
or phase evidence declares machine-actionable work. The worker reuses valid
phase receipts, stops after a repeated evidence identity, and never promotes
audio or fabricates review authority. GET and HEAD routes remain read-only.
When the bounded ladder stops, its terminal input identity suppresses further
dispatches until a review decision, repair plan, source, or other bound evidence
changes. The status API reports controller execution and production outcome as
separate fields, so `execution_state: blocked` or `succeeded` is never presented
as proof that an audio repair passed.

Use `audiobook-harness converge PROJECT --max-iterations 8` to run the same
controller without Review Center. Missing source, configuration, or local model
prerequisites stop as blockers rather than entering an unchanged retry loop.

## Routes

- `/` — redirects to the project chooser. Opening `http://127.0.0.1:8765/`
  is therefore always a safe entry point.
- `/review-center/` — project chooser.
- `/review-center/<project-id>/` — listener review page.
- `/review-center/<project-id>/api/status` — identity-safe review status.
- `/review-center/<project-id>/api/review-manifest` — current evidence.
- `/review-center/<project-id>/api/review-draft` — local draft state.
- `/review-center/<project-id>/api/finalize-review` — explicit finalization.

Existing `audiobook-harness review PROJECT` remains available for a single
project and is useful for a quick isolated review.

Dashboard and API responses are served with `Cache-Control: no-store` so a
local restart or project migration cannot leave the browser using a stale route
contract. Review media remains served through the hash-bound project routes.

## Safe workflow

1. Run `produce` or the explicit analyze/generate/verify/stage commands.
2. Start Review Center and choose the project.
3. Listen to the staged media and context evidence.
4. Save drafts as you work.
5. Finalize only the current review identity.
6. Let bounded feedback/repair work proceed.
7. Promote only after the normal staged gates pass.

If a project is generating, stale review controls are disabled. If its review
identity changes, previous drafts are discarded from the active view rather than
silently carried forward. A reject or uncertainty becomes traceable correction
work; it does not silently approve or weaken a quality threshold.
