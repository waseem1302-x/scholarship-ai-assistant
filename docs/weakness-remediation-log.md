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
