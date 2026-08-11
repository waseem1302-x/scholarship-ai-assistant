# Phase 2 opportunity data platform

## Goal

Turn the existing source-first catalog into an operational data platform that
can be reviewed, monitored, and trusted before later AI retrieval uses it.

## Delivered in this increment

- immutable `source_excerpts` evidence snapshots for reviewed source text
- admin source-check endpoint for recording observed content hashes, change
  summaries, and captured excerpts
- automatic demotion of changed source hashes to `needs_review`, which blocks
  public visibility until a curator re-verifies the source
- append-only verification records and audit logs for source checks
- admin data-quality issue endpoint with severity, issue code, opportunity id,
  source id, and human-readable message
- admin review queue endpoint that groups high and medium priority curation
  reasons by opportunity
- static admin frontend panels for the review queue and data-quality dashboard
- reviewer-action endpoint and frontend controls for publishing, holding,
  flagging conflicts, requesting rechecks, resolving conflicts, expiring, and
  archiving records
- CSV import parsing for spreadsheet-shaped curation data, mapped into the same
  review-safe import contract as JSON rows
- scheduled-source monitor runner that selects due active verified official
  sources, fetches them with SSRF-aware URL checks, computes content hashes, and
  records source checks through the same audit path

## Product and safety rules

- A changed official source is treated as untrusted until reviewed.
- Existing opportunity records are not deleted when source content changes.
- Source excerpts are separate evidence snapshots; mutable source status does
  not overwrite historical review evidence.
- Data-quality issues are visible to administrators and hidden from public
  students.
- Public catalog queries still require an active opportunity and an officially
  verified official source.
- Reviewer actions are fail-closed: hold, conflict, recheck, expire, and archive
  remove public visibility.
- Non-publish reviewer actions require notes so future maintainers can
  understand why a record changed state.
- The source monitor only fetches HTTPS URLs and blocks localhost, private,
  link-local, multicast, reserved, and unresolved network targets.

## Source monitor runner

```bash
python -m app.cli.monitor_sources
```

Environment controls:

- `APP_SOURCE_MONITOR_DRY_RUN=true` previews checks without mutating records.
- `APP_SOURCE_MONITOR_LIMIT=20` controls the maximum sources checked per run.
- `APP_SOURCE_MONITOR_INTERVAL_DAYS=7` controls how often a source becomes due.

## Reviewer actions

```text
POST /api/v1/admin/opportunities/{id}/review-actions
```

Supported actions:

- `publish`
- `hold_for_review`
- `flag_conflict`
- `request_recheck`
- `resolve_conflict`
- `expire`
- `archive`

Every reviewer action creates a verification record and audit log entry.

## CSV ingestion

```text
POST /api/v1/admin/opportunities/import
```

Use `source_format = csv` and `csv_content` in the JSON request body. CSV rows
are parsed into the same internal row shape as JSON imports, so draft forcing,
source review forcing, duplicate detection, row-level validation, and dry-run
behavior stay consistent.

## Verification

- `pytest tests/test_opportunities.py`
- `pytest tests/test_source_monitor.py`
- reviewer-action API tests in `tests/test_opportunities.py`
- CSV import parser tests in `tests/test_opportunities.py`
- `pytest tests/test_frontend.py tests/test_opportunities.py`
- full `pytest`
- `ruff check .`
- `ruff format --check .`

## Remaining Phase 2 work

- deployment scheduling for the source-monitor runner in the eventual hosting
  environment
- multipart CSV upload UI and custom column mapping
- assisted webpage/PDF extraction with human review
- richer data-quality analytics over freshness, countries, providers, and field
  coverage
