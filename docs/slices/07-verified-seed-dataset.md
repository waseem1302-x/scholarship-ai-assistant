# Slice 07 — Verified Seed Dataset

## Goal

Add a small, honest dataset of real scholarship opportunities from official
sources so the project can be demonstrated without fabricated records.

This is a portfolio/demo seed dataset, not a production data feed.

## Implemented files

- `data/seed/verified_opportunities.json`
- `app/cli/seed_verified_opportunities.py`
- `tests/test_seed_opportunities.py`

## Seed opportunities

The first seed dataset contains:

1. Chevening Scholarships 2027/28
2. Knight-Hennessy Scholars 2027 Cohort
3. DAAD Development-Related Postgraduate Courses EPOS 2027/28

## Official sources checked

- Chevening application timeline:
  <https://www.chevening.org/scholarships/application-timeline/>
- Chevening eligibility criteria:
  <https://www.chevening.org/resource-hub/guidance/eligibility/>
- Chevening funding FAQ:
  <https://www.chevening.org/faqs/what-does-a-chevening-scholarship-cover/>
- Knight-Hennessy Scholars admission:
  <https://knight-hennessy.stanford.edu/admission>
- Knight-Hennessy Scholars eligibility:
  <https://knight-hennessy.stanford.edu/admission/before-you-apply/eligibility>
- Knight-Hennessy Scholars funding:
  <https://knight-hennessy.stanford.edu/program-overview/funding>
- DAAD EPOS scholarship database:
  <https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database?detail=50076777>

## How to load the seed dataset

Use the guided, idempotent demo bootstrapper. It validates the whole dataset,
creates or updates an administrator, and then loads only records that do not
already exist:

```bash
docker compose exec api python -m app.cli.bootstrap_demo
```

Optional environment variables:

```bash
APP_DEMO_ADMIN_EMAIL=admin@example.com
APP_DEMO_ADMIN_PASSWORD=a-unique-password-of-at-least-12-characters
APP_DEMO_SEED_FILE=/app/data/seed/verified_opportunities.json
```

The lower-level seed command remains available for data operations that already
have a trusted administrator:

```bash
APP_SEED_ADMIN_EMAIL=admin@example.com python -m app.cli.seed_verified_opportunities
```

## Behavior

The loader:

- validates every seed record against the same `OpportunityCreate` schema used
  by admin opportunity creation
- requires an existing admin user
- skips existing duplicate opportunities
- creates the opportunity as a draft
- marks the primary source as officially verified through the existing
  verification service
- stores additional official source records with verification metadata

## Decision

Use an explicit CLI loader instead of automatically loading seed data at app
startup.

## Reason

Automatic seed loading can surprise developers, mutate databases unexpectedly,
and make demos look like the system has live production data. An explicit loader
keeps the action intentional.

## Alternative considered

Run seed loading during Docker startup after migrations.

## Tradeoff

Manual loading is one deliberate command, but it is safer and easier to explain.

## What this teaches

- Responsible handling of real-world data
- Source-first seed data design
- CLI operations for backend maintenance
- Idempotent data loading
- Separating demo data from application startup

## Portfolio evidence

This slice proves the project does not depend on fake scholarship examples. It
can run with a small set of real records that preserve official source URLs,
verification status, and last-verified metadata.

## Tests added

- Seed file contains valid opportunity records.
- Seed source excerpts stay short.
- Loader requires an admin user.
- Dry run validates without creating records.
- Loader creates active officially verified public records.
- Running the loader twice skips duplicates.
- Invalid seed files are rejected.

## Known limitations

- The seed set is a curated demo catalogue, not exhaustive scholarship coverage.
- Deadlines and requirements can change after 2026-07-22.
- Before any public release, re-verify official sources and schedule
  `python -m app.cli.monitor_sources`; the optional Docker `monitoring` profile
  polls the due-source monitor daily for single-host deployments.
- Some opportunities support multiple degree levels, while the current schema
  stores one representative degree level per record.
- DAAD EPOS has course-specific deadlines, so the seed record leaves the general
  deadline empty and warns users to check the selected course.

## Recommended next slice

Stage 8 should improve public search filters and result quality:

1. nationality filter
2. field filter
3. deadline window filter
4. application-fee filter
5. status and verification filters for admin search
