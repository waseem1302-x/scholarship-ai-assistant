# Terra extraction implementation log

This is the operational evidence record for the review-only extraction release
candidate. A check is reported as passing only when it completed in this
workspace on the stated baseline or subsequent commit. Environment-blocked and
failed checks are recorded separately.

## Baseline — 2026-08-24

- **Baseline commit:** `f6b3e45dc97c75c7886118d6b972a090ff56bd28`
- **Branch:** `codex/phase1b2-crawlee-secure-bridge`
- **Initial worktree:** one pre-existing modification, `uv.lock` (410 additions,
  one deletion). The diff adds Crawlee 1.9.2 and its transitive packages. It is
  preserved as user work and is not part of this implementation record.
- **Reference review:** all four 24 August audit Markdown files and all 26 pages
  of `scholarship-intelligence-platform-blueprint.pdf` were text-extracted and
  reviewed. Text confirms the target remains review-only with no automatic
  publication. Visual PDF review is environment-blocked: Poppler, Ghostscript,
  ImageMagick, LibreOffice, and PyMuPDF are unavailable; browser policy blocks
  local `file:` navigation. This is not recorded as a visual pass.
- **Current behaviour verified from source:** `POST /admin/catalogue-ingestion/runs/url`
  defaults `process_now` to true and invokes the entire pipeline in the request.
  `CatalogueIngestionRun` has no idempotency key or lease/fencing fields;
  candidate claims have leases but no fencing token. The existing worker CLI
  invokes `process_run` directly.

### Baseline commands and results

| Command | Result |
| --- | --- |
| `git status --short --branch` | Completed; only pre-existing `uv.lock` modification. |
| `uv --cache-dir .uv-cache run ruff check .` | Passed. |
| `uv --cache-dir .uv-cache run ruff format --check .` | Failed before this work: committed `app/modules/profiles/models.py` and `app/modules/profiles/schemas.py` would be reformatted. They are unrelated and intentionally untouched. |
| `uv --cache-dir .uv-cache run pytest -ra -m "not e2e"` | Environment-blocked by Windows Application Control (`pytest` launcher blocked, WinError 4551). |
| `uv --cache-dir .uv-cache run python -m pytest -ra -m "not e2e"` | Started but did not produce a completion summary through the command bridge; not counted as passed. Focused tests will use `python -m pytest` and report final summaries. |

### Source-snapshot acquisition experiment

All requests below used `SafeSourceFetcher(timeout_seconds=30, max_bytes=5_000_000)`.
The initial sandbox attempt failed closed at robots retrieval with WinError 10013;
the approved bounded read-only retry completed.

| Source | MIME | Raw hash | Normalized hash | Bytes | Normalized characters |
| --- | --- | --- | --- | ---: | ---: |
| `https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/` | `text/html` | `524c3f8c2a90a98ea774800ad80c2274aecde7c7d9350590063ad92f5853d7d4` | `137dfc2083704676e2be913797f4fdc4f75aaed3ee77ca382bba2a7b9c0370cc` | 28,825 | 8,854 |
| `https://www.studyinjapan.go.jp/en/_mt/2026/04/01-2027_Research_Guidelines_E.pdf` | `application/pdf` | `5a65f0c41f38ffbcf42e9b6e691731901955bea4efdaa34d7ab7ea55a3e3ae52` | `ed069fe906b2779647c18066c5563332f092dd76297b66dade6487947ac6b94f` | 416,454 | 52,169 |
| `https://od.globaluni.ru/` | `text/html` | `1185d4993f51f855d2d2e8284b02a629f7797f1a45bf6430bcbb8613a70c6855` | `ff1097998fde17133ee330ed7cfd12e25ed273cfa013c040ad40d8dbfb917c43` | 405,564 | 26,013 |

These hashes freeze observed source versions only. The repository does not yet
contain immutable raw fixtures, so MEXT/Open Doors protected-fixture gates are
**not executed** and must not be reported as passing.

## P0-A — contract and fixture freeze

- **Status:** partially complete; protected-fixture execution remains blocked.
- **Objective:** version the queued-ingestion and no-publication contracts;
  record source snapshot identities and the remaining raw-fixture gap.
- **Files changed:** `docs/decisions/0017-review-only-extraction-job-contract.md`,
  `docs/decisions/0018-protected-extraction-fixture-ledger.md`,
  `tests/fixtures/catalogue_extraction/source_snapshot_ledger.v1.json`, and
  `tests/test_catalogue_source_snapshot_ledger.py`.
- **Implementation:** ADR 0017 freezes the durable queue/lease/fencing and
  review-only boundary. ADR 0018 prevents snapshot hashes from being presented
  as executable protected fixtures. The ledger records three safe-acquisition
  source versions with raw and normalized hashes, MIME, byte and text lengths.
- **Security/trust invariants:** all capture requests used `SafeSourceFetcher`;
  neither the ledger nor its test enables automatic publication, live fixture
  access in tests, model calls, or arbitrary network clients.
- **Tests added:** ledger schema/identity validation and an explicit test that
  all currently recorded entries lack a raw fixture path.
- **Commands and results:**
  `uv --cache-dir .uv-cache run python -m pytest -q tests/test_catalogue_source_snapshot_ledger.py tests/test_complete_acquisition_contract.py`
  — **10 passed** (FastAPI/Starlette deprecation warning only).
- **Metrics/cost:** three bounded source acquisitions; no model calls and no
  database/graph/publication writes.
- **Known limitation:** source bytes and reviewed expected outcomes are absent.
  MEXT/Open Doors protected gates therefore remain blocked and are not
  equivalent to the snapshot-ledger tests.
- **Rollback:** remove only the additive ledger/ADRs; it has no runtime effect.

## P0-B — durable queued direct URL ingestion

- **Status:** implementation and SQLite migration regression are green;
  PostgreSQL concurrency execution remains environment-blocked.
- **Objective:** make direct URL requests enqueue-only and idempotent, and make
  the durable run claimable with leases, fencing, retry and dead-letter state.
- **Behavior before:** direct URL requests defaulted `process_now=true` and ran
  acquisition/extraction in the API request. Runs had no idempotency key,
  stage, run lease, token, retry classification or dead-letter timestamp.
  Candidate claims had a lease but no run-level fenced completion.
- **Files changed:** `app/modules/catalogue_ingestion/models.py`,
  `repository.py`, `service.py`, `routes.py`, `schemas.py`,
  `app/core/config.py`, `app/cli/process_catalogue_ingestion_runs.py`,
  `alembic/versions/20260824_0045_catalogue_ingestion_run_queue.py`,
  `tests/test_catalogue_ingestion_queue.py`,
  `tests/test_catalogue_ingestion_postgres.py`, and adjusted existing direct
  rerun tests in `tests/test_catalogue_ingestion.py`.
- **Migration:** additive revision `20260824_0045`; adds run idempotency,
  stage, bounded attempts, retry/error state, claim timestamps/token and dead
  letter timestamp. Existing runs are backfilled with unique `legacy:<id>`
  idempotency keys. Downgrade was exercised on SQLite by the migration suite.
- **Implementation details:**
  - `POST /runs/url` validates and persists only; legacy `process_now` accepts
    only `false` and cannot trigger synchronous work.
  - Direct requests use a caller key or a deterministic key over canonical URL
    bundle and immutable request options; repeat enqueue returns the same run.
  - Queue claims use `FOR UPDATE SKIP LOCKED`, bounded leases and a fresh opaque
    token. Complete, budget-exhausted and failure transitions check that token.
  - Transient failures reschedule with bounded delay; permanent/retry-exhausted
    runs become `dead_letter`. A new worker CLI claims one run at a time, so it
    cannot let self-claimed later leases expire behind a long earlier run.
  - Admin status is available through `GET /admin/catalogue-ingestion/runs/{id}`.
- **Security/trust invariants:** no acquisition code path was loosened; the
  worker continues to use `SafeSourceFetcher` through existing service paths.
  Queue completion does not publish or approve a scholarship. Lease loss fails
  closed instead of allowing stale terminal state overwrite.
- **Tests added:** SQLite tests cover no-acquisition enqueue, idempotency,
  expired lease reclamation, stale completion fencing, and transient
  retry/dead-letter. The migration suite now upgrades the immediate prior
  revision (`20260823_0044`) with a persisted legacy run, verifies its
  `legacy:<id>` idempotency backfill and queue columns/index, then downgrades
  again. PostgreSQL tests add run lease/fencing coverage beside the existing
  `SKIP LOCKED` test.
- **Commands and results:**
  - `uv --cache-dir .uv-cache run python -m pytest -q --basetemp .pytest-tmp/ingestion-final-2 tests/test_catalogue_ingestion_queue.py tests/test_catalogue_ingestion.py tests/test_catalogue_source_snapshot_ledger.py tests/test_complete_acquisition_contract.py` — **88 passed**.
  - `uv --cache-dir .uv-cache run python -m pytest -q --basetemp .pytest-tmp/migrations-final tests/test_migrations.py` — **10 passed**.
  - `uv --cache-dir .uv-cache run python -m pytest -q --basetemp .pytest-tmp/p0b-migration-queue tests/test_migrations.py::test_catalogue_run_queue_migration_backfills_prior_runs_and_rolls_back` — **1 passed**.
  - `uv --cache-dir .uv-cache run python -m pytest -q --basetemp .pytest-tmp/p0b-queue tests/test_catalogue_ingestion_queue.py tests/test_catalogue_source_snapshot_ledger.py tests/test_complete_acquisition_contract.py` — **14 passed**.
  - `uv --cache-dir .uv-cache run python -m pytest -q --basetemp .pytest-tmp/postgres tests/test_catalogue_ingestion_postgres.py` — **3 skipped**; `TEST_POSTGRES_URL` is not configured.
  - Targeted Ruff lint passed. Targeted Ruff format check passed after formatting
    changed source/tests. Whole-repository format remains baseline-failing only
    on unrelated committed profile files recorded above.
  - A combined follow-up suite reached 91 tests before the local command bridge
    stopped at 30 seconds without a completion summary; it is not counted as a
    pass. The focused bounded runs above have definitive summaries.
- **Known limitations:** no local PostgreSQL/Redis/browser service is available;
  the PostgreSQL fencing test is present but not executed. The worker only
  renews at candidate boundaries; a production worker must retain a lease
  greater than its bounded external operation duration until heartbeat support
  is added.
- **Rollback:** stop `process_catalogue_ingestion_runs` consumers, wait for
  leases to expire, and deploy the prior worker/API image. The migration is
  additive; review-only candidates and immutable artifacts remain intact.
- **Next gate:** durable direct-URL job enqueue, idempotency, leases, fencing,
  retry and dead-letter lifecycle with PostgreSQL concurrency evidence, then
  secure Crawlee static parity (P0-C).
