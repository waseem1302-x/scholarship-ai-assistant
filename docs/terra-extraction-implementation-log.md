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
