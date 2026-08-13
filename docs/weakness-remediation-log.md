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

## 2026-08-14 Checkpoint: Weaknesses 44-49

| ID | Status | Evidence | Remediation |
| --- | --- | --- | --- |
| 44 | Confirmed true, fixed | Student nationality and residence were stored only as free-text display strings. | Added canonical ISO alpha-2 country code fields for nationality, residence, and preferred destinations while preserving the user's display text. |
| 45 | Confirmed true, fixed | Intended field and academic discipline were raw text only. | Added `intended_field_taxonomy` and `intended_field_detail` so canonical matching can be separated from user-entered wording. |
| 46 | Confirmed true, fixed | Profile narrative and list fields lacked API-level bounds. | Added max lengths for free-text fields, list sizes, and list item lengths with regression tests. |
| 47 | Confirmed true, fixed | Completeness always required CGPA/grading scale even when percentage was supplied instead. | Completeness now accepts either CGPA or percentage and only asks for grading scale when CGPA is present. |
| 48 | Confirmed true, fixed | Profile updates only supported full `PUT`, making omitted fields vulnerable to accidental clearing by future clients. | Added `PATCH /profiles/me` with sparse updates and dependent canonical-field cleanup when source fields are cleared. |
| 49 | Confirmed true, fixed | Profiles had no edit version or stale-write detection. | Added profile `version`, `expected_version` conflict checks for existing `PUT`/`PATCH`, frontend save support, and stale-write tests. |

Verification:

- `.\.venv\Scripts\python.exe -m ruff check app\modules\profiles tests\test_profiles.py tests\test_migrations.py tests\test_matching.py`
- `.\.venv\Scripts\python.exe -m pytest tests\test_profiles.py tests\test_migrations.py -q`
- `.\.venv\Scripts\python.exe -m pytest tests\test_matching.py::test_matching_persists_reproducible_evaluation_history -q`
- `.\.venv\Scripts\python.exe -m pytest -q`
- `pnpm --dir frontend test`
- `pnpm --dir frontend build`

## 2026-08-14 Checkpoint: Weaknesses 59-64

| ID | Status | Evidence | Remediation |
| --- | --- | --- | --- |
| 59 | Confirmed true, fixed | Reminder idempotency used a globally unique client key and looked up reminders by key only. | Reminder idempotency is now unique and queried by `(application_id, idempotency_key)`, with a cross-tenant regression test. |
| 60 | Confirmed true, fixed | Application version was checked in memory before commit. | Application updates now require `expected_version` and use an atomic conditional SQL update with `WHERE version = expected_version`. |
| 61 | Confirmed true, fixed | Delete-all loaded at most 500 application records before deletion. | Delete-all now selects all owner applications without the 500 cap before deleting the normalized workspace and saved-opportunity tracker data. |
| 62 | Confirmed true, fixed | Export loaded at most 500 applications and 1000 events per application. | Export now uses uncapped owner-scoped application and event queries. |
| 63 | Confirmed true, fixed | Operational reporting loaded all tasks and reminders, then counted in Python. | Operational reporting now uses SQL grouped counts and filtered count queries. |
| 64 | Confirmed true, fixed | Application list/get/dashboard called deadline sync and could commit during reads. | Read routes now project current deadline state without mutating stored applications or creating deadline events. |

Verification:

- `.\.venv\Scripts\python.exe -m ruff check app\modules\applications tests\test_command_centre.py tests\test_migrations.py alembic\versions\20260814_0030_application_command_centre_hardening.py`
- `.\.venv\Scripts\python.exe -m pytest tests\test_command_centre.py tests\test_migrations.py -q`
- `.\.venv\Scripts\python.exe -m pytest -q`
- `pnpm --dir frontend build`

## 2026-08-14 Checkpoint: Weaknesses 65-67

| ID | Status | Evidence | Remediation |
| --- | --- | --- | --- |
| 65 | Confirmed true, fixed | Starter task generation scanned all historical match rule outcomes for the opportunity and ordered by evaluation time. | Starter tasks now use exactly the latest `MatchEvaluation` for the student, preventing stale next-actions from older evaluations from reappearing. |
| 66 | Verified already fixed | Application and opportunity services both route official source selection through `EvidencePolicy.select_current_official_source()`. | No code change required in this checkpoint. |
| 67 | Confirmed true, fixed | Reminder updates accepted arbitrary user-driven status changes. | Added an explicit reminder transition map and regression coverage for invalid scheduled-to-read transitions and valid cancel/reschedule transitions. |

Verification:

- `.\.venv\Scripts\python.exe -m ruff check app\modules\applications\command_service.py tests\test_command_centre.py`
- `.\.venv\Scripts\python.exe -m pytest tests\test_command_centre.py -q`
- `.\.venv\Scripts\python.exe -m pytest -q`

## 2026-08-14 Checkpoint: Weaknesses 68-78

| ID | Status | Evidence | Remediation |
| --- | --- | --- | --- |
| 68 | Verified product-positioning constraint | The default provider is explicitly deterministic and returns server-composed evidence without model inference. | Provider naming and comments already present this as an evidence-template provider rather than unreviewed model reasoning. |
| 69 | Confirmed true, fixed | Assistant profile-match explanations used a local `_profile_match_reason()` heuristic separate from `MatchingService`. | Assistant profile reasoning now calls canonical `MatchingService.match_opportunity()` for selected opportunities. |
| 70 | Confirmed true, fixed | Assistant field/nationality profile matching used substring containment against prose eligibility text. | Removed substring profile matching and route profile reasoning through structured canonical matching. |
| 71 | Confirmed true, fixed | Assistant treated the mere presence of profile values as useful match signals for rule categories. | Assistant now reports canonical rule outcomes, missing information, and known eligibility failures from the matcher. |
| 72 | Confirmed true, improved | Assistant response confidence defaulted to medium for normal composed answers. | Response confidence now derives from canonical match confidence and warning presence when profile matching is used. |
| 73 | Confirmed true, partially improved | Retrieval is still keyword/SQL based. | Added data-layer candidate limiting before evidence-policy processing; full-text/hybrid retrieval remains future work. |
| 74 | Confirmed true, improved | Assistant retrieved candidates before applying final limits. | Unselected keyword retrieval now applies a SQL candidate limit before in-memory evidence-policy filtering. |
| 75 | Confirmed true, not fully fixed | Unsupported-intent detection remains phrase-based. | Not changed in this checkpoint; requires a broader capability-routing design. |
| 76 | Confirmed true, fixed | Frontend always sent `use_profile: true` for Assistant questions. | Added a visible `Use my profile for this question` checkbox and send profile data only when selected. |
| 77 | Confirmed true, fixed | Assistant confidence existed in the backend response but was not shown in the answer header. | Assistant UI now displays evidence confidence beside the answer. |
| 78 | Confirmed true, improved | Citations were grouped separately from claims. | Facts, possible-match reasons, and requirements now render inline citation links resolved through official citation IDs to source records. |

Verification:

- `.\.venv\Scripts\python.exe -m ruff check app\modules\assistant tests\test_assistant.py`
- `.\.venv\Scripts\python.exe -m pytest tests\test_assistant.py -q`
- `.\.venv\Scripts\python.exe -m pytest -q`
- `pnpm --dir frontend test`
- `pnpm --dir frontend build`
- `git diff --check`

## 2026-08-14 Checkpoint: Weaknesses 50-58

| ID | Status | Evidence | Remediation |
| --- | --- | --- | --- |
| 50 | Verified already fixed | Matcher already normalized scores by total available rule weight and had a regression test for variable rule counts. | No new scoring-normalization change required; the matcher version was bumped because later scoring semantics changed. |
| 51 | Confirmed true, fixed | Unknown structured, fallback, deadline, location, and funding outcomes awarded partial score. | Unknown outcomes now score zero and reduce confidence instead of improving fit. |
| 52 | Confirmed true, fixed | Eligibility, preference fit, deadline freshness, and funding preference were combined into one score. | Matching now separates eligibility fit, preference fit, profile completeness, evidence completeness, confidence factors, failures, mismatches, and missing information. |
| 53 | Confirmed true, fixed | Fallback unstructured eligibility could still produce a non-zero fit score while major requirements were not captured. | Unstructured fallback eligibility remains `unknown`; missing hard-rule information is reported as missing information rather than a strong conclusion. |
| 54 | Confirmed true, fixed | Fully satisfied captured structured rules returned `eligible`. | Successful captured-rule results now return `potentially_eligible` to avoid overstating provider decisions. |
| 55 | Confirmed true, fixed | Preference misses, such as destination-country mismatches, appeared in `failed_criteria`. | Compatibility `failed_criteria` now contains eligibility failures only; preference misses are reported in `preference_mismatches`. |
| 56 | Confirmed true, improved | Confidence was derived only from answered-rule count. | Confidence now includes rule coverage, source verification/freshness, structured-rule coverage, data-confidence flags, and missing-information factors. |
| 57 | Confirmed true, partially improved | Every public opportunity was evaluated and persisted for every match request. | Added degree-level candidate pre-filtering before rule evaluation and persistence so obvious non-candidates are not written into each evaluation run. |
| 58 | Confirmed true, fixed | CGPA was linearly converted between grading scales without documented equivalence. | CGPA comparisons now require matching scales; incompatible scales become uncertain and require documented equivalence. |

Verification:

- `.\.venv\Scripts\python.exe -m ruff check app\modules\matching tests\test_matching.py tests\test_browser_e2e.py`
- `.\.venv\Scripts\python.exe -m pytest tests\test_matching.py -q`
- `.\.venv\Scripts\python.exe -m pytest -q`
- `pnpm --dir frontend test`
- `pnpm --dir frontend build`
