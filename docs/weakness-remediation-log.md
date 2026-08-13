# Weakness Remediation Log

This log tracks verified audit items from `scholarship_ai_assistant_full_weakness_audit.md`.

## Development Environment Confirmed

- Workspace: `C:\Users\Admin\Downloads\Scholarship AI Assistant`
- Branch: `main` tracking `origin/main`
- Git: `C:\Program Files\Git\cmd\git.exe`
- VS Code: `C:\Users\Admin\AppData\Local\Programs\Microsoft VS Code\Code.exe`
- Docker Desktop: running, but `docker` was not on the active PowerShell `PATH`
- Project Python: `C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Scripts\python.exe`
- Codex bundled Node: `C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`
- Codex bundled pnpm: `C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd`

## 2026-08-14 Checkpoint: Weaknesses 33-37

| ID | Status | Evidence | Remediation |
| --- | --- | --- | --- |
| 33 | Confirmed true, fixed | Public catalogue nationality filter used case-insensitive prose substring matching against `Opportunity.nationality_eligibility`. | Public nationality filtering now uses structured eligibility rules with normalized value keys and explicit `not_in` exclusion handling. |
| 34 | Confirmed true, fixed | Public catalogue field filter used case-insensitive prose substring matching against `Opportunity.field_eligibility`. | Public field filtering now uses structured eligibility rules with normalized value keys. |
| 35 | Confirmed true, fixed | English and application-fee filters used prose substring matching against requirement text. | Application-fee filtering now uses `application_fee_status`; English filtering now uses structured test/status rules. |
| 36 | Verified already fixed | Catalogue window filtering already used SQL-queryable `catalogue_*` projection columns and had regression coverage. | No code change required in this checkpoint. |
| 37 | Confirmed true for affected filters, fixed | Public field, nationality, English, and fee filters compiled to substring predicates. | Public filters now compile to exact structured columns/relationships rather than prose `LIKE` predicates. |

Verification:

- `.\.venv\Scripts\python.exe -m ruff check app\modules\opportunities tests\test_opportunities.py tests\test_catalogue_window_query.py tests\test_migrations.py tests\test_seed_opportunities.py alembic\versions\20260814_0026_funding_coverage_components.py alembic\versions\20260814_0028_structured_catalogue_filters.py app\cli\seed_verified_opportunities.py`
- `.\.venv\Scripts\python.exe -m pytest`
- `pnpm test`
- `pnpm build`

## 2026-08-14 Checkpoint: Weaknesses 38-43

| ID | Status | Evidence | Remediation |
| --- | --- | --- | --- |
| 38 | Confirmed true, fixed | `verify_source()` promoted records to `active` when one source became officially verified. | Source verification no longer publishes records; new active records are rejected at create time, and explicit `publish` review action is required for public visibility. |
| 39 | Confirmed true, fixed | Opportunity, applications, Assistant, community, and lifecycle code selected official sources with separate local predicates. | Added shared `EvidencePolicy.select_current_official_source()` and routed affected modules through it, including conflict/expired/archive rejection. |
| 40 | Confirmed true, hardened | Monitor validated DNS before opening a later urllib connection. | Added post-connect peer-address validation and rejects private/reserved peers after connection establishment. |
| 41 | Confirmed true, improved | Monitor hashed raw fetched bytes, making dynamic page noise look like factual changes. | Monitor now hashes normalized scholarship evidence text/sections with script/style/timestamp/noisy-token stripping. |
| 42 | Confirmed true, improved | Excerpt extraction stripped all HTML and took the first text block only. | Added section-aware extraction with labels for deadline, eligibility, funding, documents, and application process evidence. |
| 43 | Confirmed true, partially improved | No provider-specific crawl policy object existed. | Added `SourceCrawlPolicy` support for host-level timeout, byte limit, interval, and user-agent configuration. |

Verification:

- `.\.venv\Scripts\python.exe -m ruff check app tests\test_opportunities.py tests\test_applications.py tests\test_assistant.py tests\test_community.py tests\test_matching.py tests\test_source_monitor.py tests\test_lifecycle_reconciliation.py tests\test_seed_opportunities.py`
- `.\.venv\Scripts\python.exe -m pytest tests\test_opportunities.py::test_source_verification_does_not_publish_record_without_review_action tests\test_opportunities.py::test_admin_create_cannot_publish_record_without_review_action tests\test_opportunities.py::test_admin_review_action_publish_and_flag_conflict_control_public_visibility tests\test_opportunities.py::test_source_hash_change_blocks_public_visibility_until_reverified tests\test_applications.py tests\test_command_centre.py tests\test_assistant.py tests\test_community.py tests\test_matching.py::test_matching_requires_profile tests\test_source_monitor.py tests\test_lifecycle_reconciliation.py tests\test_seed_opportunities.py`
