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
| `https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/` | `text/html` | `47bbe69dd7be9b50c309761de57e969f426a2bc2b3eb311cbdfc70599334922e` | `137dfc2083704676e2be913797f4fdc4f75aaed3ee77ca382bba2a7b9c0370cc` | 28,825 | 8,854 |
| `https://www.studyinjapan.go.jp/en/_mt/2026/04/01-2027_Research_Guidelines_E.pdf` | `application/pdf` | `41121b625bd81fafb422d3fad5dac97105fb7a4bdb9b3029a277428a63f94fde` | `ed069fe906b2779647c18066c5563332f092dd76297b66dade6487947ac6b94f` | 416,454 | 52,169 |
| `https://od.globaluni.ru/` | `text/html` | `8fb340d0aaeb0e831d757e5313bfc4608aa780e730b059281d65234ac0244c7e` | `ff1097998fde17133ee330ed7cfd12e25ed273cfa013c040ad40d8dbfb917c43` | 405,564 | 26,013 |

The first recorded values labelled raw hashes were the fetcher's normalized
evidence hashes, not byte hashes. The ledger now uses true raw-byte SHA-256
values. Captured public source bytes were not retained: the MEXT overview
explicitly states "Copyright © JASSO. All rights reserved" and no reusable
license was established for the Open Doors capture. Raw fixture retention
therefore requires legal/reviewer approval. Reviewed expected records and the
protected evaluation remain outstanding, so protected MEXT/Open Doors gates are
**not executed** and must not be reported as passing.

## P0-A — contract and fixture freeze

- **Status:** source snapshot identity is complete; raw-fixture retention and
  protected-fixture execution remain blocked on licensing/reviewer approval,
  reviewed expected outcomes and evaluation assertions.
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
- **Known limitation:** raw source bytes cannot be committed without a reviewed
  reuse basis; reviewed expected canonical outcomes and executable protected
  evaluation are also absent. MEXT/Open Doors protected gates therefore remain
  blocked and are not equivalent to the snapshot-ledger tests.
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

## P0-C — secure Crawlee static bridge

- **Status:** local static-bridge and safe-fetcher parity tests pass; browser
  acquisition remains out of scope and disabled.
- **Objective:** make Crawlee provide bounded scheduling without allowing its
  networking, robots handling, redirects, or retries to bypass
  `SafeSourceFetcher`.
- **Behavior before:** `CrawleeStaticEvidenceAcquirer` only relabelled a direct
  `LegacySafeEvidenceAcquirer` call. It imported Crawlee to detect an optional
  installation but did not use Crawlee orchestration. The service had no
  settings-gated way to use the adapter for a static request.
- **Files changed:** `app/modules/catalogue_ingestion/crawlee_static_acquirer.py`,
  `app/modules/catalogue_ingestion/service.py`, `app/core/config.py`, and
  `tests/test_crawlee_static_acquirer.py`.
- **Implementation:** the opt-in adapter now creates a single-concurrency
  Crawlee `BasicCrawler` request and runs its handler through
  `LegacySafeEvidenceAcquirer`. The handler does not use Crawlee's
  `context.send_request`; every actual source request therefore remains the
  injected `SafeSourceFetcher` boundary. Crawlee robots handling and retries
  are disabled because those decisions already belong to the safe fetcher.
  Crawlee uses a temporary per-acquisition storage directory, so it cannot
  write queue/state files into the repository or become a second durable state
  owner. Each scheduler request also receives a fresh key: an experiment
  reproduced Crawlee's process-shared queue suppressing a previously handled
  identical URL, which would otherwise return no result on a durable-job retry.
  Artifact and extraction cache compatibility—not Crawlee queue identity—
  continues to own content idempotency.
  `catalogue_crawlee_static_enabled` defaults false and wires only non-crawl
  static requests through the adapter when explicitly enabled.
- **Security/trust invariants:** HTTPS, SSRF, private/loopback/link-local and
  metadata rejection, DNS/peer validation, redirect validation, robots, MIME,
  and byte limits remain in `SafeSourceFetcher`. The bridge is single
  concurrency and fails closed from an existing async event loop. It does not
  enable browser, document, OCR, model-selected URL, graph approval, or
  publication paths.
- **Tests added:** actual Crawlee scheduling calls the injected safe fetcher
  exactly once; an `ssrf_private_address` rejection is returned unchanged; the
  service opt-in selects the Crawlee bridge. Existing acquisition-session and
  source-monitor tests provide legacy/security parity coverage.
- **Commands and results:**
  - `uv --cache-dir .uv-cache sync --frozen --extra crawlee` initially failed
    closed with sandbox socket error `10013` while fetching a locked package;
    the approved bounded retry installed Crawlee 1.9.2 without editing
    `uv.lock`. Development dependencies were then restored with
    `uv --cache-dir .uv-cache sync --frozen --extra dev --extra crawlee`.
  - `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0c-final-final tests/test_crawlee_static_acquirer.py tests/test_safe_multi_url_session.py tests/test_source_monitor.py tests/test_catalogue_ingestion_queue.py` — **33 passed, 2 skipped, 2 warnings**. The two skips are intentional tests for the opposite, no-Crawlee-installed condition; the second warning is a local pytest cache permission issue.
  - `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0c-storage tests/test_crawlee_static_acquirer.py` — **5 passed, 2 skipped, 2 warnings**; `Test-Path storage` returned `False`, proving the bridge no longer leaves Crawlee state in the repository.
  - Targeted Ruff lint and formatting checks passed; `git diff --check` passed.
- **Metrics/cost:** one Crawlee scheduler request per opted-in static source;
  one safe-fetcher request; no model call, graph write, approval, or publication
  change. The adapter is disabled by default, so current production call/cost
  behavior is unchanged.
- **Known limitations:** the durable database queue owns cross-process resume;
  this bridge deliberately does not use Crawlee persistent request storage.
  No local PostgreSQL, Redis, browser worker, or protected raw fixture evidence
  is available. This P0-C evidence does not constitute browser/OCR readiness.
- **Rollback:** set `APP_CATALOGUE_CRAWLEE_STATIC_ENABLED=false` (the default)
  and deploy the prior worker/API image. No schema or artifact migration is
  introduced by this slice.
- **Next gate:** deterministic, versioned canonical evidence blocks (P0-D).

## P0-D — canonical evidence blocks

- **Status:** SQLite unit and migration coverage pass; PostgreSQL migration
  execution remains environment-blocked.
- **Objective:** turn immutable normalized source artifacts into deterministic,
  versioned, exact-offset citation units without trusting model-authored
  offsets.
- **Behavior before:** `CatalogueSourceArtifact` stored immutable normalized
  text, and claim validation checked spans against the full artifact, but no
  canonical block identity or locator was persisted.
- **Files changed:** `app/modules/catalogue_ingestion/evidence_blocks.py`,
  `models.py`, `service.py`,
  `alembic/versions/20260824_0046_catalogue_evidence_blocks.py`,
  `tests/test_catalogue_evidence_blocks.py`, and `tests/test_migrations.py`.
- **Migration:** additive revision `20260824_0046` creates
  `catalogue_evidence_blocks`, with immutable artifact foreign key, block
  identity/version/index, exact normalized-text offsets, verbatim block text,
  JSON locator, uniqueness constraints and offset index. Downgrade removes only
  the additive table.
- **Implementation:** `evidence-blocks.v1` preserves the artifact text byte for
  byte at the Python-character offset layer. It preferentially splits at a
  paragraph, line, or space boundary before 1,200 characters, otherwise uses a
  hard deterministic boundary. Each ID hashes version, index, offsets and block
  text. New artifacts are flushed before blocks are generated; reused immutable
  artifacts receive the same derived blocks if a prior deployment has not yet
  generated them. No artifact is modified.
- **Security/trust invariants:** blocks are derived only from existing normalized
  artifact text; no model, crawler, browser, or remote document processor
  chooses boundaries or writes citations. Artifact and block update/delete ORM
  guards remain fail-closed. This adds no approval or publication path.
- **Tests added:** repeated canonicalization yields identical IDs and offsets;
  concatenated block text preserves all source whitespace; migration upgrade
  from `20260824_0045` and downgrade back are asserted.
- **Commands and results:**
  - `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0d-final tests/test_catalogue_evidence_blocks.py tests/test_catalogue_ingestion.py tests/test_migrations.py::test_catalogue_evidence_block_migration_is_additive_and_rolls_back` — **77 passed, 2 warnings**. Warnings are the existing FastAPI/Starlette deprecation and local pytest cache permission warning.
  - `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0d-migration tests/test_migrations.py::test_catalogue_evidence_block_migration_is_additive_and_rolls_back` — **1 passed, 2 warnings**.
  - Targeted Ruff lint/format checks and `git diff --check` passed.
- **Metrics/cost:** deterministic local segmentation only; zero network and zero
  model calls. The default 1,200-character block bound limits downstream
  evidence packet size while preserving offsets.
- **Known limitations:** PDF layout-aware conversion/OCR and block-aware model
  routing remain later slices. Existing persisted artifacts acquire blocks when
  reused; a dedicated offline backfill command and PostgreSQL migration run are
  still required before a production rollout.
- **Rollback:** deploy the prior image; no existing artifact is changed. If
  repository policy requires schema rollback, downgrade `20260824_0046` after
  stopping workers that write new blocks.
- **Next gate:** layout-aware document conversion and controlled OCR (P0-E).

## P0-E — layout-aware document conversion and controlled OCR

- **Status:** unit/integration-boundary coverage is green; real Docling cold-start conversion is blocked pending a production-style image with reviewed offline models. This is not a protected-fixture or production readiness pass.
- **Baseline commit:** `4fa4782`.
- **Objective:** replace catalogue PDF's layout-flattening extraction path, when explicitly enabled, with bounded Docling conversion that preserves Markdown reading order and tables; permit OCR only after a measured deterministic-text insufficiency.
- **Behavior before:** `SafeSourceFetcher.normalize_source_payload()` used `pypdf` and whitespace collapse for every PDF. It had no layout/table representation, no parser-version propagation, no child-process timeout, no content-sniff conversion policy, and no OCR ladder.
- **Files changed:** `pyproject.toml`, `uv.lock`, `app/core/config.py`, `app/modules/catalogue_ingestion/document_conversion.py`, `document_conversion_worker.py`, `service.py`, `evidence_acquirer.py`, `crawlee_static_acquirer.py`, `app/modules/opportunities/source_monitor.py`, `tests/test_document_conversion.py`, `tests/test_evidence_acquirer.py`, and `tests/test_catalogue_ingestion.py`.
- **Migrations:** none. The parser version travels with each newly acquired artifact; immutable existing artifacts are not rewritten.
- **Implementation details:**
  - `document-conversion` is a pinned optional extra (`docling>=2,<3`); the resolved lock selects Docling `2.121.0`. The lock update intentionally includes the pre-existing Crawlee 1.9.2 entries because that user change exactly matches the already-committed Crawlee extra, then adds the Docling graph. It is now required for reproducible optional-extra installation.
  - `SafeSourceFetcher` remains the only networking boundary. It first applies URL, redirect, DNS/IP, peer-address, robots, MIME, and byte controls. Only then may a catalogue-injected payload normalizer receive admitted PDF bytes. Source-monitor behavior retains the legacy normalizer.
  - The feature gate `catalogue_document_intelligence_enabled` remains false by default. It creates a `LayoutAwareDocumentConverter` with byte, page, runtime, output, and sufficiency bounds. OCR has a separate false-by-default gate.
  - PDFs must match the declared MIME and `%PDF-` signature, parse strictly, be unencrypted, fit page/byte limits, and then enter a short-lived Docling child process. The child applies Docling table structure extraction and exports Markdown; it receives no application configuration/secrets, has an application-side timeout, and repeats Docling file/page limits. Hugging Face/Transformers are forced offline so production must use a reviewed pre-baked model image; arbitrary model downloads are disallowed.
  - Text sufficiency is measured from non-whitespace/alphanumeric content. The deterministic no-OCR conversion runs first. OCR occurs only if it fails this measurement and the independent OCR gate is explicitly enabled. Every failure has a stable code; no pypdf/remote/model fallback is used for a failed layout conversion.
  - `FetchedSource` and `AcquiredArtifact` now persist parser-version lineage. Crawlee's scheduler label composes with, rather than overwrites, the underlying parser version.
- **Security/trust invariants:** no crawler, browser, Docling, OCR, or model code chooses a URL or bypasses `SafeSourceFetcher`; source text remains the sole evidence input; content is not published, approved, or graph-written by this slice. The process boundary is application-side quarantine, but deployment still needs the dedicated restricted-egress/sandboxed document-worker image before this gate can be considered operationally complete.
- **Tests added:** layout Markdown/table preservation, deterministic sufficiency thresholds, OCR only-after-failure, OCR failure, MIME/magic/malformed/encrypted/oversized rejection, PDF-only normalizer selection, feature-gate selection, parser lineage, and worker secret-removal/offline-model environment checks.
- **Commands and results:**
  - `uv --cache-dir .uv-cache lock` initially failed closed because sandbox networking was blocked; the approved retry completed and resolved 210 locked packages.
  - `uv --cache-dir .uv-cache sync --extra dev --extra crawlee` completed after the lock required the newly pinned `websockets==16.1.1` wheel.
  - `uv --cache-dir .uv-cache run ruff check ...` and `ruff format --check ...` for all P0-E source/test files passed after formatting.
  - `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0e-focused tests/test_document_conversion.py tests/test_evidence_acquirer.py tests/test_catalogue_ingestion.py tests/test_source_monitor.py` — **108 passed, 2 warnings** (existing FastAPI/Starlette deprecation and local pytest-cache access warning).
  - The optional Docling extra installed locally. Source inspection confirmed the pinned API exposes `PdfPipelineOptions.do_ocr`, `do_table_structure`, `PdfFormatOption`, and `DocumentConverter.convert(..., max_num_pages, max_file_size)`.
  - A real blank-PDF child-process experiment with a five-second cap failed closed with `document_conversion_timeout`; it left no child process. It does not demonstrate successful Docling conversion because this workspace has no pre-baked reviewed Docling model artifacts. That failure is deliberately not reported as a converter pass.
- **Performance/cost:** default production behavior is unchanged because the feature gate is false. When enabled, one bounded child process performs one non-OCR pass and at most one OCR pass; there are zero model-provider calls and zero runtime model downloads. Cold-start model availability is currently a blocking operational dependency.
- **Skipped/environment-blocked:** no real successful Docling PDF conversion, complex-table benchmark, OCR benchmark, MEXT/Open Doors raw protected fixture, PostgreSQL, Redis, or browser-worker execution is available locally. The Document Lab is not reused or enabled.
- **Known limitations:** the process boundary cannot itself prove OS/container sandboxing, CPU/memory cgroups, or network egress denial; those require deployment manifests and a pre-baked model image. Current artifact storage lacks a dedicated layout sidecar, so Markdown is persisted as the normalized immutable text and canonical blocks derive from it. A real layout fixture evaluation is required before enabling this feature in staging.
- **Rollback:** keep `APP_CATALOGUE_DOCUMENT_INTELLIGENCE_ENABLED=false` and `APP_CATALOGUE_DOCUMENT_OCR_ENABLED=false` (both defaults), then deploy the prior image. No schema rollback or artifact mutation is required.
- **Next gate:** provision the isolated, offline-model document-worker image and execute real complex-PDF/MEXT fixture conversion; then P0-F source-role/cycle classification and objective routing.

### P0-E follow-up — offline artifact proof and raw fixture capture

- **Status:** the local offline conversion proof is green; deployment-image and
  restricted-egress/container-runtime evidence remain open.
- **Objective:** prove a real complex MEXT PDF conversion with a reviewed,
  pinned Docling artifact bundle; prevent the conversion child from inheriting
  a mutable host model cache; verify whether MEXT/Open Doors bytes can safely
  be retained for later protected evaluation.
- **Files changed:** `app/core/config.py`,
  `app/modules/catalogue_ingestion/document_conversion.py`,
  `document_conversion_worker.py`, `service.py`,
  `docker/docling-worker.Dockerfile`, `docker/docling-artifacts.lock.json`,
  `scripts/verify_docling_artifacts.py`, `compose.yaml`, `.dockerignore`,
  `.gitignore`, source fixture ledger/test, and
  `tests/test_document_conversion.py`.
- **Implementation:** conversion children now receive only a configured
  `DOCLING_ARTIFACTS_PATH`/home path and offline flags. They reject a missing
  artifact directory before Docling initialization. The new dedicated image
  downloads layout, TableFormer and RapidOCR models at build time, verifies
  the 26-file, 765,212,139-byte artifact bundle against the recorded aggregate
  SHA-256 `2eb473093fb3b99176cdb10b485707400b34e22c5414021f1ad5c3e4056c81b6`,
  and has no database, Redis or application-secret environment. The Compose
  profile specifies no network, read-only root filesystem, dropped Linux
  capabilities, no-new-privileges, 2 CPU, 4 GiB memory and 256 PID limits.
- **Fixture capture:** bounded `SafeSourceFetcher` calls temporarily acquired
  the 28,825 byte MEXT overview HTML, 416,454 byte MEXT 2027 Research
  Guidelines PDF and 405,564 byte Open Doors homepage, yielding the true raw
  hashes in the ledger. The 850,843 bytes were removed before commit after the
  MEXT page's explicit all-rights-reserved notice and the absence of a reviewed
  Open Doors reuse license. The ledger test continues to prevent a snapshot
  hash from being misrepresented as a protected raw fixture.
- **Real conversion experiment:** with Docling `2.121.0`, forced
  `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, the MEXT PDF converted in
  **40.672 seconds**: 11 pages, 56,293 Markdown characters, 13 table lines and
  16 ordered-list lines. The preserved seven-column document table includes
  document name, one-original, two-copy and remarks cells. A deliberately
  blank permitted PDF entered the real OCR second pass and failed closed after
  **35.140 seconds** as `document_ocr_text_insufficient`; it did not fall back
  to flattened text or a remote service.
- **Commands and results:**
  - `uv --cache-dir .uv-cache run docling-tools models download layout tableformer rapidocr --output-dir .docling-models --quiet` — completed; staging artifacts are ignored and never committed.
  - `uv --cache-dir .uv-cache run python scripts/verify_docling_artifacts.py --model-dir .docling-models --lock docker/docling-artifacts.lock.json` — passed.
  - `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0e-fixtures-green tests/test_document_conversion.py tests/test_catalogue_source_snapshot_ledger.py tests/test_catalogue_ingestion.py tests/test_evidence_acquirer.py tests/test_source_monitor.py` — **111 passed, 2 warnings** before the licensing-driven fixture retention rollback. Rerun is required before counting the final fixture state as green.
  - `docker compose config -q` — environment-blocked: `docker` is not installed in this workspace, so the image build, Compose validation, cgroup enforcement and egress-deny behavior are not claimed as executed.
- **Security/trust invariants:** all source captures passed through
  `SafeSourceFetcher`; the child receives no application configuration or
  secrets; runtime model download remains forbidden; no browser, model or
  converter chooses a URL; no approval/publication path was added.
- **Known limitations:** licensed/reviewer-approved protected raw fixtures and
  expected protected records, real OCR-success quality benchmark, canonical
  layout-region/table-coordinate blocks, Docker image build and runtime
  isolation proof, PostgreSQL/Redis and browser-worker execution remain open.
  The P0-E operational/deployment gate is therefore incomplete despite the
  local conversion proof.
- **Rollback:** keep the document-intelligence and OCR feature gates false;
  discard the ignored local `.docling-models` staging directory; deploy the
  prior image. Do not retain captured raw source bytes without a reviewed reuse
  basis.
- **Next gate:** rerun the corrected fixture/P0-E suites, then implement P0-F
  source-role/cycle classification and routed objective work without weakening
  the open deployment gate.

## P0-F — source-role, cycle, and objective routing

- **Status:** deterministic classifier/routing contract and opt-in durable
  extraction-loop wiring implemented; full routed-run and PostgreSQL evidence
  remain pending.
- **Objective:** replace the unsafe default assumption that every official page
  can answer every one of the twelve extraction objectives.
- **Files changed:** `source_routing.py`, `models.py`, `repository.py`,
  `service.py`, `app/core/config.py`, additive migration
  `20260824_0047_catalogue_source_routing.py`, and focused router/migration
  tests.
- **Implementation:** `source-router.v1` identifies the required role set,
  classifies current/upcoming/historical/evergreen/ambiguous cycles from
  deterministic signals, and maps roles to only applicable objectives. Unknown
  and conflicting roles route no objectives and require manual review; mixed
  cycle years are ambiguous and also route no objectives. Confidence is
  diagnostic only.
- **Tests added:** funding pages route only funding; document checklists exclude
  funding/programme work; unknown/conflicting roles fail closed; mixed years
  stop routing.
- **Commands and results:**
  `uv --cache-dir .uv-cache run ruff check app/modules/catalogue_ingestion/source_routing.py tests/test_source_routing.py`,
  `ruff format --check ...`, and
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0f-router-green tests/test_source_routing.py`
  — **4 passed, 2 warnings**. Warnings are existing Starlette deprecation and
  local pytest-cache access warning.
- **Security/trust invariants:** lexical signals are explainable diagnostics;
  source text never authorizes a model call outside the routing matrix; unknown
  is not silently upgraded to overview; no automatic publication is added.
- **Persistence/wiring:** each enabled run stores one immutable-artifact and
  classifier-version keyed decision containing role, cycle, deterministic
  signals, diagnostic confidence, ambiguity/manual-review state and applicable
  objectives. The extraction loop reuses that stored decision; ambiguous or
  unknown decisions record a manual-review reason and make no model call.
  `catalogue_source_routing_enabled` defaults false pending production-shaped
  evidence, so current behavior is unchanged until an operator enables it.
- **Additional tests:** additive migration upgrade from `0046`, schema/index
  inspection and downgrade back to `0046`.
- **Additional commands/results:**
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0f-routing-final tests/test_source_routing.py tests/test_migrations.py::test_catalogue_source_routing_migration_is_additive_and_rolls_back`
  — **5 passed, 2 warnings**.
- **Known limitations:** the router currently receives all objectives as
  unresolved because P0-G bundle completeness has not yet supplied a scoped
  unresolved set. Full routed-run, attempt reuse, budget-resume and PostgreSQL
  concurrency evidence are still required; this is not a P0-F completion claim.
- **Rollback:** keep `APP_CATALOGUE_SOURCE_ROUTING_ENABLED=false` (default),
  stop workers using the new path and downgrade `0047` only after they stop.
- **Next gate:** supply scoped unresolved objectives, add routed service tests,
  then demonstrate cache/budget/resume behavior and PostgreSQL execution.

### P0-F follow-up — fail-closed routed service regression

- **Status:** the opt-in routed service path now has an end-to-end regression
  proving that conflicting source roles persist a decision, make no model call,
  and retain the candidate in manual review.
- **Files changed:** `service.py` and `tests/test_catalogue_ingestion.py`.
- **Implementation:** when a persisted or newly classified decision requires
  manual review, `_process_direct_claims` returns immediately after recording
  the manual-review state. This prevents its later normal extraction finalizer
  from overwriting `needs_review` with an extraction/validation status.
- **Test added:** an official direct URL whose immutable artifact carries both
  funding and document-checklist signals produces one `unknown` routing
  decision with `conflicting_role_signals`, zero `FakeClaimProvider` calls,
  and a `needs_review` candidate.
- **Commands and results:**
  `uv --cache-dir .uv-cache run pytest tests/test_catalogue_ingestion.py -k source_routing_blocks_ambiguous_artifact_without_model_calls -q`
  — **1 passed, 2 warnings**. Warnings are the existing Starlette deprecation
  and local pytest-cache access warning.
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/p0f-routed-service tests/test_catalogue_ingestion.py tests/test_source_routing.py tests/test_migrations.py::test_catalogue_source_routing_migration_is_additive_and_rolls_back`
  — **81 passed, 2 warnings**. The same two known warnings were emitted.
  Targeted Ruff check/format checks and `git diff --check` passed after the
  formatter normalized line endings in the two touched Python files.
- **Security/trust invariant:** an ambiguous source cannot fall through to
  broad extraction or replace the manual-review status; no publication path is
  involved.

### P0-F follow-up — scoped unresolved objective routing

- **Status:** enabled source routing now carries objective completion state
  through an ordered direct-source bundle rather than independently invoking
  every role-eligible objective for every source.
- **Files changed:** `service.py` and `tests/test_catalogue_ingestion.py`.
- **Implementation:** all claim objectives start unresolved for an extraction
  bundle. A routed source receives only objectives it is allowed to answer and
  that remain unresolved. A `complete` or `not_applicable` result removes that
  objective; `partial` and `not_stated` results leave it available for a later
  relevant source. The existing final completeness validation remains the
  authoritative review gate for objectives no source has completed.
- **Test added:** two official funding sources in one bundle persist two
  funding decisions but make one model call and create one extraction attempt,
  because the first source reports funding complete.
- **Commands and results:**
  `uv --cache-dir .uv-cache run pytest tests/test_catalogue_ingestion.py -k "source_routing_blocks_ambiguous_artifact_without_model_calls or source_routing_only_retries_objectives_left_unresolved_in_bundle" -q`
  — **2 passed, 2 warnings**. Targeted Ruff checks, formatting, and
  `git diff --check` passed. The final focused service/router/migration command
  using `.pytest-tmp/p0f-unresolved-objectives-final` completed with **82
  passed, 1 warning** (the existing Starlette deprecation warning).
- **Security/trust invariant:** only source-role-permitted objectives can
  consume model budget; an incomplete source cannot claim completion or block
  a later relevant source from addressing the same objective.

### P0-F follow-up — cross-cycle merge prevention

- **Status:** enabled routing now prevents a direct-source bundle from merging
  explicit facts drawn from different cycle identities.
- **Baseline commit:** `b473df6`.
- **Files changed:** `source_routing.py`, `service.py`,
  `tests/test_source_routing.py`, and `tests/test_catalogue_ingestion.py`.
- **Implementation:** source decisions retain deterministic `year:<year>`
  signals. The routed extraction loop accepts one explicit non-evergreen cycle
  identity per bundle and immediately sends the candidate to manual review when
  a later source has a different cycle state or year. An evergreen deadline
  notice is also manual-review-only (`deadline_cycle_unresolved`), so it cannot
  establish a universal current-cycle deadline. Evergreen non-deadline sources
  retain their existing role-limited behavior.
- **Tests added:** an evergreen deadline receives no routeable objective; a
  current funding source followed by an otherwise compatible historical funding
  source produces one model call, no proposed payload, persisted `current` and
  `historical` decisions, and a `needs_review` candidate.
- **Commands and results:**
  `uv --cache-dir .uv-cache run pytest tests/test_source_routing.py tests/test_catalogue_ingestion.py -k "evergreen_deadline_source_requires_cycle_resolution or source_routing_blocks_current_and_historical_cycle_merge" -q`
  — **2 passed, 2 warnings**. Targeted Ruff checks, formatting and
  `git diff --check` passed. The focused router/service/migration suite using
  `.pytest-tmp/p0f-cycle-current` completed with **84 passed, 2 warnings**
  (existing Starlette deprecation and local pytest-cache access warnings).
- **Security/trust invariant:** claims from a prior/current/upcoming cycle are
  never combined into one resolved proposal merely because the source domain
  is official; ambiguous/unresolved deadline cycle facts remain review work.

## R-01 — atomic beta invitation expiry

- **Status:** local regression coverage is green; PostgreSQL concurrency proof
  remains required for release evidence.
- **Baseline commit:** `97cb69f`.
- **Objective:** make bulk invitation expiry apply the same safety transition
  as verification-time expiry: expire the invitation and deactivate its
  reserved account in one locked, idempotent transaction.
- **Files changed:** `app/modules/beta/service.py` and `tests/test_beta.py`.
- **Behavior before:** `_expire_due()` changed only pending invitation status,
  so a reserved user could remain active after a bulk-expiry pass. The
  verification-time branch separately deactivated the user, leaving two
  inconsistent implementations.
- **Implementation:** `_expire_invitation()` is now the single idempotent
  transition. Bulk expiry selects due pending invitations with row locking,
  deactivates any reserved user, records one audit event, and commits once.
  Email verification uses the same helper in its surrounding transaction.
- **Tests added:** an invitation is reserved, forced past expiry, processed by
  two bulk-expiry passes, and verified as expired with its user inactive and
  exactly one expiry audit record.
- **Commands and results:**
  `uv --cache-dir .uv-cache run pytest tests/test_beta.py -q` — **8 passed, 2
  warnings**. Targeted Ruff checks, formatting and `git diff --check` passed.
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp .pytest-tmp/r01-beta tests/test_beta.py tests/test_auth.py`
  — **27 passed, 2 warnings** (existing Starlette deprecation and local
  pytest-cache access warnings).
- **Security/trust invariant:** an expired pending invitation cannot retain an
  active reserved beta account, and retrying expiry cannot generate duplicate
  state transitions or audit records.
- **Known limitation:** SQLite validates the idempotent state transition; the
  row-lock/concurrent-expiry behavior still requires real PostgreSQL execution.
- **Rollback:** deploy the prior service image. This is an in-place state
  correction with no schema migration; already-expired reservations can be
  safely reconciled by rerunning the bounded expiry operation.

## R-02 — atomic profile optimistic locking

- **Status:** conditional-update regression coverage is green; real
  PostgreSQL concurrent-session execution remains required for release proof.
- **Baseline commit:** `4d48e4d`.
- **Objective:** make profile updates database-enforced compare-and-swap
  operations so two writers using one expected version cannot both succeed.
- **Files changed:** `app/modules/profiles/repository.py`,
  `app/modules/profiles/service.py`, and `tests/test_profiles.py`.
- **Behavior before:** the service loaded a profile, compared `version` in
  Python, mutated the ORM row and committed. Two sessions could both observe
  the old version and independently commit.
- **Implementation:** `update_if_version()` issues one `UPDATE` constrained by
  `user_id` and `expected_version`, increments the version in the statement,
  and returns the updated ORM row. The service maps a no-row result to the
  existing `profile_version_conflict` 409 response. Payload normalization and
  create behavior remain unchanged.
- **Tests added:** two direct repository writes using expected version 1 allow
  only the first write; it returns version 2 and the second writes no row.
- **Commands and results:**
  `uv --cache-dir .uv-cache run pytest tests/test_profiles.py -q` — **10
  passed, 2 warnings**. Targeted Ruff checks, formatting and `git diff --check`
  passed. `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/r02-profiles tests/test_profiles.py tests/test_matching.py` —
  **30 passed, 2 warnings** (existing Starlette deprecation and local
  pytest-cache access warnings).
- **Security/trust invariant:** a stale version cannot overwrite a newer
  profile update; no handler accepts a successful stale write merely because
  the process loaded an old ORM object.
- **Known limitation:** the deterministic predicate is database-portable, but
  the required two-real-PostgreSQL-session 409 experiment is environment
  blocked until `TEST_POSTGRES_URL` is configured.
- **Rollback:** deploy the prior service image; no migration or stored-data
  rewrite is required.

## R-08 — public community member-ID moderation

- **Status:** local API regression coverage is green.
- **Baseline commit:** `1c21696`.
- **Objective:** make moderation use the public community member identifier
  exposed in queue/feed responses, never an internal user primary key.
- **Files changed:** `app/modules/community/schemas.py`,
  `app/modules/community/service.py`, and `tests/test_community.py`.
- **Behavior before:** suspend/reinstate requests required `user_id`, and the
  service called `session.get(CommunityPreference, user_id)`. The API exposes
  `CommunityPreference.public_id`, making the visible identifier unusable and
  encouraging internal-ID exposure.
- **Implementation:** the request field is now `member_id`; suspend/reinstate
  resolve it against `CommunityPreference.public_id`. Moderation/audit target
  records use the public member ID and a `community_member` target type.
- **Tests added:** an administrator suspends and reinstates a participating
  author using the public author ID returned from a post; publishing is denied
  while suspended.
- **Commands and results:** `uv --cache-dir .uv-cache run pytest
  tests/test_community.py -q` — **7 passed, 2 warnings**. Targeted Ruff checks,
  formatting and `git diff --check` passed. `uv --cache-dir .uv-cache run
  python -m pytest -ra --basetemp .pytest-tmp/r08-community
  tests/test_community.py tests/test_auth.py` — **26 passed, 2 warnings**
  (existing Starlette deprecation and local pytest-cache access warnings).
- **Security/trust invariant:** privileged moderation no longer requires or
  records an internal user identifier in its externally supplied target
  contract; existing admin step-up remains unchanged.
- **Rollback:** deploy the prior service image. This intentionally changes the
  request contract; clients must use the public member ID exposed by community
  content before rollback/roll-forward.

## R-06 — atomic assistant quota reservation

- **Status:** local quota-admission and terminal-state coverage is green; the
  required real PostgreSQL competing-request execution is present but not run
  because `TEST_POSTGRES_URL` is not configured.
- **Baseline commit:** `c51d820`.
- **Objective:** reserve daily and monthly assistant capacity atomically before
  a request can reach the provider boundary.
- **Files changed:** `app/modules/assistant/models.py`,
  `app/modules/assistant/service.py`,
  `alembic/versions/20260824_0048_assistant_quota_reservations.py`,
  `tests/test_assistant.py`, `tests/test_assistant_quota_postgres.py`,
  `tests/test_migrations.py`, and `tests/test_postgres_tenant_isolation.py`.
- **Behavior before:** the service counted persisted answers, then later
  inserted an answer. Competing requests could both observe remaining capacity
  and begin provider work.
- **Implementation:** a durable per-user UTC daily/monthly counter is
  incremented with an `INSERT ... ON CONFLICT DO UPDATE ... WHERE` capacity
  predicate. Both counters and a reservation row commit together before the
  response path begins. The reservation becomes `consumed` only when its answer
  commits. Failures after an attempted provider invocation remain consumed;
  only failures proved to occur before invocation are marked `refunded` and
  decrement both counters. The additive migration backfills the active UTC
  daily/monthly counters from existing answers and applies PostgreSQL RLS to
  both new user-owned tables.
- **Tests added:** limit-one admission rejects a second request before its
  provider can run; provider failures consume their reservation; a local
  pre-provider failure refunds it; the migration upgrades and rolls back; and
  a PostgreSQL-marked two-session limit-one race test asserts exactly one
  admission.
- **Commands and results:** `uv --cache-dir .uv-cache run ruff check
  app/modules/assistant/models.py app/modules/assistant/service.py
  alembic/versions/20260824_0048_assistant_quota_reservations.py
  tests/test_assistant.py tests/test_assistant_quota_postgres.py
  tests/test_migrations.py tests/test_postgres_tenant_isolation.py` and the
  equivalent `ruff format --check` both passed. `uv --cache-dir .uv-cache run
  python -m pytest -ra --basetemp .pytest-tmp/r06-quota-final
  tests/test_assistant.py
  tests/test_migrations.py::test_assistant_quota_reservation_migration_is_additive_and_rolls_back
  tests/test_assistant_quota_postgres.py` — **16 passed, 1 skipped, 2
  warnings**. The skip is explicitly the PostgreSQL concurrency test awaiting
  `TEST_POSTGRES_URL`; the warnings were the existing Starlette deprecation
  and local pytest-cache access warning. A final clean-basetemp rerun of the
  same selection reported **16 passed, 1 skipped, 1 warning**.
- **Security/trust invariant:** quota rejection occurs before provider work;
  a provider failure cannot silently free capacity after a possibly billable
  attempt; RLS keeps reservation and counter state tenant-scoped.
- **Known limitation:** this is not PostgreSQL runtime evidence. The marked
  two-session test must pass against a disposable PostgreSQL service before RC
  acceptance. Current counters use UTC calendar daily/monthly windows; this
  behavior is explicit in the migration backfill and must remain aligned with
  published quota policy before release.
- **Rollback:** deploy the prior service image and downgrade migration
  `20260824_0048` only if no retained quota reservation data is needed. The
  migration is additive; existing answers remain untouched.

## R-07 — assistant answer, evidence, and feedback retention

- **Status:** local retention coverage is green; scheduled execution remains
  dependent on the existing `app.cli.run_retention` operational job being run
  in deployment.
- **Baseline commit:** `28d3d93`.
- **Objective:** ensure user prompts, rendered answers, evidence snapshots,
  citations, and feedback do not outlive their declared retention periods.
- **Implementation:** the existing retention job now deletes every assistant
  answer older than `assistant_audit_retention_days`, including saved answers.
  Database cascades remove its citations and feedback; the already-existing
  orphan-packet pass then removes its evidence packet. Conversation messages
  retain their shorter history policy, and standalone feedback retains its own
  expiry rule. No saved-workspace exception prolongs a private payload.
- **Test added:** an answer with a source-backed packet, citation, feedback,
  and saved-workspace flag is aged beyond the 30-day audit period. Retention
  removes the answer, packet, citation, and feedback even when the feedback's
  own expiry would otherwise be in the future.
- **Commands and results:** `uv --cache-dir .uv-cache run ruff check
  app/modules/assistant/service.py tests/test_assistant.py` passed. `uv
  --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/r07-retention-final tests/test_assistant.py` — **16 passed, 2
  warnings** (existing Starlette deprecation and local pytest-cache access).
- **Security/trust invariant:** a retained answer cannot indefinitely pin its
  evidence packet or feedback, and a workspace-save flag is never an implicit
  permanent-retention consent.
- **Known limitation:** code-level cleanup does not prove production scheduling;
  deployment still needs recurring `run_retention` execution and operational
  health evidence before RC acceptance.
- **Rollback:** deploy the prior service image. No migration is required; the
  cleanup is irreversible for records already purged.

## R-09 — fenced source-monitor completion

- **Status:** local fenced-completion coverage is green; real PostgreSQL
  concurrent-worker evidence remains required.
- **Baseline commit:** `09d0266`.
- **Implementation:** each monitor claim now receives an opaque token. A
  successful check locks and verifies that token before changing the hash,
  verification state, excerpts, audit record, next schedule, failure count, and
  lease fields; all changes commit together. Failure completion likewise only
  releases the matching token.
- **Test:** a stale token after a simulated reclaim cannot write a hash or
  verification record, nor clear the newer worker's lease.
- **Commands:** `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/source-monitor-fencing tests/test_source_monitor.py
  tests/test_migrations.py::test_source_monitor_fencing_migration_is_additive_and_rolls_back`
  — **20 passed, 2 warnings**. Targeted Ruff lint and formatting passed.
- **Known limitation:** SQLite does not prove concurrent PostgreSQL row-lock
  behavior; a two-session PostgreSQL fencing test remains an RC gate.

## R-04 — bounded Document Lab job leases

- **Status:** local reclaim and migration coverage is green; PostgreSQL
  competing-worker proof remains required.
- **Baseline:** `934ec87`.
- **Implementation:** preparation jobs now carry an opaque claim token and
  expiry. Expired jobs are requeued until their bounded attempt count is
  reached, then become terminal `document_job_lease_exhausted`; completion and
  failure updates are fenced on the active token so late workers cannot replace
  newer state.
- **Migration:** `20260824_0050_document_job_leases` is additive and reversible.
- **Evidence:** reclaim now also proves that a late failure carrying the prior
  token cannot overwrite a newer running claim. The focused reclaim/migration
  run completed **2 passed, 2 warnings**. The complete Document Lab suite was
  split because the local runner did not return a final summary within its
  per-process window: the intake/deletion group completed **12 passed, 10
  deselected, 1 warning in 15.23s**, and the retention/analysis group completed
  **10 passed, 12 deselected, 1 warning in 18.85s**. Targeted Ruff lint and
  formatting passed.
- **Known limitation:** real PostgreSQL lease-reclaim/fencing execution and
  production worker health evidence remain RC gates.

## R-03 — durable private Document Lab deletion

- **Status:** local durable deletion, retry, reconciliation, terminal state,
  and aggregate metric coverage is green; production object-store and
  PostgreSQL evidence remain required.
- **Baseline:** `39bf336`.
- **Implementation:** deletion requests now make an asset inaccessible and
  durably enqueue an idempotent job before any object-store call. Each job
  retains only opaque scoped storage keys while pending, has bounded attempts,
  lease/token fencing, retry scheduling, a terminal failure code, and safe
  aggregate status metrics. A successful job deletes private objects first,
  then atomically hard-deletes relational private data and clears its retained
  keys; the compact completed job remains for operator reconciliation. The
  existing preparation worker drains deletion work when no preparation job is
  queued. Expiry now enqueues deletion rather than performing synchronous I/O.
- **Migration:** `20260824_0051_document_deletion_jobs` is additive and
  reversible.
- **Security/trust:** a pending or terminally failed asset is immediately
  unavailable through asset, version, analysis, list, and export paths; no
  filename or document text is stored in the deletion job or emitted as a
  failure reason.
- **Tests:** a storage outage requeues then idempotently completes, with safe
  aggregate queued/retry/completed metrics; bounded repeated failures become
  terminal and reconciliation does not duplicate a job. Document Lab
  verification completed **12 passed, 10 deselected, 1
  warning in 19.29s**, **5 passed, 17 deselected, 1 warning in 9.73s**, and
  **5 passed, 17 deselected, 1 warning in 16.16s**. The deletion migration
  test completed **1 passed, 1 warning in 4.27s**. Targeted Ruff lint,
  formatting, and `git diff --check` passed.
- **Known limitation:** real PostgreSQL multi-worker fencing and a real
  production object-store outage/reconciliation exercise remain RC gates.

## R-05 — fail closed on Document Lab provider deadlines

- **Status:** local provider-boundary regression coverage is green; a real
  reviewed provider transport and production worker execution remain required.
- **Baseline:** `7e6bd0f`.
- **Implementation:** removed the `ThreadPoolExecutor` timeout fallback,
  because cancelling a Python future cannot stop an in-flight provider call.
  Document Lab now invokes only `analyse_with_deadline`, passing the bounded
  configured timeout, and rejects a provider that does not implement that
  boundary before its ordinary `analyse` method is called.
- **Security/trust:** private extracted text is no longer handed to an
  unbounded background thread. Provider adapters must enforce their own
  transport deadline; no fallback silently weakens that contract.
- **Tests:** a provider-reported deadline expiry remains a safe terminal
  failure; a provider missing the deadline method is never executed; the
  deadline argument reaches a compliant provider. Focused verification
  completed **3 passed, 20 deselected, 2 warnings in 4.94s** and the related
  analysis group completed **9 passed, 14 deselected, 1 warning in 21.67s**.
  Targeted Ruff lint, formatting, and `git diff --check` passed.
- **Known limitation:** this is a contract boundary, not proof that a future
  third-party adapter correctly configures its HTTP transport deadline;
  production adapter review and a killable isolated-worker proof remain RC
  gates.

### P0-E follow-up â€” terminate timed-out Docling process trees

- **Status:** local deadline enforcement is green; this does not close the
  dedicated-worker, restricted-egress, cgroup, offline-image, protected-fixture,
  or real OCR-success gates.
- **Baseline commit:** `99aba4f`.
- **Objective:** ensure an application-side catalogue document-conversion
  timeout cannot leave Docling helper processes consuming CPU after the parent
  worker has returned a terminal failure.
- **Files changed:** `app/modules/catalogue_ingestion/document_conversion.py`
  and `tests/test_document_conversion.py`.
- **Behavior before:** `subprocess.run(..., timeout=...)` only terminated its
  direct Python child. Docling can create native/model helper descendants, so a
  timeout did not provide a process-tree termination guarantee.
- **Implementation:** the converter now starts the child in a dedicated Windows
  process group or POSIX session. On timeout it recursively calls `taskkill
  /T` on Windows or `killpg` on POSIX, waits for termination, and falls back to
  a direct kill only when the group operation is unavailable. The sanitized,
  offline-only worker environment and stable `document_conversion_timeout`
  error remain unchanged.
- **Tests added:** a timed-out fake worker proves the Windows launch uses
  `CREATE_NEW_PROCESS_GROUP` and issues one recursive `taskkill /PID <pid> /T
  /F` before the stable timeout error is raised.
- **Commands and results:**
  `uv --cache-dir .uv-cache run ruff check
  app/modules/catalogue_ingestion/document_conversion.py
  tests/test_document_conversion.py` â€” passed;
  `uv --cache-dir .uv-cache run ruff format --check
  app/modules/catalogue_ingestion/document_conversion.py
  tests/test_document_conversion.py` â€” passed;
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/p0e-process-tree-doc-evidence-final
  tests/test_document_conversion.py tests/test_evidence_acquirer.py` â€” **17
  passed, 2 warnings in 4.62s**; `git diff --check` â€” passed.
- **Security/trust invariant:** the process tree still receives no application
  secrets, cannot select or fetch a URL, and remains subject to the existing
  file/page/byte/output limits. No model, approval, or publication behavior was
  changed.
- **Known limitations:** Windows `taskkill` and POSIX `killpg` behavior are
  mocked regression coverage, not a live child-tree experiment. Docker and
  Poppler are absent locally, so the reference Docling image, its cgroup/egress
  envelope, and visual blueprint review are not claimed as executed. Azure
  deployment still has no dedicated Docling job wired to the restricted image;
  `APP_CATALOGUE_DOCUMENT_INTELLIGENCE_ENABLED` remains false there.
- **Rollback:** deploy the prior image; no migration or stored artifact changes
  are involved. Keep the document-intelligence and OCR gates disabled.
- **Next gate:** provide the dedicated Azure document-worker transport and
  execute its image/runtime isolation evidence, then add protected approved
  MEXT/Open Doors evaluations and real PostgreSQL/Redis proof.

## P0-H follow-up â€” aggregate enabled-capability readiness

- **Status:** local fail-closed readiness contract is green; live dependency
  probes and deployment evidence remain required.
- **Baseline commit:** `c713325`.
- **Implementation:** `/health/ready` now evaluates a single aggregate
  dependency report. Redis is probed only when enabled. Scheduled catalogue
  ingestion requires a fresh worker record and zero dead-letter runs. Enabled
  Docling, browser, and Azure extraction are explicitly blocked until their
  dedicated runtime/provider probes exist. Production Document Lab is blocked
  until its object-storage runtime probe exists. Disabled capabilities do not
  affect readiness; non-production Document Lab retains its documented test
  policy. Authenticated operations health exposes the safe report without
  secrets.
- **Tests:** disabled capabilities remain outside the gate; enabling Docling
  without its dedicated transport returns `dedicated_worker_transport_unavailable`.
- **Commands and results:** targeted Ruff lint/format passed;
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/p0h-readiness-summary tests/test_operations.py tests/test_auth.py`
  â€” **30 passed, 2 warnings in 16.69s**; `git diff --check` passed.
- **Security/trust invariant:** readiness never exposes secrets and never marks
  an enabled high-risk dependency healthy merely because PostgreSQL responds.
  No feature flag, worker, publication, or deployment state changed.
- **Known limitations:** the blocked statuses are intentionally not runtime
  proof. Dedicated Azure Docling/browser worker transport, object storage and
  scanner probes, Azure extraction probe, migration-version verification, and
  real PostgreSQL/Redis execution remain RC gates.
- **Rollback:** deploy the prior API image; no migration or stored data changed.

## P0-H follow-up — safe operator ingestion-run projection

- **Status:** local projection and confidentiality regression are green; this
  adds a read-only operator view and does not complete the broader P0-H review
  projection, live dependency, or deployment gates.
- **Baseline commit:** `2e92eab`.
- **Implementation:** `GET /admin/catalogue-ingestion/runs/{run_id}` now
  returns a dedicated operator projection rather than the raw ORM-shaped run.
  It reports candidate/source roles, artifact IDs and hashes, parser versions,
  canonical evidence-block counts, source-routing decisions, safe OCR/browser
  decision state, objective coverage, executed/reused extraction counts, and
  provider/model/prompt/schema/cost lineage. The endpoint exposes lease owner
  timing and a `lease_active` state but no fencing token. It also excludes raw
  artifact text, excerpts, HTML, model output, and external failure text. New
  artifacts persist the fetch parser version in immutable artifact metadata;
  historic PDF artifacts explicitly report that OCR outcome was not recorded,
  rather than inventing an outcome.
- **Test added:** a real local queued extraction verifies hashes, parser and
  evidence-block lineage, attempt accounting, safe decision states, and that a
  deliberately populated fencing token or source text cannot appear in the
  serialized projection.
- **Commands and results:** targeted Ruff lint and format checks passed;
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/p0h-operator-projection-evidence
  tests/test_catalogue_ingestion.py::test_operator_run_status_exposes_safe_lineage_without_source_content_or_lease_token -q`
  — passed with the existing Starlette deprecation and local pytest-cache
  permission warnings; `git diff --check` passed.
- **Security/trust invariant:** a fencing token never reaches any run response,
  and the operator endpoint exposes lineage metadata only—never raw source
  HTML/text or unbounded external exception text. No review action,
  publication action, feature flag, worker, or deployment state changed.
- **Known limitations:** no review projection yet displays proposed facts,
  exact evidence blocks, scoped conflicts, reviewer actions, or append-only
  review history. OCR decision telemetry is not yet persisted by the document
  normalizer, browser acquisition remains disabled, and the remaining P0-H
  runtime/readiness gates stay open.
- **Rollback:** deploy the prior API image; no migration or stored data rewrite
  is required.

## P0-E/P0-H follow-up — durable PDF conversion telemetry

- **Status:** local provenance and safe operator-status coverage is green; this
  records conversion outcomes only and does not close the real-Docling,
  protected-fixture, dedicated-worker, restricted-egress, cgroup, or real OCR
  operational gates.
- **Baseline commit:** `112765c`.
- **Objective:** retain per-fetch Docling page count, parser version, and
  measured OCR outcome without shared mutable normalizer state, then expose
  only that persisted lineage through the review-only operator run status.
- **Files changed:** `app/modules/opportunities/source_monitor.py`,
  `app/modules/catalogue_ingestion/document_conversion.py`,
  `app/modules/catalogue_ingestion/service.py`,
  `app/modules/catalogue_ingestion/schemas.py`, and focused conversion,
  fetcher, and ingestion tests.
- **Data/migrations:** none. New immutable catalogue artifacts store a closed
  `document_conversion` metadata object in their existing `fetch_metadata`
  JSON field. Existing PDF artifacts correctly remain `not_recorded` because
  their historical conversion outcome cannot be inferred.
- **Verified behavior before:** `ConvertedDocument` contained `page_count` and
  `used_ocr`, but `CatalogueDocumentPayloadNormalizer` returned only text;
  `SafeSourceFetcher` therefore dropped conversion facts and operator status
  necessarily reported PDF OCR as `not_recorded`.
- **Implementation:** the fetch boundary now accepts both legacy string
  normalizers and a typed `NormalizedSourcePayload`. The Docling normalizer
  returns text plus its own parser version, page count, and one of the measured
  outcomes `not_used/text_sufficient` or
  `used/text_insufficient_ocr_succeeded`. Ingestion whitelists and validates
  the complete three-field record before persisting it. Operator status reads
  the same validated record, includes `page_count`, and never exposes arbitrary
  metadata. No mutable `last_conversion` state is retained on the shared
  normalizer.
- **Security/trust invariant:** all acquisition still enters through
  `SafeSourceFetcher`; PDF bytes and normalized text are still omitted from
  operator status. Only a bounded closed vocabulary of conversion facts is
  persisted, so worker secrets, configuration, and arbitrary fetcher metadata
  cannot enter immutable artifacts or the status response. OCR remains an
  explicit feature-gated fallback after measured text insufficiency; no
  publication or reviewer write behavior changed.
- **Tests added:** non-OCR PDF conversion records page count and
  `text_sufficient`; the fake OCR-success regression records the fallback
  reason; the safe fetcher preserves typed per-call telemetry while ordinary
  string normalizers remain covered by the monitor suite; a queued PDF
  ingestion persists and projects OCR/page lineage while proving an injected
  `worker_secret` is not serialized.
- **Commands and results:** targeted Ruff lint and formatting passed;
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/p0h-document-telemetry-source tests/test_document_conversion.py
  tests/test_source_monitor.py` — **29 passed, 1 warning in 9.49s**;
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/p0h-document-telemetry-focused tests/test_document_conversion.py
  tests/test_source_monitor.py::test_safe_fetcher_keeps_per_fetch_normalization_telemetry
  tests/test_catalogue_ingestion.py::test_operator_run_status_exposes_safe_lineage_without_source_content_or_lease_token
  tests/test_catalogue_ingestion.py::test_operator_run_status_reports_persisted_pdf_conversion_telemetry
  tests/test_catalogue_ingestion.py::test_candidate_review_projection_cites_exact_blocks_and_preserves_audit_history`
  — **13 passed, 2 warnings in 3.39s** (existing Starlette deprecation and
  local pytest-cache permission warnings); `git diff --check` passed before
  this log update.
- **Skipped/environment-blocked:** a complete `tests/test_catalogue_ingestion.py`
  attempt did not return a final summary within the local 30-second command
  window, so it is not counted as passing. The real Docling/MEXT/OCR execution
  and dedicated worker runtime evidence remain unavailable.
- **Rollback:** deploy the prior application image; no migration or data
  backfill is involved. New artifacts retain immutable conversion provenance;
  legacy artifacts remain readable.
- **Next gate:** execute a real approved complex PDF with pre-baked Docling
  artifacts in a dedicated restricted worker, then verify persisted telemetry
  against protected MEXT/Open Doors fixture evaluations.

## P0-H follow-up — cited candidate review projection

- **Status:** local read-only review projection is green; it closes neither the
  universal-graph approval gate nor the remaining P0-H runtime/deployment gates.
- **Baseline commit:** `a4c0d28`.
- **Implementation:** `GET /admin/catalogue-ingestion/candidates/{candidate_id}/review-projection`
  now turns a validated claim-resolution payload into proposed facts with the
  typed value, cycle/route/institution/programme scope, source URL/role,
  mapped T0–T3 provenance tier, and the single immutable canonical evidence
  block containing the exact claim span. It fails closed if a resolved claim
  cannot be joined to its stored artifact/block. The projection includes
  resolved conflicts, rejected claims, missing mandatory objectives, and the
  append-only candidate audit history with actor, action, reason, timestamp,
  and integrity hash. Evidence is declared `plain_text`; this JSON endpoint
  never returns source HTML, and any future UI must render the supplied text
  as escaped plain text.
- **Data/migrations:** none. The view reads existing immutable artifacts,
  evidence blocks, routing decisions, claim resolutions, and audit logs.
- **Tests added:** a local queued extraction is projected into a cited
  scholarship fact; the test verifies its normalized scope, T0 authority,
  exact block offsets/text, and a preserved append-only reviewer audit event.
- **Commands and results:** targeted Ruff lint and format checks passed;
  `uv --cache-dir .uv-cache run python -m pytest -ra --basetemp
  .pytest-tmp/p0h-review-projection-evidence
  tests/test_catalogue_ingestion.py::test_operator_run_status_exposes_safe_lineage_without_source_content_or_lease_token
  tests/test_catalogue_ingestion.py::test_candidate_review_projection_cites_exact_blocks_and_preserves_audit_history
  tests/test_source_routing.py -q` — **7 passed, 2 warnings in 10.4s**
  (existing Starlette deprecation and local pytest-cache permission warnings);
  `git diff --check` passed.
- **Security/trust invariant:** the view cannot turn a claim into a reviewable
  fact without a persisted exact evidence block. It has no write path, cannot
  publish, and provides normalized plain text rather than raw HTML.
- **Known limitations:** authority mapping is a projection over the current
  source classifier (provider/government T0, route T1, institution T2, portal
  T3); durable universal authority/delegation state still requires P0-G. There
  is no reviewer decision write model/version yet, and no browser UI exists to
  enforce escaped rendering at the presentation layer.
- **Rollback:** deploy the prior API image; no migration or stored data rewrite
  is required.

## P0-H/P0-G follow-up — immutable review submission lineage

- **Status:** local review-only proposal/decision lineage is green; universal
  graph approval and durable accept/reject semantics remain open.
- **Baseline:** `a6adfaa`.
- **Implementation:** additive proposal and decision tables snapshot the exact
  candidate payload, cited artifact hashes, and evidence-block canonicalization
  versions under a deterministic proposal hash. A reviewer submission records
  actor, reason, timestamp, and prior candidate state against that proposal.
  Scoped v3 candidates can now enter `submitted_for_review` without legacy
  graph materialization; this remains review-only and writes no public record.
- **Migration:** `20260824_0052_catalogue_review_proposals`, additive and
  reversible.
- **Evidence:** focused Ruff checks passed; proposal/submission, scoped staging,
  and migration upgrade/downgrade coverage completed **3 passed, 2 warnings in
  9.29s**. Warnings are existing Starlette deprecation and local pytest-cache
  permissions.
- **Security/trust:** exact evidence is mandatory; no decision can be recorded
  without immutable evidence blocks. No publication path was added.
- **Known limitations:** this records submission, not a final accept/reject
  decision, and does not implement universal graph approval or UI rendering.

## P0-H follow-up — review-decision projection

- **Status:** local read-only decision lineage projection is green.
- **Baseline:** `4a98d75`.
- **Implementation:** the candidate review projection now includes each
  persisted submission action with the immutable proposal hash/schema version,
  actor, reason, prior candidate state, and timestamp. It remains read-only
  and returns no raw source HTML.
- **Evidence:** focused submission and cited-projection coverage completed
  **2 passed, 2 warnings**; targeted Ruff checks and `git diff --check` passed.
- **Security/trust:** the projection reads only persisted proposal/decision
  lineage; it cannot create approvals or publication records.
- **Known limitations:** final accept/reject actions, universal graph approval,
  browser UI escaping, and operational RC evidence remain open.

## P0-G follow-up — durable routed authority tier

- **Status:** local authority lineage is green; this is not complete scoped
  delegation/completeness enforcement.
- **Implementation:** each versioned immutable source-routing decision now
  persists T0 provider/government, T1 route, T2 institution, T3 portal, or
  unresolved authority. Safe operator status exposes that stored value.
- **Migration:** `20260824_0053_catalogue_routing_authority`, additive and
  reversible.
- **Evidence:** focused authority mapping and migration upgrade/downgrade tests
  completed **2 passed, 2 warnings in 7.36s**; targeted Ruff and diff checks
  passed. Warnings are existing Starlette deprecation and pytest-cache access.
- **Security/trust:** unresolved sources remain unresolved; the tier does not
  override scope, exact evidence, conflicts, or review-only publication gates.
- **Known limitations:** delegated facts and bundle-level per-scope completeness
  remain to be modeled durably.

## P0-E follow-up — isolated real-Docling MEXT proof

- **Status:** the first real offline conversion proof is green; it does not
  close P0-E or the protected-fixture evaluation gate. The image is local-only,
  the catalogue supervisor has no transport to it yet, and a reviewed
  text-insufficient scan is still required to prove the automatic OCR fallback.
- **Input provenance:** on 2026-08-24, the official MEXT 2027 Research
  Students guidelines PDF was acquired once through `SafeSourceFetcher` and
  staged only under `tmp/p0e-proof`. Its URL, final URL, MIME type, and
  416,454-byte raw SHA-256 exactly match the MEXT entry in
  `tests/fixtures/catalogue_extraction/source_snapshot_ledger.v1.json`. The
  raw input and generated outputs are not committed, uploaded, or exposed by
  an operator endpoint.
- **Worker image:** `docker/docling-worker.Dockerfile` now bakes the reviewed
  `.docling-models` bundle instead of downloading models while building or at
  runtime. The image verifies the bundle before it drops to the `docling`
  user. It contains no application-secret environment variables and sets
  `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and
  `DOCLING_ARTIFACTS_PATH=/opt/docling/models`.
- **Integrity correction:** the original bundle hash depended on host `Path`
  ordering, which differed between Windows lock generation and Linux worker
  verification. `scripts/verify_docling_artifacts.py` now canonicalizes
  relative POSIX paths before hashing. The reviewed bundle has 26 files,
  765,212,139 bytes, and canonical SHA-256
  `0474ee1ce69c48c8fcff5671164021892f34e8260f68da33b6c03d4180af9885`.
  A regression test locks that ordering. The image also installs the minimal
  headless OpenCV libraries (`libgl1`, `libglib2.0-0`, `libxcb1`, `libxext6`,
  and `libxrender1`) required by Docling table inference.
- **Isolation evidence:** the Compose profile and one-shot proof both use
  `network_mode: none`, read-only root filesystem, a 512 MB `/tmp` tmpfs,
  `cap_drop: ALL`, `no-new-privileges`, 256 PIDs, 2 CPUs, and 4 GB memory.
  The PDF is bind-mounted read-only and only `tmp/p0e-proof/output` is
  writable. The disposable containers were removed on completion.
- **Real conversion result:** the restricted local image
  `scholarship-catalogue-docling-worker:p0e-proof` completed the 11-page PDF
  and produced 56,293 characters of Markdown (SHA-256
  `7b0d0bbf092c44f68de61299421dcd2144ddfa3481762dd59814fc40fd1f5219`).
  It preserved 23 ordered headings through `15. NOTES`, 130 list items, and
  the 11-row application-documents Markdown table. This is a genuine Docling
  layout/table conversion, not a `pypdf` fallback.
- **OCR result:** an otherwise identical restricted run with `--enable-ocr`
  initialized RapidOCR's detector, classifier, and recognizer from the baked
  bundle on CPU, then produced byte-identical Markdown. This is expected for
  the text-sufficient MEXT PDF. It proves the real offline OCR stack starts;
  it does **not** prove the application's `text_insufficient` OCR-fallback
  decision and must not be treated as such.
- **Fixture discrepancy:** the live raw PDF matched the reviewed raw hash, but
  this real worker output does not match the ledger's older normalized PDF
  count/hash (52,169 characters / `ed069...`). No ledger was rewritten. A
  reviewer must decide the approved expected normalization before P0-A's
  executable fixture evaluation can pass.
- **Evidence:** host and Linux-container bundle verification passed; focused
  Ruff lint/format checks passed; and
  `uv --cache-dir .uv-cache run python -m pytest -ra
  tests/test_docling_artifacts.py tests/test_document_conversion.py -q`
  completed **10 passed, 2 warnings**. Warnings are the existing Starlette
  deprecation and local pytest-cache permission warning.
- **Security/trust:** every networked acquisition still passes through
  `SafeSourceFetcher`; the worker accepts only local paths and no credentials,
  URLs, database access, or application settings. No feature flag, reviewer
  decision, public opportunity, deployment, merge, or publication changed.
- **Remaining P0-E work:** implement and prove the application-to-dedicated
  worker transport; add a reviewed text-insufficient scan with expected
  outcomes; demonstrate the automatic OCR fallback and persist its telemetry;
  then execute the full protected-fixture evaluation.

## CI follow-up — PostgreSQL quota migration compatibility

- **Status:** fixed a hosted-CI PostgreSQL migration failure that blocked all
  later lint and test steps. This is a migration correctness repair only; it
  changes no feature flag, review decision, publication, or deployment state.
- **Cause:** `20260824_0048_assistant_quota_reservations` backfilled the
  reserved `assistant_quota_counters.window` column using raw unquoted SQL.
  SQLite accepted it, while PostgreSQL rejected the insert at `window`.
- **Fix:** quote `"window"` in both dialect-specific backfill statements. The
  table definition and ORM field remain unchanged.
- **PostgreSQL evidence:** a fresh disposable database named
  `p0e_migration_proof` in the local Compose PostgreSQL service was upgraded
  from an empty schema to `20260824_0053` using a disposable read-only
  application container. It completed successfully; the target table has
  `user_id`, `window`, `window_start`, `used_slots`, and `updated_at`, and its
  RLS/force-RLS flags are enabled. The running application database was not
  used.
- **Next evidence:** push the corrective commit and require hosted CI to
  complete its full lint and test stages before treating this as a closed CI
  gate.

## CI follow-up — reclaimed lease accounting and release preflight

- **Status:** repaired the remaining hosted-CI regressions identified after
  the PostgreSQL quota migration fix. No deployment, merge, release, feature
  enablement, review decision, or publication was performed.
- **Lease accounting:** an expired `RUNNING` lease is now reclaimed with a
  fresh fencing token without incrementing `attempt_count`. It is an
  availability recovery, not a reported failed execution, so it cannot drain
  the retry budget before the reclaiming worker reports its outcome. Ordinary
  pending claims still increment the count and the existing two transient
  failure dead-letter behavior is unchanged. SQLite and PostgreSQL regressions
  assert the reclaimed run remains at one attempt.
- **Timeout cleanup:** process-tree termination retains the native
  process-group/task-tree path and uses a guarded direct-process fallback.
  The cross-platform regression explicitly verifies `taskkill` on Windows and
  `killpg` on POSIX, without relying on a fake process having the full
  `subprocess.Popen` interface.
- **Release policy:** the declared Alembic head is now `20260824_0053` and
  the review date is `2026-08-24`; the existing expand-only, rolling-safe,
  deferred-contract policy is unchanged.
- **Evidence:** focused Ruff check/format and
  `tests/test_document_conversion.py tests/test_catalogue_ingestion_queue.py
  tests/test_release_policy.py` completed **16 passed, 2 known warnings**.
  The PostgreSQL lease-reclaim/fencing/failure transition was also executed in
  a disposable read-only application container against the isolated
  `p0e_migration_proof` database and passed. The proof creates and removes its
  sole test row; it does not access the running application database.
- **Next evidence:** run the full suite and push the repair before rechecking
  hosted CI. P0-E remains open for its separate worker-transport and reviewed
  OCR-fixture gates.

## CI follow-up — Crawlee bridge lifecycle

- **Status:** repaired optional-Crawlee regressions exposed by the local
  environment where the extra is installed. No default acquisition path,
  network policy, feature flag, deployment, merge, release, or publication was
  changed.
- **Fix:** Crawlee-labelled artifact versions now retain the inner safe-fetcher
  parser version (`crawlee-static.v2-safe-bridge+legacy-safe-fetcher.v1`), so
  provenance accurately identifies both the scheduler and parser. When a host
  already owns an active event loop, the synchronous bridge runs Crawlee in a
  short-lived thread instead of nesting `asyncio.run`; its handler still calls
  only `LegacySafeEvidenceAcquirer` and never Crawlee HTTP APIs.
- **Tests:** added active-event-loop coverage. The focused optional-Crawlee
  suite completed **6 passed, 2 expected skips, 2 known warnings**. The final
  local suite completed **711 passed, 33 skipped, 5 warnings in 190.25s**.
  Skips are the intentionally unconfigured browser, PostgreSQL, and Redis
  integration environments; the catalogue lease PostgreSQL contract was
  separately proven against the isolated disposable database above.
- **Security/trust:** the thread changes scheduler lifetime only; DNS/IP,
  redirect, robots, MIME, byte, and SSRF controls remain exclusively in
  `SafeSourceFetcher`.

## CI follow-up — POSIX Docling timeout assertion

- **Status:** hosted CI run 481 passed migration, lint, format, security scan,
  coverage (86.53%), and 729 tests before one Linux-specific test assertion
  failed. Azure infrastructure validation run 124 and the release-candidate
  security scan were green.
- **Cause and fix:** the timeout production code uses `creationflags` and
  `taskkill` on Windows, but `start_new_session` and `killpg` on POSIX. The
  regression test still read Windows-only `creationflags` unconditionally;
  it now asserts the appropriate process-isolation mechanism for each
  platform.
- **Evidence:** focused lint/format and `tests/test_document_conversion.py`
  completed **9 passed, 2 known warnings** locally. The next push is limited
  to this cross-platform test correction; hosted CI remains the release gate.

## P0-E — application-to-dedicated Docling worker transport

- **Status:** bounded local transport contract is green. The default
  `catalogue_document_intelligence_enabled` gate remains false; this does not
  enable production conversion, deploy an image, or close the reviewed OCR
  fixture gate.
- **Baseline:** `c43ccdd`.
- **Implementation:** when the existing document-intelligence gate is enabled,
  `CatalogueIngestionService` now selects a filesystem job-volume transport
  instead of a local Docling subprocess. The application writes a fresh opaque
  job directory containing only admitted PDF bytes and fixed conversion limits,
  then atomically publishes it to the restricted worker. The worker atomically
  claims one request, starts a fresh isolated Docling child for that request,
  returns only bounded text or a stable error code, and removes the input.
  Request/result messages have an absolute deadline; the caller cancels late
  work, and the worker rejects expired work before starting Docling. Both the
  caller and worker impose the runtime cap; worker timeout termination reuses
  the existing process-group cleanup path. Pending plus in-flight work is
  bounded, abandoned result/cancellation messages are pruned, and the worker
  emits a volume heartbeat used by readiness.
- **Isolation/configuration:** the pre-existing restricted `document-converter`
  Compose profile now mounts only the dedicated jobs volume and runs the worker
  service loop. The API receives the same volume path but the conversion feature
  flag stays false. The worker still has no database, Redis, URL, or application
  credential transport. `docker compose --profile catalogue-document-conversion
  config --quiet` completed successfully; no container or conversion run was
  started.
- **Files changed:** `app/modules/catalogue_ingestion/document_conversion_transport.py`,
  `document_conversion_worker.py`, `service.py`, `app/core/config.py`,
  `app/core/health.py`, `compose.yaml`, and focused transport/readiness tests.
- **Focused evidence:**
  `uv --cache-dir .uv-cache run python -m pytest -q --basetemp
  .pytest-tmp/p0e-transport-final tests/test_document_conversion_transport.py
  tests/test_document_conversion.py
  tests/test_operations.py::test_aggregate_readiness_fails_closed_when_catalogue_docling_is_enabled_without_worker
  tests/test_operations.py::test_aggregate_readiness_accepts_a_fresh_catalogue_docling_worker_heartbeat
  tests/test_catalogue_ingestion.py::test_service_enables_layout_document_normalizer_only_behind_feature_gate`
  — **21 passed, 2 warnings in 3.51s**. Warnings are the existing Starlette
  TestClient deprecation and local pytest-cache permission warning. Targeted
  Ruff lint, format check, and `git diff --check` passed.
- **Known limitations:** this proves the application/worker protocol, not a
  reviewed text-insufficient OCR fixture or protected-fixture evaluation. The
  dedicated worker profile remains opt-in, and no production flag was enabled.
- **Rollback:** keep `APP_CATALOGUE_DOCUMENT_INTELLIGENCE_ENABLED=false` (the
  default) or remove the worker profile; pending jobs are bounded and carry no
  database state. Deploying the prior application image restores the previous
  disabled behavior.
