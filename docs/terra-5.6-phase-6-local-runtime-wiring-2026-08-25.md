# Terra 5.6 Phase 6 — local runtime wiring

Date: 2026-08-25  
Branch: `codex/phase1b2-crawlee-secure-bridge`  
Status: zero-cost container exit gate passed

## Outcome

Phase 6 now has an opt-in, isolated catalogue worker and a read-only preflight command. The
default API image does not install Crawlee, the worker receives no JWT/API/SMTP configuration,
and every expensive or autonomous capability remains disabled by default.

The Docker/Compose re-audit passed on Docker Desktop, including Compose expansion, image build,
container startup, migrations, PostgreSQL concurrency, kill-switch behavior, Crawlee availability,
and the in-container preflight.

No scholarship was acquired or processed, no Azure credential was exercised, no model was
called, and nothing was published, deployed, pushed, or merged during this phase.

## Runtime wiring

- `Dockerfile` has a dedicated `catalogue-worker` target installed from the frozen `uv.lock`
  with the `crawlee` extra. A final `runtime`-derived stage remains the implicit default image.
- `compose.yaml` has an opt-in `catalogue` profile with a read-only worker filesystem, bounded
  `/tmp`, dropped Linux capabilities, `no-new-privileges`, the document transport volume, and a
  polling loop around `app.cli.process_catalogue_ingestion_runs`.
- The worker depends on completed migrations and a healthy API, but receives only the database,
  catalogue, and optional Azure credential environment surface. It receives no JWT, SMTP,
  account-email, API-key, or student-assistant secret.
- `.env.catalogue.example` contains safe first-pilot defaults. `.env.catalogue.local` and the
  `.catalogue-local/` receipt directory are ignored. The optional local env file was not needed
  or created for this zero-cost proof.
- The worker observes `/run/catalogue/STOP` before claiming work, between candidates, and between
  model objectives. The host can create `.catalogue-local/STOP` without changing the container.
- Existing durable queue claims, fenced leases, retries, dead letters, candidate checkpoints,
  and objective-level extraction reuse remain the stop/resume authority.

## Preflight contract

Run:

```text
python -m app.cli.catalogue_preflight
```

The command returns structured JSON and exits non-zero when an enabled dependency is blocked.
It performs no run creation, queue claim, source acquisition, extraction, model request, graph
write, review decision, or publication action.

It checks:

| Check | Behaviour |
| --- | --- |
| Database | Executes only `SELECT 1`. |
| Migrations | Compares database heads with the repository's current Alembic heads. |
| Disk | Compares temporary-volume free bytes with the configured minimum. |
| Kill switch | Requires an available, inactive switch path whenever AI ingestion is enabled. |
| Budgets | Reports candidate, page, call, input, output, and estimated-cost ceilings. |
| Worker | Requires a fresh, error-free `catalogue_ingestion` heartbeat only when configured. |
| Azure identity | Calls `DefaultAzureCredential.get_token` only when AI ingestion is enabled. |
| Model capability | Validates a local, expiring receipt for deployment, API version, model family, chat completions, and strict JSON Schema; it never probes the model. |
| Crawlee | Requires the optional package only when static Crawlee orchestration is enabled. |
| Documents/OCR | Requires a fresh filesystem transport heartbeat only when document conversion is enabled; OCR cannot be enabled without conversion. |
| Pilot policy | Blocks web discovery, browser fetching, scheduled ingestion, and graph rollout if any are enabled. Publication is reported as manual-only and disabled. |

Probe boundaries are injected in tests, so failure handling is deterministic and cannot
accidentally authenticate, acquire a source, or invoke a model.

## Local operator sequence

1. Keep AI, discovery, crawling, Crawlee, document conversion/OCR, routing, browser fetching,
   scheduling, and graph flags off for the zero-work baseline.
2. Inspect pending ingestion runs. Create `.catalogue-local/STOP` before startup if any work must
   be prevented from claiming.
3. Start the opt-in stack:

   ```text
   docker compose --profile catalogue up --build api catalogue-worker
   ```

4. After the worker has emitted a heartbeat, run:

   ```text
   docker compose exec catalogue-worker python -m app.cli.catalogue_preflight
   ```

5. To pause safely, create `.catalogue-local/STOP`. The worker will stop claiming work and will
   release an in-progress run at its next stage/objective boundary. Remove the file only when the
   operator intends processing to resume.
6. Before any approved AI pilot, copy
   `docs/catalogue-ai-capability-receipt.example.json` to
   `.catalogue-local/model-capability.json`, replace every example value with reviewed deployment
   evidence, provide positive pricing and `DefaultAzureCredential` inputs only through the ignored
   local file or shell environment, recreate the worker, and rerun preflight.

Preflight authorization is not authorization to process a candidate. Phase 7 still requires
explicit owner approval.

## Verification evidence

- Focused preflight tests: `7 passed`.
- Queue, Crawlee bridge, operations, and preflight integration set: `26 passed, 2 skipped`.
- Full backend suite excluding E2E: `768 passed, 23 skipped, 10 deselected`.
- Empty-queue worker smoke against a temporary database migrated to head:
  - preflight status: `ready`;
  - current/expected Alembic head: `20260825_0056`;
  - ingestion runs: `0`;
  - candidates: `0`;
  - catalogue worker heartbeat records: `1`.
- Ruff lint: passed.
- `git diff --check`: passed.
- Compose YAML structure and safe `.env.catalogue.example` defaults: parsed and asserted locally.

## Docker/Compose re-audit evidence

Docker was absent from the shell `PATH`, but the installed executable was found and invoked by
its absolute path:

```powershell
$DockerExe = 'C:\Users\Admin\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
Test-Path -LiteralPath $DockerExe
& $DockerExe version
& $DockerExe compose version
& $DockerExe info
& $DockerExe compose ps
& $DockerExe compose --profile catalogue config
```

`Test-Path` returned `True`. Docker Engine `29.7.2`, Docker Desktop `4.86.0`, and Compose
`5.3.1` responded on the healthy `desktop-linux` context. Compose expansion passed and showed
AI ingestion, bounded crawling, web discovery, browser fetching, scheduled ingestion, graph
reads/writes, and every other paid or autonomous capability disabled.

Before worker startup, the database contained 14 completed runs and no pending run, 62
candidates, and two historical extraction attempts. Those historical attempts recorded 4,236
input tokens, 1,581 output tokens, and `0.004222` estimated cost. This is pre-existing database
history, not usage or cost generated by this proof.

The ignored `.catalogue-local/STOP` kill switch was created before startup, and the safe profile
was built and started with:

```powershell
New-Item -ItemType File -Force '.catalogue-local\STOP'
& $DockerExe compose --profile catalogue up --build -d db migrate api catalogue-worker
```

The resulting containers were:

- `scholarship-ai-assistant-api-1` — healthy;
- `scholarship-ai-assistant-db-1` — healthy;
- `scholarship-ai-assistant-migrate-1` — exited `0`;
- `scholarship-ai-assistant-catalogue-worker-1` — running.

Migration logs showed ordered upgrades from `20260824_0053` through `20260825_0054`,
`20260825_0055`, and `20260825_0056`. The repository and database heads both reported
`20260825_0056`.

With the switch present, the worker logged `Catalogue ingestion paused: operator kill switch is
active`; preflight failed closed with `operator_kill_switch_active`, and nothing was claimed.
After reconfirming that no run was pending, the switch was removed. In-container preflight then
returned overall `ready`: database, migrations, heartbeat, disk, budgets, and kill switch were
ready, while AI, Azure credential/model capability, crawling, discovery, browser, scheduling, and
graph checks remained disabled.

The worker's bounded `/tmp` exposes 536,870,912 bytes. The former 1 GiB example minimum could
never pass in that 512 MiB volume, so `.env.catalogue.example` now uses
`APP_CATALOGUE_WORKER_MIN_FREE_DISK_BYTES=268435456` (256 MiB). The corrected check passed while
retaining a meaningful free-space margin.

Further in-container evidence:

```text
Crawlee: 1.9.2
Azure-prefixed environment names: []
API /health/ready: 200 {"status":"ready"}
```

An empty worker invocation with `--limit 1 --batch-size 1` completed without work. The database
counts and historical usage totals were unchanged afterward: 14 completed and zero pending runs,
62 candidates, two attempts, 4,236 input tokens, 1,581 output tokens, and `0.004222` estimated
historical cost. New provider calls, tokens, and estimated or observed Azure cost were all zero.

For the real PostgreSQL concurrency proof, a temporary Compose override published the database
only on `127.0.0.1:55432`, then the following module ran against it:

```powershell
$env:TEST_POSTGRES_URL = 'postgresql+psycopg://scholarship:scholarship@127.0.0.1:55432/scholarship'
uv run pytest tests/test_catalogue_ingestion_postgres.py -q
```

Result: `4 passed`, including the two-worker atomic budget-reservation test. The temporary
override was removed and the database was recreated without a published host port.

The completed verification set is therefore:

- focused catalogue safety: `104 passed`;
- PostgreSQL ingestion/concurrency: `4 passed`, no skips;
- full backend regression: `773 passed, 23 skipped, 10 deselected`;
- frontend: `37 passed`; production build passed;
- Compose expansion, build/start, migrations, health, Crawlee import, kill switch, in-container
  preflight, and empty-queue smoke: passed;
- Ruff and `git diff --check`: passed.

## Phase boundary

The zero-cost Phase 6 exit gate is passed. Phase 7 is the first live-source and paid-model phase;
it has not started. Do not authenticate to Azure, probe a deployment, enqueue a pilot candidate,
acquire live sources, or make a model call without explicit owner approval.
