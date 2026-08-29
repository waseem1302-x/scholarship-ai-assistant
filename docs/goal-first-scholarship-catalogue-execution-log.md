# Goal-first catalogue execution log

- timestamp: 2026-08-27T17:19:55.8926903+08:00
- branch: codex/phase1b2-crawlee-secure-bridge
- commit: 4635c998ff8dd8877ea67f511461c81d38951fcb

## Session: initial Milestone 0 checks

### Outcome
Read docs/gpt-5-mini-scholarship-catalogue-execution-prompt.md and ran git inspections.

### Commands run
- git status --porcelain=2 --branch
- git rev-parse --abbrev-ref HEAD
- git rev-parse HEAD
- git log -1 --pretty=format:%H%n%an%n%ad%n%s --date=iso
- git ls-files -m
- git ls-files --others --exclude-standard
- git ls-files --others -i --exclude-standard
- git diff --name-only
- git remote -v
- checked .catalogue-local/STOP and .env.catalogue.local presence

### Summary
- branch: codex/phase1b2-crawlee-secure-bridge
- commit: 4635c998ff8dd8877ea67f511461c81d38951fcb
- catalogue_stop: missing
- .env.catalogue.local: present

### Files of interest (short)
- modified tracked: see git ls-files -m
- untracked: see git ls-files --others --exclude-standard
- ignored: see git ls-files --others -i --exclude-standard

### Catalogue evidence
- model calls: 0

### Next action
- classify modified/untracked files and decide safe cleanup/wrapping steps.

---
- timestamp: 2026-08-27T17:21:49.0512903+08:00
- action: created .catalogue-local/STOP to enforce fail-safe worker stop

---
- timestamp: 2026-08-27T17:24:00.6464281+08:00
- branch: codex/phase1b2-crawlee-secure-bridge
- commit: 4635c998ff8dd8877ea67f511461c81d38951fcb


Counts:
- modified_tracked_count: 47
- untracked_count: 64
- local_secrets_count: 11
- intended_impl_count: 45
- generated_evidence_count: 2
- scratch_debug_count: 23
- malformed_docs_count: 18


Modified tracked files:

- .env.example
- .gitignore
- Dockerfile
- app/cli/process_catalogue_ingestion_runs.py
- app/cli/seed_verified_opportunities.py
- app/core/config.py
- app/modules/catalogue_ingestion/claim_provider.py
- app/modules/catalogue_ingestion/claim_resolution.py
- app/modules/catalogue_ingestion/claim_schemas.py
- app/modules/catalogue_ingestion/document_conversion.py
- app/modules/catalogue_ingestion/models.py
- app/modules/catalogue_ingestion/provider.py
- app/modules/catalogue_ingestion/repository.py
- app/modules/catalogue_ingestion/schemas.py
- app/modules/catalogue_ingestion/service.py
- app/modules/catalogue_ingestion/source_routing.py
- app/modules/opportunities/models.py
- app/modules/opportunities/repository.py
- app/modules/opportunities/routes.py
- app/modules/opportunities/schemas.py
- app/modules/opportunities/service.py
- app/modules/opportunities/source_monitor.py
- app/release_policy.json
- compose.yaml
- data/seed/verified_opportunities.json
- frontend/src/App.tsx
- frontend/src/features/admin/AdminPage.tsx
- frontend/src/features/admin/DirectUrlIngestionPanel.tsx
- frontend/src/features/admin/admin.test.ts
- frontend/src/features/admin/admin.ts
- frontend/src/features/admin/types.ts
- frontend/src/features/catalogue/OpportunityDetailPage.tsx
- frontend/src/features/catalogue/catalogue.ts
- frontend/src/features/catalogue/types.ts
- frontend/src/styles.css
- tests/conftest.py
- tests/test_browser_e2e.py
- tests/test_catalogue_ingestion.py
- tests/test_catalogue_ingestion_postgres.py
- tests/test_document_conversion.py
- tests/test_document_conversion_transport.py
- tests/test_frontend.py
- tests/test_matching.py
- tests/test_opportunities.py
- tests/test_seed_opportunities.py
- tests/test_source_monitor.py
- tests/test_source_routing.py

Untracked files:

- .azure/az.json
- .azure/az.sess
- .azure/azureProfile.json
- .azure/commandIndex.json
- .azure/commands/2026-08-26.21-15-10.rest.23400.log
- .azure/config
- .azure/extensionHelpIndex.json
- .azure/extensionIndex.json
- .azure/helpIndex.json
- .azure/logs/telemetry.log
- .azure/versionCheck.json
- .env.catalogue.example
- alembic/versions/20260825_0054_publication_readiness.py
- alembic/versions/20260825_0055_acquisition_bundle.py
- alembic/versions/20260825_0056_catalogue_identity.py
- app/cli/catalogue_preflight.py
- app/cli/probe_catalogue_ai_capability.py
- app/modules/catalogue_ingestion/acquisition_bundle.py
- app/modules/catalogue_ingestion/ai_contract.py
- app/modules/catalogue_ingestion/capability_probe.py
- app/modules/catalogue_ingestion/preflight.py
- app/modules/catalogue_ingestion/worker_safety.py
- app/modules/opportunities/catalogue_identity.py
- app/modules/opportunities/publication_readiness.py
- data/seed/private_priority_scholarship_candidates.v1.json
- docs/01-architecture-and-data-flow-audit.md
- docs/02-ai-scraping-and-extraction-audit.md
- docs/03-reliability-security-production-readiness-audit.md
- docs/04-terra-detailed-implementation-plan.md
- docs/audit-evidence-report-full.md
- docs/audit-evidence-report.md
- docs/catalogue-ai-capability-receipt.example.json
- docs/goal-first-scholarship-catalogue-execution-log.md
- docs/goal-first-scholarship-catalogue-go-live-plan.md
- docs/gpt-5-mini-scholarship-catalogue-execution-prompt.md
- docs/private-catalogue-seed-audit-2026-08-24.md
- docs/terra-5.6-catalogue-completion-plan.md
- docs/terra-5.6-phase-0-zero-cost-audit-2026-08-25.md
- docs/terra-5.6-phase-1-publication-readiness-2026-08-25.md
- docs/terra-5.6-phase-2-official-source-acquisition-2026-08-25.md
- docs/terra-5.6-phase-3-provenance-safe-extraction-2026-08-25.md
- docs/terra-5.6-phase-4-family-route-deduplication-2026-08-25.md
- docs/terra-5.6-phase-5-admin-review-experience-2026-08-25.md
- docs/terra-5.6-phase-6-local-runtime-wiring-2026-08-25.md
- docs/terra-5.6-phase-7-live-pilot-readiness-2026-08-25.md
- frontend/src/features/admin/AdminAcquiredReviewPage.tsx
- frontend/src/features/admin/AdminReviewPage.tsx
- frontend/src/features/catalogue/ScholarshipDetailView.tsx
- scripts/inspect_app_local_db.py
- scripts/list_db_info.py
- scripts/list_tables.py
- scripts/list_tables2.py
- scripts/run_probe_smoke.py
- tests/evidence_matrix.json
- tests/fixtures/catalogue_acquisition/three_family_source_bundles.v1.json
- tests/fixtures/catalogue_readiness/three_family_gold.v1.json
- tests/test_catalogue_acquisition_bundles.py
- tests/test_catalogue_capability_probe.py
- tests/test_catalogue_identity.py
- tests/test_catalogue_preflight.py
- tests/test_catalogue_readiness_gold.py
- tests/test_mapping.json
- tests/test_private_priority_seed.py
- tests/test_publication_readiness.py

Local secrets/runtime files:

- .azure/az.json
- .azure/az.sess
- .azure/azureProfile.json
- .azure/commandIndex.json
- .azure/commands/2026-08-26.21-15-10.rest.23400.log
- .azure/config
- .azure/extensionHelpIndex.json
- .azure/extensionIndex.json
- .azure/helpIndex.json
- .azure/logs/telemetry.log
- .azure/versionCheck.json

Intended implementation:

- app/cli/process_catalogue_ingestion_runs.py
- app/cli/seed_verified_opportunities.py
- app/core/config.py
- app/modules/catalogue_ingestion/claim_provider.py
- app/modules/catalogue_ingestion/claim_resolution.py
- app/modules/catalogue_ingestion/claim_schemas.py
- app/modules/catalogue_ingestion/document_conversion.py
- app/modules/catalogue_ingestion/models.py
- app/modules/catalogue_ingestion/provider.py
- app/modules/catalogue_ingestion/repository.py
- app/modules/catalogue_ingestion/schemas.py
- app/modules/catalogue_ingestion/service.py
- app/modules/catalogue_ingestion/source_routing.py
- app/modules/opportunities/models.py
- app/modules/opportunities/repository.py
- app/modules/opportunities/routes.py
- app/modules/opportunities/schemas.py
- app/modules/opportunities/service.py
- app/modules/opportunities/source_monitor.py
- app/release_policy.json
- frontend/src/App.tsx
- frontend/src/features/admin/AdminPage.tsx
- frontend/src/features/admin/DirectUrlIngestionPanel.tsx
- frontend/src/features/admin/admin.test.ts
- frontend/src/features/admin/admin.ts
- frontend/src/features/admin/types.ts
- frontend/src/features/catalogue/OpportunityDetailPage.tsx
- frontend/src/features/catalogue/catalogue.ts
- frontend/src/features/catalogue/types.ts
- frontend/src/styles.css
- alembic/versions/20260825_0054_publication_readiness.py
- alembic/versions/20260825_0055_acquisition_bundle.py
- alembic/versions/20260825_0056_catalogue_identity.py
- app/cli/catalogue_preflight.py
- app/cli/probe_catalogue_ai_capability.py
- app/modules/catalogue_ingestion/acquisition_bundle.py
- app/modules/catalogue_ingestion/ai_contract.py
- app/modules/catalogue_ingestion/capability_probe.py
- app/modules/catalogue_ingestion/preflight.py
- app/modules/catalogue_ingestion/worker_safety.py
- app/modules/opportunities/catalogue_identity.py
- app/modules/opportunities/publication_readiness.py
- frontend/src/features/admin/AdminAcquiredReviewPage.tsx
- frontend/src/features/admin/AdminReviewPage.tsx
- frontend/src/features/catalogue/ScholarshipDetailView.tsx

Generated evidence:

- data/seed/verified_opportunities.json
- data/seed/private_priority_scholarship_candidates.v1.json

Scratch/debug/test files:

- tests/conftest.py
- tests/test_browser_e2e.py
- tests/test_catalogue_ingestion.py
- tests/test_catalogue_ingestion_postgres.py
- tests/test_document_conversion.py
- tests/test_document_conversion_transport.py
- tests/test_frontend.py
- tests/test_matching.py
- tests/test_opportunities.py
- tests/test_seed_opportunities.py
- tests/test_source_monitor.py
- tests/test_source_routing.py
- tests/evidence_matrix.json
- tests/fixtures/catalogue_acquisition/three_family_source_bundles.v1.json
- tests/fixtures/catalogue_readiness/three_family_gold.v1.json
- tests/test_catalogue_acquisition_bundles.py
- tests/test_catalogue_capability_probe.py
- tests/test_catalogue_identity.py
- tests/test_catalogue_preflight.py
- tests/test_catalogue_readiness_gold.py
- tests/test_mapping.json
- tests/test_private_priority_seed.py
- tests/test_publication_readiness.py

Malformed docs:

- docs/01-architecture-and-data-flow-audit.md
- docs/02-ai-scraping-and-extraction-audit.md
- docs/03-reliability-security-production-readiness-audit.md
- docs/04-terra-detailed-implementation-plan.md
- docs/audit-evidence-report-full.md
- docs/audit-evidence-report.md
- docs/catalogue-ai-capability-receipt.example.json
- docs/gpt-5-mini-scholarship-catalogue-execution-prompt.md
- docs/private-catalogue-seed-audit-2026-08-24.md
- docs/terra-5.6-catalogue-completion-plan.md
- docs/terra-5.6-phase-0-zero-cost-audit-2026-08-25.md
- docs/terra-5.6-phase-1-publication-readiness-2026-08-25.md
- docs/terra-5.6-phase-2-official-source-acquisition-2026-08-25.md
- docs/terra-5.6-phase-3-provenance-safe-extraction-2026-08-25.md
- docs/terra-5.6-phase-4-family-route-deduplication-2026-08-25.md
- docs/terra-5.6-phase-5-admin-review-experience-2026-08-25.md
- docs/terra-5.6-phase-6-local-runtime-wiring-2026-08-25.md
- docs/terra-5.6-phase-7-live-pilot-readiness-2026-08-25.md

- test_run_started: 2026-08-27T18:56:52.1867011+08:00
- test_command: python -m pytest -q tests/test_catalogue_ingestion.py tests/test_document_conversion.py

- test_run_completed: 2026-08-27T18:56:52.4770863+08:00
- pytest_exit_code: 1
- pytest_output: |
  C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe: No module named pytest

- py_compile_run_started: 2026-08-27T18:59:59.2663247+08:00
- py_compile_command: python -m py_compile <tracked .py files>
- compiling: alembic/env.py
- compiling: alembic/versions/20260718_0001_auth.py
- compiling: alembic/versions/20260722_0002_opportunity_catalog.py
- compiling: alembic/versions/20260722_0003_student_profiles.py
- compiling: alembic/versions/20260722_0004_saved_opportunities.py
- compiling: alembic/versions/20260811_0005_cycles_and_eligibility_rules.py
- compiling: alembic/versions/20260811_0006_account_security.py
- compiling: alembic/versions/20260812_0007_source_excerpts.py
- compiling: alembic/versions/20260812_0008_match_evaluation_records.py
- compiling: alembic/versions/20260812_0009_structured_eligibility_completion.py
- compiling: alembic/versions/20260812_0010_application_command_centre.py
- compiling: alembic/versions/20260812_0011_citation_first_assistant.py
- compiling: alembic/versions/20260812_0012_assistant_safety_controls.py
- compiling: alembic/versions/20260812_0013_document_lab_foundation.py
- compiling: alembic/versions/20260813_0014_scholarship_community.py
- compiling: alembic/versions/20260813_0015_phase9_beta_invitations.py
- compiling: alembic/versions/20260813_0016_phase9_webauthn.py
- compiling: alembic/versions/20260813_0017_phase9_beta_legal_acceptance.py
- compiling: alembic/versions/20260813_0018_phase9_operational_job_health.py
- compiling: alembic/versions/20260813_0019_beta_invitation_reservations.py
- compiling: alembic/versions/20260813_0020_user_token_version.py
- compiling: alembic/versions/20260813_0021_admin_step_up_scope.py
- compiling: alembic/versions/20260813_0022_passkey_lifecycle.py
- compiling: alembic/versions/20260813_0023_catalogue_window_projection.py
- compiling: alembic/versions/20260814_0024_review_queue_indexes.py
- compiling: alembic/versions/20260814_0025_canonical_duplicate_suggestions.py
- compiling: alembic/versions/20260814_0026_funding_coverage_components.py
- compiling: alembic/versions/20260814_0027_source_hash_algorithms.py
- compiling: alembic/versions/20260814_0028_structured_catalogue_filters.py
- compiling: alembic/versions/20260814_0029_profile_canonical_versioning.py
- compiling: alembic/versions/20260814_0030_application_command_centre_hardening.py
- compiling: alembic/versions/20260814_0031_document_lab_consistency_metadata.py
- compiling: alembic/versions/20260814_0032_community_identity_and_counts.py
- compiling: alembic/versions/20260814_0033_operational_run_history.py
- compiling: alembic/versions/20260814_0034_audit_log_integrity_hash.py
- compiling: alembic/versions/20260814_0035_append_only_audit_history.py
- compiling: alembic/versions/20260814_0036_tenant_row_level_security.py
- compiling: alembic/versions/20260815_0037_catalogue_ingestion_pipeline.py
- compiling: alembic/versions/20260817_0038_scholarship_graph_schema.py
- compiling: alembic/versions/20260817_0039_scholarship_graph_evidence.py
- compiling: alembic/versions/20260817_0040_relationship_classification.py
- compiling: alembic/versions/20260820_0041_catalogue_discovery_foundation.py
- compiling: alembic/versions/20260822_0042_direct_url_source_artifacts.py
- compiling: alembic/versions/20260822_0043_graph_precision.py
- compiling: alembic/versions/20260823_0044_catalogue_source_roles.py
- compiling: alembic/versions/20260824_0045_catalogue_ingestion_run_queue.py
- compiling: alembic/versions/20260824_0046_catalogue_evidence_blocks.py
- compiling: alembic/versions/20260824_0047_catalogue_source_routing.py
- compiling: alembic/versions/20260824_0048_assistant_quota_reservations.py
- compiling: alembic/versions/20260824_0049_source_monitor_fencing.py
- compiling: alembic/versions/20260824_0050_document_job_leases.py
- compiling: alembic/versions/20260824_0051_document_deletion_jobs.py
- compiling: alembic/versions/20260824_0052_catalogue_review_proposals.py
- compiling: alembic/versions/20260824_0053_catalogue_routing_authority.py
- compiling: app/__init__.py
- compiling: app/api/__init__.py
- compiling: app/api/router.py
- compiling: app/cli/__init__.py
- compiling: app/cli/bootstrap_demo.py
- compiling: app/cli/create_admin.py
- compiling: app/cli/dispatch_document_jobs.py
- compiling: app/cli/dispatch_reminders.py
- compiling: app/cli/evaluate_catalogue_extraction.py
- compiling: app/cli/ingest_catalogue_seeds.py
- compiling: app/cli/monitor_sources.py
- compiling: app/cli/process_catalogue_ingestion_runs.py
- compiling: app/cli/reconcile_opportunity_lifecycles.py
- compiling: app/cli/release_preflight.py
- compiling: app/cli/run_retention.py
- compiling: app/cli/seed_verified_opportunities.py
- compiling: app/core/__init__.py
- compiling: app/core/config.py
- compiling: app/core/email.py
- compiling: app/core/errors.py
- compiling: app/core/feature_gates.py
- compiling: app/core/health.py
- compiling: app/core/http_security.py
- compiling: app/core/middleware.py
- compiling: app/core/observability.py
- compiling: app/core/password_security.py
- compiling: app/core/proxy_headers.py
- compiling: app/core/rate_limit.py
- compiling: app/core/security.py
- compiling: app/db/__init__.py
- compiling: app/db/base.py
- compiling: app/db/models.py
- compiling: app/db/session.py
- compiling: app/main.py
- compiling: app/modules/__init__.py
- compiling: app/modules/applications/__init__.py
- compiling: app/modules/applications/command_repository.py
- compiling: app/modules/applications/command_routes.py
- compiling: app/modules/applications/command_service.py
- compiling: app/modules/applications/deadlines.py
- compiling: app/modules/applications/models.py
- compiling: app/modules/applications/repository.py
- compiling: app/modules/applications/routes.py
- compiling: app/modules/applications/schemas.py
- compiling: app/modules/applications/service.py
- compiling: app/modules/assistant/__init__.py
- compiling: app/modules/assistant/models.py
- compiling: app/modules/assistant/provider.py
- compiling: app/modules/assistant/routes.py
- compiling: app/modules/assistant/schemas.py
- compiling: app/modules/assistant/service.py
- compiling: app/modules/auth/__init__.py
- compiling: app/modules/auth/dependencies.py
- compiling: app/modules/auth/models.py
- compiling: app/modules/auth/repository.py
- compiling: app/modules/auth/routes.py
- compiling: app/modules/auth/schemas.py
- compiling: app/modules/auth/service.py
- compiling: app/modules/auth/webauthn_service.py
- compiling: app/modules/beta/__init__.py
- compiling: app/modules/beta/models.py
- compiling: app/modules/beta/routes.py
- compiling: app/modules/beta/schemas.py
- compiling: app/modules/beta/service.py
- compiling: app/modules/catalogue_ingestion/__init__.py
- compiling: app/modules/catalogue_ingestion/acquisition_contract.py
- compiling: app/modules/catalogue_ingestion/azure_discovery_provider.py
- compiling: app/modules/catalogue_ingestion/claim_provider.py
- compiling: app/modules/catalogue_ingestion/claim_resolution.py
- compiling: app/modules/catalogue_ingestion/claim_schemas.py
- compiling: app/modules/catalogue_ingestion/classification.py
- compiling: app/modules/catalogue_ingestion/crawlee_static_acquirer.py
- compiling: app/modules/catalogue_ingestion/crawler.py
- compiling: app/modules/catalogue_ingestion/discovery.py
- compiling: app/modules/catalogue_ingestion/discovery_binding.py
- compiling: app/modules/catalogue_ingestion/discovery_models.py
- compiling: app/modules/catalogue_ingestion/discovery_officiality.py
- compiling: app/modules/catalogue_ingestion/discovery_promotion.py
- compiling: app/modules/catalogue_ingestion/discovery_provider.py
- compiling: app/modules/catalogue_ingestion/discovery_repository.py
- compiling: app/modules/catalogue_ingestion/discovery_service.py
- compiling: app/modules/catalogue_ingestion/document_conversion.py
- compiling: app/modules/catalogue_ingestion/document_conversion_transport.py
- compiling: app/modules/catalogue_ingestion/document_conversion_worker.py
- compiling: app/modules/catalogue_ingestion/evaluation.py
- compiling: app/modules/catalogue_ingestion/evidence.py
- compiling: app/modules/catalogue_ingestion/evidence_acquirer.py
- compiling: app/modules/catalogue_ingestion/evidence_blocks.py
- compiling: app/modules/catalogue_ingestion/graph_materializer.py
- compiling: app/modules/catalogue_ingestion/metrics.py
- compiling: app/modules/catalogue_ingestion/models.py
- compiling: app/modules/catalogue_ingestion/provider.py
- compiling: app/modules/catalogue_ingestion/repository.py
- compiling: app/modules/catalogue_ingestion/routes.py
- compiling: app/modules/catalogue_ingestion/safe_multi_url_session.py
- compiling: app/modules/catalogue_ingestion/schemas.py
- compiling: app/modules/catalogue_ingestion/seed_parser.py
- compiling: app/modules/catalogue_ingestion/service.py
- compiling: app/modules/catalogue_ingestion/source_routing.py
- compiling: app/modules/catalogue_ingestion/sources.py
- compiling: app/modules/catalogue_ingestion/url_policy.py
- compiling: app/modules/catalogue_ingestion/validation.py
- compiling: app/modules/community/__init__.py
- compiling: app/modules/community/models.py
- compiling: app/modules/community/routes.py
- compiling: app/modules/community/schemas.py
- compiling: app/modules/community/service.py
- compiling: app/modules/document_lab/__init__.py
- compiling: app/modules/document_lab/crypto.py
- compiling: app/modules/document_lab/extraction.py
- compiling: app/modules/document_lab/models.py
- compiling: app/modules/document_lab/process_sandbox.py
- compiling: app/modules/document_lab/provider.py
- compiling: app/modules/document_lab/routes.py
- compiling: app/modules/document_lab/scanner.py
- compiling: app/modules/document_lab/schemas.py
- compiling: app/modules/document_lab/service.py
- compiling: app/modules/document_lab/storage.py
- compiling: app/modules/document_lab/validation.py
- compiling: app/modules/matching/__init__.py
- compiling: app/modules/matching/models.py
- compiling: app/modules/matching/repository.py
- compiling: app/modules/matching/routes.py
- compiling: app/modules/matching/schemas.py
- compiling: app/modules/matching/service.py
- compiling: app/modules/operations/__init__.py
- compiling: app/modules/operations/models.py
- compiling: app/modules/operations/service.py
- compiling: app/modules/opportunities/__init__.py
- compiling: app/modules/opportunities/evidence_models.py
- compiling: app/modules/opportunities/evidence_policy.py
- compiling: app/modules/opportunities/graph_models.py
- compiling: app/modules/opportunities/graph_query.py
- compiling: app/modules/opportunities/graph_schemas.py
- compiling: app/modules/opportunities/lifecycle.py
- compiling: app/modules/opportunities/models.py
- compiling: app/modules/opportunities/repository.py
- compiling: app/modules/opportunities/routes.py
- compiling: app/modules/opportunities/schemas.py
- compiling: app/modules/opportunities/service.py
- compiling: app/modules/opportunities/source_monitor.py
- compiling: app/modules/profiles/__init__.py
- compiling: app/modules/profiles/models.py
- compiling: app/modules/profiles/repository.py
- compiling: app/modules/profiles/routes.py
- compiling: app/modules/profiles/schemas.py
- compiling: app/modules/profiles/service.py
- compiling: scripts/phase9_load_test.py
- compiling: scripts/staging_smoke.py
- compiling: scripts/validate_budget_currency.py
- compiling: scripts/verify_docling_artifacts.py
- compiling: tests/conftest.py
- compiling: tests/test_alias_resolution.py
- compiling: tests/test_application_deadlines.py
- compiling: tests/test_applications.py
- compiling: tests/test_assistant.py
- compiling: tests/test_assistant_browser_e2e.py
- compiling: tests/test_assistant_quota_postgres.py
- compiling: tests/test_auth.py
- compiling: tests/test_auth_rate_limit_routes.py
- compiling: tests/test_auth_session_security.py
- compiling: tests/test_azure_discovery_provider.py
- compiling: tests/test_azure_proxy_headers.py
- compiling: tests/test_beta.py
- compiling: tests/test_bounded_crawler_core.py
- compiling: tests/test_bounded_crawler_ingestion.py
- compiling: tests/test_bounded_crawler_safe_fetcher.py
- compiling: tests/test_browser_e2e.py
- compiling: tests/test_budget_currency.py
- compiling: tests/test_catalogue_discovery.py
- compiling: tests/test_catalogue_discovery_binding.py
- compiling: tests/test_catalogue_discovery_config.py
- compiling: tests/test_catalogue_discovery_migration.py
- compiling: tests/test_catalogue_discovery_officiality.py
- compiling: tests/test_catalogue_discovery_postgres.py
- compiling: tests/test_catalogue_discovery_promotion.py
- compiling: tests/test_catalogue_discovery_urls.py
- compiling: tests/test_catalogue_evidence_blocks.py
- compiling: tests/test_catalogue_ingestion.py
- compiling: tests/test_catalogue_ingestion_postgres.py
- compiling: tests/test_catalogue_ingestion_queue.py
- compiling: tests/test_catalogue_source_snapshot_ledger.py
- compiling: tests/test_catalogue_window_query.py
- compiling: tests/test_classification_decisions.py
- compiling: tests/test_command_centre.py
- compiling: tests/test_community.py
- compiling: tests/test_complete_acquisition_contract.py
- compiling: tests/test_crawlee_static_acquirer.py
- compiling: tests/test_delivery_policy.py
- compiling: tests/test_docling_artifacts.py
- compiling: tests/test_document_conversion.py
- compiling: tests/test_document_conversion_transport.py
- compiling: tests/test_document_lab_foundation.py
- compiling: tests/test_document_lab_intake.py
- compiling: tests/test_document_process_sandbox.py
- compiling: tests/test_evidence_acquirer.py
- compiling: tests/test_feature_gates.py
- compiling: tests/test_frontend.py
- compiling: tests/test_graph_fact_inheritance.py
- compiling: tests/test_independence_gate.py
- compiling: tests/test_lifecycle_reconciliation.py
- compiling: tests/test_matching.py
- compiling: tests/test_middleware_composition.py
- compiling: tests/test_migrations.py
- compiling: tests/test_operations.py
- compiling: tests/test_opportunities.py
- compiling: tests/test_phase1_lifecycle.py
- compiling: tests/test_phase1_security.py
- compiling: tests/test_phase9_document_storage.py
- compiling: tests/test_phase9_rate_limit.py
- compiling: tests/test_postgres_audit_security.py
- compiling: tests/test_postgres_tenant_isolation.py
- compiling: tests/test_pr4_azure_wiring.py
- compiling: tests/test_profiles.py
- compiling: tests/test_redis_rate_limit_integration.py
- compiling: tests/test_relationship_classifier.py
- compiling: tests/test_relationship_classifier_migration.py
- compiling: tests/test_relationship_regression_fixtures.py
- compiling: tests/test_release_policy.py
- compiling: tests/test_safe_multi_url_session.py
- compiling: tests/test_scholarship_graph_evidence.py
- compiling: tests/test_scholarship_graph_migration.py
- compiling: tests/test_scholarship_graph_pr0_boundary.py
- compiling: tests/test_scholarship_graph_schema.py
- compiling: tests/test_seed_opportunities.py
- compiling: tests/test_source_monitor.py
- compiling: tests/test_source_routing.py
- py_compile_run_completed: 2026-08-27T19:00:23.3052224+08:00
- py_compile_compiled_count: 281
- py_compile_failed_count: 0

- pytest_install_flow_started: 2026-08-27T19:05:24.7326226+08:00
- install_command: python -m pip install --user pytest
- install_exit_code: 0
- install_output: |
  Collecting pytest
    Using cached pytest-9.1.1-py3-none-any.whl.metadata (7.6 kB)
  Collecting colorama>=0.4 (from pytest)
    Using cached colorama-0.4.6-py2.py3-none-any.whl.metadata (17 kB)
  Collecting iniconfig>=1.0.1 (from pytest)
    Using cached iniconfig-2.3.0-py3-none-any.whl.metadata (2.5 kB)
  Collecting packaging>=22 (from pytest)
    Using cached packaging-26.3-py3-none-any.whl.metadata (3.5 kB)
  Collecting pluggy<2,>=1.5 (from pytest)
    Using cached pluggy-1.6.0-py3-none-any.whl.metadata (4.8 kB)
  Collecting pygments>=2.7.2 (from pytest)
    Downloading pygments-2.21.0-py3-none-any.whl.metadata (2.5 kB)
  Using cached pytest-9.1.1-py3-none-any.whl (386 kB)
  Using cached pluggy-1.6.0-py3-none-any.whl (20 kB)
  Using cached colorama-0.4.6-py2.py3-none-any.whl (25 kB)
  Using cached iniconfig-2.3.0-py3-none-any.whl (7.5 kB)
  Using cached packaging-26.3-py3-none-any.whl (129 kB)
  Downloading pygments-2.21.0-py3-none-any.whl (1.3 MB)
     ---------------------------------------- 1.3/1.3 MB 3.0 MB/s  0:00:00
  Installing collected packages: pygments, pluggy, packaging, iniconfig, colorama, pytest
    WARNING: The script pygmentize.exe is installed in 'C:\Users\Admin\AppData\Roaming\Python\Python314\Scripts' which is not on PATH.
    Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
    WARNING: The scripts py.test.exe and pytest.exe are installed in 'C:\Users\Admin\AppData\Roaming\Python\Python314\Scripts' which is not on PATH.
    Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
  
  Successfully installed colorama-0.4.6 iniconfig-2.3.0 packaging-26.3 pluggy-1.6.0 pygments-2.21.0 pytest-9.1.1
- pytest_run_started: 2026-08-27T19:05:32.0899264+08:00
- pytest_command: python -m pytest -q tests/test_catalogue_ingestion.py tests/test_document_conversion.py
- pytest_exit_code: 4
- pytest_output: |
  ImportError while loading conftest 'C:\Users\Admin\Downloads\Scholarship AI Assistant\tests\conftest.py'.
  tests\conftest.py:8: in <module>
      from fastapi.testclient import TestClient
  E   ModuleNotFoundError: No module named 'fastapi'
- pytest_install_flow_completed: 2026-08-27T19:05:32.6260289+08:00

- venv_checked: .venv\Scripts\python.exe
- venv_python_version: Python 3.12.13
- pytest_venv_run_started: 2026-08-27T19:16:04.7004766+08:00
- pytest_venv_command: ".venv\Scripts\python.exe -m pytest -q tests/test_catalogue_ingestion.py tests/test_document_conversion.py"
- pytest_venv_exit_code: 0
- pytest_venv_output: |
  ........................................................................ [ 73%]
  ..........................                                               [100%]
  ============================== warnings summary ===============================
  .venv\Lib\site-packages\fastapi\testclient.py:1
    C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
      from starlette.testclient import TestClient as TestClient  # noqa
  
  .venv\Lib\site-packages\_pytest\cacheprovider.py:469
    C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Lib\site-packages\_pytest\cacheprovider.py:469: PytestCacheWarning: cache could not write path C:\Users\Admin\Downloads\Scholarship AI Assistant\.pytest_cache\v\cache\nodeids: [Errno 13] Permission denied: 'C:\\Users\\Admin\\Downloads\\Scholarship AI Assistant\\.pytest_cache\\v\\cache\\nodeids'
      config.cache.set("cache/nodeids", sorted(self.cached_nodeids))
  
  -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
- pytest_venv_run_completed: 2026-08-27T19:16:18.0057533+08:00

- extra_tests_run: tests/test_worker_preflight.py tests/test_catalogue_ingestion.py tests/test_document_conversion.py
- extra_pytest_exit: 0
- extra_pytest_output: |
  ........................................................................ [ 72%]
  ...........................                                              [100%]
  ============================== warnings summary ===============================
  .venv\Lib\site-packages\fastapi\testclient.py:1
    C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
      from starlette.testclient import TestClient as TestClient  # noqa
  
  .venv\Lib\site-packages\_pytest\cacheprovider.py:469
    C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Lib\site-packages\_pytest\cacheprovider.py:469: PytestCacheWarning: cache could not write path C:\Users\Admin\Downloads\Scholarship AI Assistant\.pytest_cache\v\cache\nodeids: [Errno 13] Permission denied: 'C:\\Users\\Admin\\Downloads\\Scholarship AI Assistant\\.pytest_cache\\v\\cache\\nodeids'
      config.cache.set("cache/nodeids", sorted(self.cached_nodeids))
  
  -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

- ruff_run_started: 2026-08-27T19:20:54.9102604+08:00
- ruff_exit: 1
- ruff_output: |
  I001 [*] Import block is un-sorted or un-formatted
    --> app\cli\process_catalogue_ingestion_runs.py:3:1
     |
   1 |   """Claim and process durable catalogue ingestion runs outside HTTP requests."""
   2 |
   3 | / import argparse
   4 | | import json
   5 | | import os
   6 | | import socket
   7 | |
   8 | | from app.core.config import get_settings
   9 | | from app.db.session import SystemSessionLocal
  10 | | from app.modules.catalogue_ingestion.service import CatalogueIngestionService
  11 | | from app.modules.catalogue_ingestion.worker_safety import kill_switch_active
  12 | | from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  13 | | from app.modules.operations.service import OperationalJobService
     | |________________________________________________________________^
  help: Organize imports
     |
  9  | from app.db.session import SystemSessionLocal
  10 + from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  11 | from app.modules.catalogue_ingestion.service import CatalogueIngestionService
  12 | from app.modules.catalogue_ingestion.worker_safety import kill_switch_active
     - from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  13 | from app.modules.operations.service import OperationalJobService
     |
  
  SIM105 Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`
    --> app\cli\process_catalogue_ingestion_runs.py:45:13
     |
  43 |           if preflight_report.get("status") != "ready":
  44 |               print("Catalogue preflight blocked ingestion. Report summary:")
  45 | /             try:
  46 | |                 print(json.dumps(preflight_report.get("checks", {}), indent=2, sort_keys=True))
  47 | |             except Exception:
  48 | |                 pass
     | |____________________^
  49 |               stopped = True
     |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(Exception): ...`
  
  SIM105 Use `contextlib.suppress(FileNotFoundError)` instead of `try`-`except`-`pass`
     --> app\modules\catalogue_ingestion\capability_probe.py:474:9
      |
  472 |           os.replace(temporary_name, path)
  473 |       except BaseException:
  474 | /         try:
  475 | |             os.unlink(temporary_name)
  476 | |         except FileNotFoundError:
  477 | |             pass
      | |________________^
  478 |           raise
      |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(FileNotFoundError): ...`
  
  E401 [*] Multiple imports on one line
   --> scripts\inspect_app_local_db.py:1:1
    |
  1 | import sqlite3,os
    | ^^^^^^^^^^^^^^^^^
  2 | DB='app-local.db'
  3 | if not os.path.exists(DB):
    |
  help: Split imports
    |
    - ﻿import sqlite3,os
  1 + ﻿import sqlite3
  2 + import os
  3 | DB='app-local.db'
    |
  
  I001 [*] Import block is un-sorted or un-formatted
   --> scripts\inspect_app_local_db.py:1:1
    |
  1 | import sqlite3,os
    | ^^^^^^^^^^^^^^^^^
  2 | DB='app-local.db'
  3 | if not os.path.exists(DB):
    |
  help: Organize imports
    |
    - ﻿import sqlite3,os
  1 + ﻿import os
  2 + import sqlite3
  3 +
  4 | DB='app-local.db'
    |
  
  UP031 Use format specifiers instead of percent format
    --> scripts\inspect_app_local_db.py:18:25
     |
  16 |         if t in tables:
  17 |             print('\nTABLE',t)
  18 |             cur.execute("PRAGMA table_info('%s')"%t)
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  19 |             cols=[r[1] for r in cur.fetchall()]
  20 |             print(' COLUMNS:',cols)
     |
  help: Replace with format specifiers
  
  E501 Line too long (126 > 100)
    --> scripts\inspect_app_local_db.py:24:101
     |
  22 |                 # build a safe select
  23 |                 sel_cols=[]
  24 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
  25 |                     if c in cols: sel_cols.append(c)
  26 |                 if not sel_cols:
     |
  
  E701 Multiple statements on one line (colon)
    --> scripts\inspect_app_local_db.py:25:33
     |
  23 |                 sel_cols=[]
  24 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  25 |                     if c in cols: sel_cols.append(c)
     |                                 ^
  26 |                 if not sel_cols:
  27 |                     sel='*'
     |
  
  SIM108 Use ternary operator `sel = '*' if not sel_cols else ','.join(sel_cols)` instead of `if`-`else`-block
    --> scripts\inspect_app_local_db.py:26:17
     |
  24 |                   for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  25 |                       if c in cols: sel_cols.append(c)
  26 | /                 if not sel_cols:
  27 | |                     sel='*'
  28 | |                 else:
  29 | |                     sel=','.join(sel_cols)
     | |__________________________________________^
  30 |                   cur.execute(f"SELECT {sel} FROM {t} ORDER BY ROWID DESC LIMIT 5")
  31 |                   rows=cur.fetchall()
     |
  help: Replace `if`-`else`-block with `sel = '*' if not sel_cols else ','.join(sel_cols)`
  
  E401 [*] Multiple imports on one line
   --> scripts\list_db_info.py:1:1
    |
  1 | import sqlite3,sys,os
    | ^^^^^^^^^^^^^^^^^^^^^
  2 | files = ['app-local.db','scholarship.db','e2e-test.db']
  3 | for f in files:
    |
  help: Split imports
    |
    - ﻿import sqlite3,sys,os
  1 + ﻿import sqlite3
  2 + import sys
  3 + import os
  4 | files = ['app-local.db','scholarship.db','e2e-test.db']
    |
  
  I001 [*] Import block is un-sorted or un-formatted
   --> scripts\list_db_info.py:1:1
    |
  1 | import sqlite3,sys,os
    | ^^^^^^^^^^^^^^^^^^^^^
  2 | files = ['app-local.db','scholarship.db','e2e-test.db']
  3 | for f in files:
    |
  help: Organize imports
    |
    - ﻿import sqlite3,sys,os
  1 + ﻿import os
  2 + import sqlite3
  3 + import sys
  4 +
  5 | files = ['app-local.db','scholarship.db','e2e-test.db']
    |
  
  F401 [*] `sys` imported but unused
   --> scripts\list_db_info.py:1:16
    |
  1 | import sqlite3,sys,os
    |                ^^^
  2 | files = ['app-local.db','scholarship.db','e2e-test.db']
  3 | for f in files:
    |
  help: Remove unused import: `sys`
    |
    - ﻿import sqlite3,sys,os
  1 + ﻿import sqlite3,os
  2 | files = ['app-local.db','scholarship.db','e2e-test.db']
    |
  
  E501 Line too long (137 > 100)
    --> scripts\list_db_info.py:15:101
     |
  13 | …
  14 | …
  15 | …quest_id','provider_response_id','response_id','request_id','receipt','capability']):
     |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  16 | …
  17 | …p().replace('\n',' '))
     |
  
  E401 [*] Multiple imports on one line
   --> scripts\list_tables.py:1:1
    |
  1 | import sqlite3,os
    | ^^^^^^^^^^^^^^^^^
  2 | DB='app-local.db'
  3 | if not os.path.exists(DB):
    |
  help: Split imports
    |
    - ﻿import sqlite3,os
  1 + ﻿import sqlite3
  2 + import os
  3 | DB='app-local.db'
    |
  
  I001 [*] Import block is un-sorted or un-formatted
   --> scripts\list_tables.py:1:1
    |
  1 | import sqlite3,os
    | ^^^^^^^^^^^^^^^^^
  2 | DB='app-local.db'
  3 | if not os.path.exists(DB):
    |
  help: Organize imports
    |
    - ﻿import sqlite3,os
  1 + ﻿import os
  2 + import sqlite3
  3 +
  4 | DB='app-local.db'
    |
  
  E401 [*] Multiple imports on one line
   --> scripts\list_tables2.py:1:1
    |
  1 | import sqlite3,os
    | ^^^^^^^^^^^^^^^^^
  2 | for DB in ['scholarship.db','e2e-test.db']:
  3 |     if not os.path.exists(DB):
    |
  help: Split imports
    |
    - ﻿import sqlite3,os
  1 + ﻿import sqlite3
  2 + import os
  3 | for DB in ['scholarship.db','e2e-test.db']:
    |
  
  I001 [*] Import block is un-sorted or un-formatted
   --> scripts\list_tables2.py:1:1
    |
  1 | import sqlite3,os
    | ^^^^^^^^^^^^^^^^^
  2 | for DB in ['scholarship.db','e2e-test.db']:
  3 |     if not os.path.exists(DB):
    |
  help: Organize imports
    |
    - ﻿import sqlite3,os
  1 + ﻿import os
  2 + import sqlite3
  3 +
  4 | for DB in ['scholarship.db','e2e-test.db']:
    |
  
  I001 [*] Import block is un-sorted or un-formatted
    --> scripts\run_probe_smoke.py:1:1
     |
   1 | / from pathlib import Path
   2 | | import json
   3 | | import io
   4 | | import uuid
   5 | | from datetime import UTC, datetime
   6 | | from decimal import Decimal
   7 | | from types import SimpleNamespace
   8 | |
   9 | | from app.core.config import Settings
  10 | | from app.modules.catalogue_ingestion.capability_probe import (
  11 | |     run_capability_probe,
  12 | |     persist_capability_probe_outcome,
  13 | | )
     | |_^
  14 |
  15 |   class FakeCredential:
     |
  help: Organize imports
     |
     - ﻿from pathlib import Path
  1  + ﻿import io
  2  | import json
     - import io
  3  | import uuid
  4  | from datetime import UTC, datetime
  5  | from decimal import Decimal
  6  + from pathlib import Path
  7  | from types import SimpleNamespace
  8  |
  9  | from app.core.config import Settings
  10 | from app.modules.catalogue_ingestion.capability_probe import (
  11 +     persist_capability_probe_outcome,
  12 |     run_capability_probe,
     -     persist_capability_probe_outcome,
  13 | )
  14 |
  15 +
  16 | class FakeCredential:
     |
  
  E501 Line too long (130 > 100)
    --> scripts\run_probe_smoke.py:54:101
     |
  54 | def response_payload(*, finish_reason: str = "stop", refusal: str | None = None, content: str | None = None) -> dict[str, object]:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  55 |     valid_content = json.dumps(
  56 |         {
     |
  
  E701 Multiple statements on one line (colon)
     --> scripts\run_probe_smoke.py:102:18
      |
  100 | # Persist to temp paths under current dir
  101 | p = Path('tmp_probe_test')
  102 | if not p.exists(): p.mkdir()
      |                  ^
  103 | try:
  104 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
      |
  
  E501 Line too long (133 > 100)
     --> scripts\run_probe_smoke.py:104:101
      |
  102 | if not p.exists(): p.mkdir()
  103 | try:
  104 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
      |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  105 |     print('Wrote evidence to', (p / 'capability-evidence.json').absolute())
  106 |     print('evidence failure_category:', json.loads((p / 'capability-evidence.json').read_text())['failure_category'])
      |
  
  E501 Line too long (117 > 100)
     --> scripts\run_probe_smoke.py:106:101
      |
  104 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
  105 |     print('Wrote evidence to', (p / 'capability-evidence.json').absolute())
  106 |     print('evidence failure_category:', json.loads((p / 'capability-evidence.json').read_text())['failure_category'])
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  107 | finally:
  108 |     pass
      |
  
  E501 Line too long (104 > 100)
     --> tests\test_catalogue_capability_probe.py:134:101
      |
  132 |             {
  133 |                 **response_payload(finish_reason="content_filter"),
  134 |                 "prompt_filter_results": [{"content_filter_results": {"violence": {"filtered": True}}}],
      |                                                                                                     ^^^^
  135 |             },
  136 |             "content_filter",
      |
  
  E501 Line too long (117 > 100)
     --> tests\test_catalogue_capability_probe.py:202:101
      |
  201 | def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  202 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  203 |     from pathlib import Path
  204 |     import os
      |
  
  I001 [*] Import block is un-sorted or un-formatted
     --> tests\test_catalogue_capability_probe.py:203:5
      |
  201 |   def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  202 |       """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
  203 | /     from pathlib import Path
  204 | |     import os
      | |_____________^
  205 |
  206 |       # Create a failing outcome (length) to get a sanitized evidence payload
      |
  help: Organize imports
      |
  202 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
  203 +     import os
  204 |     from pathlib import Path
      -     import os
  205 |
      |
  
  I001 [*] Import block is un-sorted or un-formatted
   --> tests\test_worker_preflight.py:1:1
    |
  1 | / import sys
  2 | | import builtins
  3 | |
  4 | | import pytest
  5 | |
  6 | | import app.cli.process_catalogue_ingestion_runs as proc
    | |_______________________________________________________^
  help: Organize imports
    |
    - ﻿import sys
    - import builtins
  1 + ﻿import builtins
  2 + import sys
  3 |
    |
  
  F401 [*] `sys` imported but unused
   --> tests\test_worker_preflight.py:1:8
    |
  1 | import sys
    |        ^^^
  2 | import builtins
    |
  help: Remove unused import: `sys`
    |
    - ﻿import sys
    - import builtins
  1 + ﻿import builtins
  2 |
    |
  
  F401 [*] `builtins` imported but unused
   --> tests\test_worker_preflight.py:2:8
    |
  1 | import sys
  2 | import builtins
    |        ^^^^^^^^
  3 |
  4 | import pytest
    |
  help: Remove unused import: `builtins`
    |
  1 | ﻿import sys
    - import builtins
  2 |
    |
  
  F401 [*] `pytest` imported but unused
   --> tests\test_worker_preflight.py:4:8
    |
  2 | import builtins
  3 |
  4 | import pytest
    |        ^^^^^^
  5 |
  6 | import app.cli.process_catalogue_ingestion_runs as proc
    |
  help: Remove unused import: `pytest`
    |
  3 |
    - import pytest
  4 |
    |
  
  E501 Line too long (110 > 100)
    --> tests\test_worker_preflight.py:11:101
     |
   9 | def test_process_stops_on_preflight_block(monkeypatch, capsys):
  10 |     # Make preflight report blocked
  11 |     monkeypatch.setattr(proc, 'run_catalogue_preflight', lambda settings: {'status': 'blocked', 'checks': {}})
     |                                                                                                     ^^^^^^^^^^
  12 |     # Ensure kill switch is not active
  13 |     monkeypatch.setattr(proc, 'kill_switch_active', lambda path: False)
     |
  
  Found 30 errors.
  [*] 16 fixable with the `--fix` option (4 hidden fixes can be enabled with the `--unsafe-fixes` option).

- ruff_fix_started: 2026-08-27T19:21:38.9447423+08:00
- ruff_fix_exit: 1
- ruff_fix_output: |
  SIM105 Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`
    --> app\cli\process_catalogue_ingestion_runs.py:45:13
     |
  43 |           if preflight_report.get("status") != "ready":
  44 |               print("Catalogue preflight blocked ingestion. Report summary:")
  45 | /             try:
  46 | |                 print(json.dumps(preflight_report.get("checks", {}), indent=2, sort_keys=True))
  47 | |             except Exception:
  48 | |                 pass
     | |____________________^
  49 |               stopped = True
     |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(Exception): ...`
  
  SIM105 Use `contextlib.suppress(FileNotFoundError)` instead of `try`-`except`-`pass`
     --> app\modules\catalogue_ingestion\capability_probe.py:474:9
      |
  472 |           os.replace(temporary_name, path)
  473 |       except BaseException:
  474 | /         try:
  475 | |             os.unlink(temporary_name)
  476 | |         except FileNotFoundError:
  477 | |             pass
      | |________________^
  478 |           raise
      |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(FileNotFoundError): ...`
  
  UP031 Use format specifiers instead of percent format
    --> scripts\inspect_app_local_db.py:20:25
     |
  18 |         if t in tables:
  19 |             print('\nTABLE',t)
  20 |             cur.execute("PRAGMA table_info('%s')"%t)
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  21 |             cols=[r[1] for r in cur.fetchall()]
  22 |             print(' COLUMNS:',cols)
     |
  help: Replace with format specifiers
  
  E501 Line too long (126 > 100)
    --> scripts\inspect_app_local_db.py:26:101
     |
  24 |                 # build a safe select
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
  27 |                     if c in cols: sel_cols.append(c)
  28 |                 if not sel_cols:
     |
  
  E701 Multiple statements on one line (colon)
    --> scripts\inspect_app_local_db.py:27:33
     |
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                     if c in cols: sel_cols.append(c)
     |                                 ^
  28 |                 if not sel_cols:
  29 |                     sel='*'
     |
  
  SIM108 Use ternary operator `sel = '*' if not sel_cols else ','.join(sel_cols)` instead of `if`-`else`-block
    --> scripts\inspect_app_local_db.py:28:17
     |
  26 |                   for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                       if c in cols: sel_cols.append(c)
  28 | /                 if not sel_cols:
  29 | |                     sel='*'
  30 | |                 else:
  31 | |                     sel=','.join(sel_cols)
     | |__________________________________________^
  32 |                   cur.execute(f"SELECT {sel} FROM {t} ORDER BY ROWID DESC LIMIT 5")
  33 |                   rows=cur.fetchall()
     |
  help: Replace `if`-`else`-block with `sel = '*' if not sel_cols else ','.join(sel_cols)`
  
  E501 Line too long (137 > 100)
    --> scripts\list_db_info.py:17:101
     |
  15 | …
  16 | …
  17 | …quest_id','provider_response_id','response_id','request_id','receipt','capability']):
     |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  18 | …
  19 | …p().replace('\n',' '))
     |
  
  E501 Line too long (130 > 100)
    --> scripts\run_probe_smoke.py:55:101
     |
  55 | def response_payload(*, finish_reason: str = "stop", refusal: str | None = None, content: str | None = None) -> dict[str, object]:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  56 |     valid_content = json.dumps(
  57 |         {
     |
  
  E701 Multiple statements on one line (colon)
     --> scripts\run_probe_smoke.py:103:18
      |
  101 | # Persist to temp paths under current dir
  102 | p = Path('tmp_probe_test')
  103 | if not p.exists(): p.mkdir()
      |                  ^
  104 | try:
  105 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
      |
  
  E501 Line too long (133 > 100)
     --> scripts\run_probe_smoke.py:105:101
      |
  103 | if not p.exists(): p.mkdir()
  104 | try:
  105 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
      |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  106 |     print('Wrote evidence to', (p / 'capability-evidence.json').absolute())
  107 |     print('evidence failure_category:', json.loads((p / 'capability-evidence.json').read_text())['failure_category'])
      |
  
  E501 Line too long (117 > 100)
     --> scripts\run_probe_smoke.py:107:101
      |
  105 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
  106 |     print('Wrote evidence to', (p / 'capability-evidence.json').absolute())
  107 |     print('evidence failure_category:', json.loads((p / 'capability-evidence.json').read_text())['failure_category'])
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  108 | finally:
  109 |     pass
      |
  
  E501 Line too long (104 > 100)
     --> tests\test_catalogue_capability_probe.py:134:101
      |
  132 |             {
  133 |                 **response_payload(finish_reason="content_filter"),
  134 |                 "prompt_filter_results": [{"content_filter_results": {"violence": {"filtered": True}}}],
      |                                                                                                     ^^^^
  135 |             },
  136 |             "content_filter",
      |
  
  E501 Line too long (117 > 100)
     --> tests\test_catalogue_capability_probe.py:202:101
      |
  201 | def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  202 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  203 |     import os
  204 |     from pathlib import Path
      |
  
  E501 Line too long (110 > 100)
    --> tests\test_worker_preflight.py:8:101
     |
   6 | def test_process_stops_on_preflight_block(monkeypatch, capsys):
   7 |     # Make preflight report blocked
   8 |     monkeypatch.setattr(proc, 'run_catalogue_preflight', lambda settings: {'status': 'blocked', 'checks': {}})
     |                                                                                                     ^^^^^^^^^^
   9 |     # Ensure kill switch is not active
  10 |     monkeypatch.setattr(proc, 'kill_switch_active', lambda path: False)
     |
  
  Found 29 errors (15 fixed, 14 remaining).
  No fixes available (4 hidden fixes can be enabled with the `--unsafe-fixes` option).

- ruff_check_after_fix_exit: 1
- ruff_check_after_fix_output: |
  I001 [*] Import block is un-sorted or un-formatted
    --> app\cli\process_catalogue_ingestion_runs.py:3:1
     |
   1 |   """Claim and process durable catalogue ingestion runs outside HTTP requests."""
   2 |
   3 | / import argparse
   4 | | import json
   5 | | import os
   6 | | import socket
   7 | | import contextlib
   8 | |
   9 | | from app.core.config import get_settings
  10 | | from app.db.session import SystemSessionLocal
  11 | | from app.modules.catalogue_ingestion.service import CatalogueIngestionService
  12 | | from app.modules.catalogue_ingestion.worker_safety import kill_switch_active
  13 | | from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  14 | | from app.modules.operations.service import OperationalJobService
     | |________________________________________________________________^
  help: Organize imports
     |
  3  | import argparse
  4  + import contextlib
  5  | import json
  6  | import os
  7  | import socket
     - import contextlib
  8  |
  9  | from app.core.config import get_settings
  10 | from app.db.session import SystemSessionLocal
  11 + from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  12 | from app.modules.catalogue_ingestion.service import CatalogueIngestionService
  13 | from app.modules.catalogue_ingestion.worker_safety import kill_switch_active
     - from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  14 | from app.modules.operations.service import OperationalJobService
     |
  
  SIM105 Use `contextlib.suppress(FileNotFoundError)` instead of `try`-`except`-`pass`
     --> app\modules\catalogue_ingestion\capability_probe.py:474:9
      |
  472 |           os.replace(temporary_name, path)
  473 |       except BaseException:
  474 | /         try:
  475 | |             os.unlink(temporary_name)
  476 | |         except FileNotFoundError:
  477 | |             pass
      | |________________^
  478 |           raise
      |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(FileNotFoundError): ...`
  
  UP031 Use format specifiers instead of percent format
    --> scripts\inspect_app_local_db.py:20:25
     |
  18 |         if t in tables:
  19 |             print('\nTABLE',t)
  20 |             cur.execute("PRAGMA table_info('%s')"%t)
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  21 |             cols=[r[1] for r in cur.fetchall()]
  22 |             print(' COLUMNS:',cols)
     |
  help: Replace with format specifiers
  
  E501 Line too long (126 > 100)
    --> scripts\inspect_app_local_db.py:26:101
     |
  24 |                 # build a safe select
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
  27 |                     if c in cols: sel_cols.append(c)
  28 |                 if not sel_cols:
     |
  
  E701 Multiple statements on one line (colon)
    --> scripts\inspect_app_local_db.py:27:33
     |
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                     if c in cols: sel_cols.append(c)
     |                                 ^
  28 |                 if not sel_cols:
  29 |                     sel='*'
     |
  
  SIM108 Use ternary operator `sel = '*' if not sel_cols else ','.join(sel_cols)` instead of `if`-`else`-block
    --> scripts\inspect_app_local_db.py:28:17
     |
  26 |                   for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                       if c in cols: sel_cols.append(c)
  28 | /                 if not sel_cols:
  29 | |                     sel='*'
  30 | |                 else:
  31 | |                     sel=','.join(sel_cols)
     | |__________________________________________^
  32 |                   cur.execute(f"SELECT {sel} FROM {t} ORDER BY ROWID DESC LIMIT 5")
  33 |                   rows=cur.fetchall()
     |
  help: Replace `if`-`else`-block with `sel = '*' if not sel_cols else ','.join(sel_cols)`
  
  E501 Line too long (137 > 100)
    --> scripts\list_db_info.py:17:101
     |
  15 | …
  16 | …
  17 | …quest_id','provider_response_id','response_id','request_id','receipt','capability']):
     |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  18 | …
  19 | …p().replace('\n',' '))
     |
  
  E501 Line too long (130 > 100)
    --> scripts\run_probe_smoke.py:55:101
     |
  55 | def response_payload(*, finish_reason: str = "stop", refusal: str | None = None, content: str | None = None) -> dict[str, object]:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  56 |     valid_content = json.dumps(
  57 |         {
     |
  
  E701 Multiple statements on one line (colon)
     --> scripts\run_probe_smoke.py:103:18
      |
  101 | # Persist to temp paths under current dir
  102 | p = Path('tmp_probe_test')
  103 | if not p.exists(): p.mkdir()
      |                  ^
  104 | try:
  105 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
      |
  
  E501 Line too long (133 > 100)
     --> scripts\run_probe_smoke.py:105:101
      |
  103 | if not p.exists(): p.mkdir()
  104 | try:
  105 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
      |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  106 |     print('Wrote evidence to', (p / 'capability-evidence.json').absolute())
  107 |     print('evidence failure_category:', json.loads((p / 'capability-evidence.json').read_text())['failure_category'])
      |
  
  E501 Line too long (117 > 100)
     --> scripts\run_probe_smoke.py:107:101
      |
  105 |     persist_capability_probe_outcome(outcome, evidence_path=p / 'capability-evidence.json', receipt_path=p / 'model-capability.json')
  106 |     print('Wrote evidence to', (p / 'capability-evidence.json').absolute())
  107 |     print('evidence failure_category:', json.loads((p / 'capability-evidence.json').read_text())['failure_category'])
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  108 | finally:
  109 |     pass
      |
  
  E501 Line too long (104 > 100)
     --> tests\test_catalogue_capability_probe.py:134:101
      |
  132 |             {
  133 |                 **response_payload(finish_reason="content_filter"),
  134 |                 "prompt_filter_results": [{"content_filter_results": {"violence": {"filtered": True}}}],
      |                                                                                                     ^^^^
  135 |             },
  136 |             "content_filter",
      |
  
  E501 Line too long (117 > 100)
     --> tests\test_catalogue_capability_probe.py:202:101
      |
  201 | def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  202 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  203 |     import os
  204 |     from pathlib import Path
      |
  
  Found 13 errors.
  [*] 1 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

- ruff_check_second_pass_exit: 1
- ruff_check_second_pass_output: |
  I001 [*] Import block is un-sorted or un-formatted
    --> app\cli\process_catalogue_ingestion_runs.py:3:1
     |
   1 |   """Claim and process durable catalogue ingestion runs outside HTTP requests."""
   2 |
   3 | / import argparse
   4 | | import json
   5 | | import os
   6 | | import socket
   7 | | import contextlib
   8 | |
   9 | | from app.core.config import get_settings
  10 | | from app.db.session import SystemSessionLocal
  11 | | from app.modules.catalogue_ingestion.service import CatalogueIngestionService
  12 | | from app.modules.catalogue_ingestion.worker_safety import kill_switch_active
  13 | | from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  14 | | from app.modules.operations.service import OperationalJobService
     | |________________________________________________________________^
  help: Organize imports
     |
  3  | import argparse
  4  + import contextlib
  5  | import json
  6  | import os
  7  | import socket
     - import contextlib
  8  |
  9  | from app.core.config import get_settings
  10 | from app.db.session import SystemSessionLocal
  11 + from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  12 | from app.modules.catalogue_ingestion.service import CatalogueIngestionService
  13 | from app.modules.catalogue_ingestion.worker_safety import kill_switch_active
     - from app.modules.catalogue_ingestion.preflight import run_catalogue_preflight
  14 | from app.modules.operations.service import OperationalJobService
     |
  
  SIM105 Use `contextlib.suppress(FileNotFoundError)` instead of `try`-`except`-`pass`
     --> app\modules\catalogue_ingestion\capability_probe.py:474:9
      |
  472 |           os.replace(temporary_name, path)
  473 |       except BaseException:
  474 | /         try:
  475 | |             os.unlink(temporary_name)
  476 | |         except FileNotFoundError:
  477 | |             pass
      | |________________^
  478 |           raise
      |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(FileNotFoundError): ...`
  
  UP031 Use format specifiers instead of percent format
    --> scripts\inspect_app_local_db.py:20:25
     |
  18 |         if t in tables:
  19 |             print('\nTABLE',t)
  20 |             cur.execute("PRAGMA table_info('%s')"%t)
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  21 |             cols=[r[1] for r in cur.fetchall()]
  22 |             print(' COLUMNS:',cols)
     |
  help: Replace with format specifiers
  
  E501 Line too long (126 > 100)
    --> scripts\inspect_app_local_db.py:26:101
     |
  24 |                 # build a safe select
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
  27 |                     if c in cols: sel_cols.append(c)
  28 |                 if not sel_cols:
     |
  
  E701 Multiple statements on one line (colon)
    --> scripts\inspect_app_local_db.py:27:33
     |
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                     if c in cols: sel_cols.append(c)
     |                                 ^
  28 |                 if not sel_cols:
  29 |                     sel='*'
     |
  
  SIM108 Use ternary operator `sel = '*' if not sel_cols else ','.join(sel_cols)` instead of `if`-`else`-block
    --> scripts\inspect_app_local_db.py:28:17
     |
  26 |                   for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                       if c in cols: sel_cols.append(c)
  28 | /                 if not sel_cols:
  29 | |                     sel='*'
  30 | |                 else:
  31 | |                     sel=','.join(sel_cols)
     | |__________________________________________^
  32 |                   cur.execute(f"SELECT {sel} FROM {t} ORDER BY ROWID DESC LIMIT 5")
  33 |                   rows=cur.fetchall()
     |
  help: Replace `if`-`else`-block with `sel = '*' if not sel_cols else ','.join(sel_cols)`
  
  E501 Line too long (137 > 100)
    --> scripts\list_db_info.py:17:101
     |
  15 | …
  16 | …
  17 | …quest_id','provider_response_id','response_id','request_id','receipt','capability']):
     |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  18 | …
  19 | …p().replace('\n',' '))
     |
  
  E501 Line too long (104 > 100)
     --> tests\test_catalogue_capability_probe.py:134:101
      |
  132 |             {
  133 |                 **response_payload(finish_reason="content_filter"),
  134 |                 "prompt_filter_results": [{"content_filter_results": {"violence": {"filtered": True}}}],
      |                                                                                                     ^^^^
  135 |             },
  136 |             "content_filter",
      |
  
  E501 Line too long (117 > 100)
     --> tests\test_catalogue_capability_probe.py:202:101
      |
  201 | def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  202 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  203 |     import os
  204 |     from pathlib import Path
      |
  
  Found 9 errors.
  [*] 1 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

- ruff_check_third_pass_exit: 1
- ruff_check_third_pass_output: |
  SIM105 Use `contextlib.suppress(FileNotFoundError)` instead of `try`-`except`-`pass`
     --> app\modules\catalogue_ingestion\capability_probe.py:474:9
      |
  472 |           os.replace(temporary_name, path)
  473 |       except BaseException:
  474 | /         try:
  475 | |             os.unlink(temporary_name)
  476 | |         except FileNotFoundError:
  477 | |             pass
      | |________________^
  478 |           raise
      |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(FileNotFoundError): ...`
  
  UP031 Use format specifiers instead of percent format
    --> scripts\inspect_app_local_db.py:20:25
     |
  18 |         if t in tables:
  19 |             print('\nTABLE',t)
  20 |             cur.execute("PRAGMA table_info('%s')"%t)
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  21 |             cols=[r[1] for r in cur.fetchall()]
  22 |             print(' COLUMNS:',cols)
     |
  help: Replace with format specifiers
  
  E501 Line too long (126 > 100)
    --> scripts\inspect_app_local_db.py:26:101
     |
  24 |                 # build a safe select
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
  27 |                     if c in cols: sel_cols.append(c)
  28 |                 if not sel_cols:
     |
  
  E701 Multiple statements on one line (colon)
    --> scripts\inspect_app_local_db.py:27:33
     |
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                     if c in cols: sel_cols.append(c)
     |                                 ^
  28 |                 if not sel_cols:
  29 |                     sel='*'
     |
  
  SIM108 Use ternary operator `sel = '*' if not sel_cols else ','.join(sel_cols)` instead of `if`-`else`-block
    --> scripts\inspect_app_local_db.py:28:17
     |
  26 |                   for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                       if c in cols: sel_cols.append(c)
  28 | /                 if not sel_cols:
  29 | |                     sel='*'
  30 | |                 else:
  31 | |                     sel=','.join(sel_cols)
     | |__________________________________________^
  32 |                   cur.execute(f"SELECT {sel} FROM {t} ORDER BY ROWID DESC LIMIT 5")
  33 |                   rows=cur.fetchall()
     |
  help: Replace `if`-`else`-block with `sel = '*' if not sel_cols else ','.join(sel_cols)`
  
  E501 Line too long (137 > 100)
    --> scripts\list_db_info.py:17:101
     |
  15 | …
  16 | …
  17 | …quest_id','provider_response_id','response_id','request_id','receipt','capability']):
     |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  18 | …
  19 | …p().replace('\n',' '))
     |
  
  invalid-syntax: Expected a newline after line continuation character
     --> tests\test_catalogue_capability_probe.py:134:43
      |
  132 | …     {
  133 | …         **response_payload(finish_reason="content_filter"),
  134 | …         "prompt_filter_results": [\n                {\n                    "content_filter_results": {"violence": {"filtered": True…
      |                                     ^
  135 | …     },
  136 | …     "content_filter",
      |
  
  invalid-syntax: Expected `,`, found `{`
     --> tests\test_catalogue_capability_probe.py:134:61
      |
  132 | …     {
  133 | …         **response_payload(finish_reason="content_filter"),
  134 | …         "prompt_filter_results": [\n                {\n                    "content_filter_results": {"violence": {"filtered": True…
      |                                                       ^
  135 | …     },
  136 | …     "content_filter",
      |
  
  invalid-syntax: Expected a newline after line continuation character
     --> tests\test_catalogue_capability_probe.py:134:62
      |
  132 | …     {
  133 | …         **response_payload(finish_reason="content_filter"),
  134 | …         "prompt_filter_results": [\n                {\n                    "content_filter_results": {"violence": {"filtered": True…
      |                                                        ^
  135 | …     },
  136 | …     "content_filter",
      |
  
  invalid-syntax: Expected `,`, found string
     --> tests\test_catalogue_capability_probe.py:134:84
      |
  132 | …     {
  133 | …         **response_payload(finish_reason="content_filter"),
  134 | …         "prompt_filter_results": [\n                {\n                    "content_filter_results": {"violence": {"filtered": True…
      |                                                                              ^^^^^^^^^^^^^^^^^^^^^^^^
  135 | …     },
  136 | …     "content_filter",
      |
  
  E501 Line too long (176 > 100)
     --> tests\test_catalogue_capability_probe.py:134:101
      |
  132 | …
  133 | …
  134 | …           "content_filter_results": {"violence": {"filtered": True}}\n                }\n            ],
      |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  135 | …
  136 | …
      |
  
  invalid-syntax: Expected `,`, found `:`
     --> tests\test_catalogue_capability_probe.py:134:108
      |
  132 | …     {
  133 | …         **response_payload(finish_reason="content_filter"),
  134 | …         "prompt_filter_results": [\n                {\n                    "content_filter_results": {"violence": {"filtered": True…
      |                                                                                                      ^
  135 | …     },
  136 | …     "content_filter",
      |
  
  invalid-syntax: Expected a newline after line continuation character
     --> tests\test_catalogue_capability_probe.py:134:142
      |
  132 | …
  133 | …
  134 | …       "content_filter_results": {"violence": {"filtered": True}}\n                }\n            ],
      |                                                                   ^
  135 | …
  136 | …
      |
  
  invalid-syntax: Expected a newline after line continuation character
     --> tests\test_catalogue_capability_probe.py:134:161
      |
  132 | …
  133 | …
  134 | …ter_results": {"violence": {"filtered": True}}\n                }\n            ],
      |                                                                   ^
  135 | …
  136 | …
      |
  
  E501 Line too long (117 > 100)
     --> tests\test_catalogue_capability_probe.py:202:101
      |
  201 | def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  202 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  203 |     import os
  204 |     from pathlib import Path
      |
  
  Found 15 errors.
  No fixes available (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

- ruff_check_fourth_pass_exit: 1
- ruff_check_fourth_pass_output: |
  SIM105 Use `contextlib.suppress(FileNotFoundError)` instead of `try`-`except`-`pass`
     --> app\modules\catalogue_ingestion\capability_probe.py:474:9
      |
  472 |           os.replace(temporary_name, path)
  473 |       except BaseException:
  474 | /         try:
  475 | |             os.unlink(temporary_name)
  476 | |         except FileNotFoundError:
  477 | |             pass
      | |________________^
  478 |           raise
      |
  help: Replace `try`-`except`-`pass` with `with contextlib.suppress(FileNotFoundError): ...`
  
  UP031 Use format specifiers instead of percent format
    --> scripts\inspect_app_local_db.py:20:25
     |
  18 |         if t in tables:
  19 |             print('\nTABLE',t)
  20 |             cur.execute("PRAGMA table_info('%s')"%t)
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  21 |             cols=[r[1] for r in cur.fetchall()]
  22 |             print(' COLUMNS:',cols)
     |
  help: Replace with format specifiers
  
  E501 Line too long (126 > 100)
    --> scripts\inspect_app_local_db.py:26:101
     |
  24 |                 # build a safe select
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
  27 |                     if c in cols: sel_cols.append(c)
  28 |                 if not sel_cols:
     |
  
  E701 Multiple statements on one line (colon)
    --> scripts\inspect_app_local_db.py:27:33
     |
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                     if c in cols: sel_cols.append(c)
     |                                 ^
  28 |                 if not sel_cols:
  29 |                     sel='*'
     |
  
  SIM108 Use ternary operator `sel = '*' if not sel_cols else ','.join(sel_cols)` instead of `if`-`else`-block
    --> scripts\inspect_app_local_db.py:28:17
     |
  26 |                   for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                       if c in cols: sel_cols.append(c)
  28 | /                 if not sel_cols:
  29 | |                     sel='*'
  30 | |                 else:
  31 | |                     sel=','.join(sel_cols)
     | |__________________________________________^
  32 |                   cur.execute(f"SELECT {sel} FROM {t} ORDER BY ROWID DESC LIMIT 5")
  33 |                   rows=cur.fetchall()
     |
  help: Replace `if`-`else`-block with `sel = '*' if not sel_cols else ','.join(sel_cols)`
  
  E501 Line too long (137 > 100)
    --> scripts\list_db_info.py:17:101
     |
  15 | …
  16 | …
  17 | …quest_id','provider_response_id','response_id','request_id','receipt','capability']):
     |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  18 | …
  19 | …p().replace('\n',' '))
     |
  
  invalid-syntax: Expected `)`, found `]`
     --> tests\test_catalogue_capability_probe.py:146:5
      |
  144 |         ),
  145 |         (response_payload(content="not-json"), "parser_contract", "stop", False),
  146 |     ],
      |     ^
  147 | )
  148 | def test_failed_probe_retains_sanitized_metadata_and_usage(
      |
  
  E501 Line too long (117 > 100)
     --> tests\test_catalogue_capability_probe.py:207:101
      |
  206 | def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  207 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  208 |     import os
  209 |     from pathlib import Path
      |
  
  Found 8 errors.
  No fixes available (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

- capability_probe_header_repair_run: 2026-08-27T19:39:01.7511920+08:00
- py_compile_exit: 0
- ruff_exit: 1
- pytest_exit: 0
- ruff_output: |
  I001 [*] Import block is un-sorted or un-formatted
    --> app\modules\catalogue_ingestion\capability_probe.py:3:1
     |
   1 |   """One-shot Azure OpenAI capability probe with sanitized durable evidence."""
   2 |
   3 | / from __future__ import annotations
   4 | |
   5 | | import json
   6 | | import os
   7 | | import tempfile
   8 | | import time
   9 | | import urllib.error
  10 | | import urllib.request
  11 | | import uuid
  12 | | from collections.abc import Callable, Mapping
  13 | | from dataclasses import dataclass
  14 | | from datetime import UTC, datetime, timedelta
  15 | | from decimal import Decimal
  16 | | from pathlib import Path
  17 | | from typing import Any
  18 | | import contextlib
  19 | |
  20 | | from app.core.config import Settings
  21 | | from app.modules.catalogue_ingestion.ai_contract import azure_openai_request_url
  22 | | from app.modules.catalogue_ingestion.claim_provider import (
  23 | |     CLAIM_SYSTEM_INSTRUCTION,
  24 | |     OBJECTIVE_INSTRUCTIONS,
  25 | |     _objective_azure_schema,
  26 | | )
  27 | | from app.modules.catalogue_ingestion.claim_schemas import (
  28 | |     ClaimExtractionOutput,
  29 | |     ClaimObjective,
  30 | | )
  31 | | from app.modules.catalogue_ingestion.preflight import (
  32 | |     expected_catalogue_capability_contract,
  33 | | )
  34 | | from app.modules.catalogue_ingestion.provider import estimate_cost
     | |__________________________________________________________________^
  35 |
  36 |   CAPABILITY_PROBE_EVIDENCE_SCHEMA_VERSION = 1
     |
  help: Organize imports
     |
  4  |
  5  + import contextlib
  6  | import json
  --------------------------------------------------------------------------------
  18 | from typing import Any
     - import contextlib
  19 |
     |
  
  UP031 Use format specifiers instead of percent format
    --> scripts\inspect_app_local_db.py:20:25
     |
  18 |         if t in tables:
  19 |             print('\nTABLE',t)
  20 |             cur.execute("PRAGMA table_info('%s')"%t)
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  21 |             cols=[r[1] for r in cur.fetchall()]
  22 |             print(' COLUMNS:',cols)
     |
  help: Replace with format specifiers
  
  E501 Line too long (126 > 100)
    --> scripts\inspect_app_local_db.py:26:101
     |
  24 |                 # build a safe select
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
     |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^
  27 |                     if c in cols: sel_cols.append(c)
  28 |                 if not sel_cols:
     |
  
  E701 Multiple statements on one line (colon)
    --> scripts\inspect_app_local_db.py:27:33
     |
  25 |                 sel_cols=[]
  26 |                 for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                     if c in cols: sel_cols.append(c)
     |                                 ^
  28 |                 if not sel_cols:
  29 |                     sel='*'
     |
  
  SIM108 Use ternary operator `sel = '*' if not sel_cols else ','.join(sel_cols)` instead of `if`-`else`-block
    --> scripts\inspect_app_local_db.py:28:17
     |
  26 |                   for c in ['id','status','created_at','provider_response_id','provider_request_id','response_id','request_id']:
  27 |                       if c in cols: sel_cols.append(c)
  28 | /                 if not sel_cols:
  29 | |                     sel='*'
  30 | |                 else:
  31 | |                     sel=','.join(sel_cols)
     | |__________________________________________^
  32 |                   cur.execute(f"SELECT {sel} FROM {t} ORDER BY ROWID DESC LIMIT 5")
  33 |                   rows=cur.fetchall()
     |
  help: Replace `if`-`else`-block with `sel = '*' if not sel_cols else ','.join(sel_cols)`
  
  E501 Line too long (137 > 100)
    --> scripts\list_db_info.py:17:101
     |
  15 | …
  16 | …
  17 | …quest_id','provider_response_id','response_id','request_id','receipt','capability']):
     |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  18 | …
  19 | …p().replace('\n',' '))
     |
  
  E501 Line too long (117 > 100)
     --> tests\test_catalogue_capability_probe.py:206:101
      |
  205 | def test_persist_writes_optional_local_copy(tmp_path, monkeypatch):
  206 |     """Ensure persist_capability_probe_outcome writes a best-effort local copy to `.catalogue-local` when present."""
      |                                                                                                     ^^^^^^^^^^^^^^^^^
  207 |     import os
  208 |     from pathlib import Path
      |
  
  Found 7 errors.
  [*] 1 fixable with the `--fix` option (2 hidden fixes can be enabled with the `--unsafe-fixes` option).
- pytest_output: |
  ........................................................................ [ 73%]
  ..........................                                               [100%]
  ============================== warnings summary ===============================
  .venv\Lib\site-packages\fastapi\testclient.py:1
    C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
      from starlette.testclient import TestClient as TestClient  # noqa
  
  .venv\Lib\site-packages\_pytest\cacheprovider.py:469
    C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv\Lib\site-packages\_pytest\cacheprovider.py:469: PytestCacheWarning: cache could not write path C:\Users\Admin\Downloads\Scholarship AI Assistant\.pytest_cache\v\cache\nodeids: [Errno 13] Permission denied: 'C:\\Users\\Admin\\Downloads\\Scholarship AI Assistant\\.pytest_cache\\v\\cache\\nodeids'
      config.cache.set("cache/nodeids", sorted(self.cached_nodeids))
  
  -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
## 2026-08-27 19:49:47 +08:00 - Automated Milestone 0 run
- Actions:
  - Ran targeted Ruff checks and applied minimal patches to:
    - pp/modules/catalogue_ingestion/capability_probe.py (removed duplicate import block; sorted imports)
    - scripts/inspect_app_local_db.py (fixed PRAGMA call, refactored column selection)
    - scripts/list_db_info.py (extracted sensitive-key list to avoid long line)
    - 	ests/test_catalogue_capability_probe.py (wrapped long docstring)
  - Re-ran 
uff and fixed remaining issues.
  - Compiled tracked Python files with .venv\Scripts\python.exe -m py_compile (281 files).
  - Ran focused pytest suite: 	ests/test_catalogue_ingestion.py tests/test_document_conversion.py tests/test_worker_preflight.py — all passed.
  - Ran non-E2E backend tests: pytest -m 'not e2e and not redis and not postgres' — all passed.
- Results:
  - Ruff: clean across repo.
  - Tests: focused + non-E2E backend gates passed (exit code 0).


## 2026-08-27T20:04:15.626374+08:00 - Dirty worktree classification
- milestone_0 (17 files)
  - M app/cli/process_catalogue_ingestion_runs.py
  - M app/modules/catalogue_ingestion/claim_provider.py
  - M app/modules/catalogue_ingestion/claim_resolution.py
  - M app/modules/catalogue_ingestion/claim_schemas.py
  - M app/modules/catalogue_ingestion/document_conversion.py
  - M app/modules/catalogue_ingestion/models.py
  - M app/modules/catalogue_ingestion/provider.py
  - M app/modules/catalogue_ingestion/repository.py
  - M app/modules/catalogue_ingestion/schemas.py
  - M app/modules/catalogue_ingestion/service.py
  - M app/modules/catalogue_ingestion/source_routing.py
  - ?? app/modules/catalogue_ingestion/acquisition_bundle.py
  - ?? app/modules/catalogue_ingestion/ai_contract.py
  - ?? app/modules/catalogue_ingestion/capability_probe.py
  - ?? app/modules/catalogue_ingestion/preflight.py
  - ?? app/modules/catalogue_ingestion/worker_safety.py
  - ?? tests/test_worker_preflight.py
- local_secrets_runtime (0 files)
- scratch_debug (0 files)
- malformed_generated (0 files)
- frontend (13 files)
  - M frontend/src/App.tsx
  - M frontend/src/features/admin/AdminPage.tsx
  - M frontend/src/features/admin/DirectUrlIngestionPanel.tsx
  - M frontend/src/features/admin/admin.test.ts
  - M frontend/src/features/admin/admin.ts
  - M frontend/src/features/admin/types.ts
  - M frontend/src/features/catalogue/OpportunityDetailPage.tsx
  - M frontend/src/features/catalogue/catalogue.ts
  - M frontend/src/features/catalogue/types.ts
  - M frontend/src/styles.css
  - ?? frontend/src/features/admin/AdminAcquiredReviewPage.tsx
  - ?? frontend/src/features/admin/AdminReviewPage.tsx
  - ?? frontend/src/features/catalogue/ScholarshipDetailView.tsx
- docs (20 files)
  - ?? docs/01-architecture-and-data-flow-audit.md
  - ?? docs/02-ai-scraping-and-extraction-audit.md
  - ?? docs/03-reliability-security-production-readiness-audit.md
  - ?? docs/04-terra-detailed-implementation-plan.md
  - ?? docs/audit-evidence-report-full.md
  - ?? docs/audit-evidence-report.md
  - ?? docs/catalogue-ai-capability-receipt.example.json
  - ?? docs/goal-first-scholarship-catalogue-execution-log.md
  - ?? docs/goal-first-scholarship-catalogue-go-live-plan.md
  - ?? docs/gpt-5-mini-scholarship-catalogue-execution-prompt.md
  - ?? docs/private-catalogue-seed-audit-2026-08-24.md
  - ?? docs/terra-5.6-catalogue-completion-plan.md
  - ?? docs/terra-5.6-phase-0-zero-cost-audit-2026-08-25.md
  - ?? docs/terra-5.6-phase-1-publication-readiness-2026-08-25.md
  - ?? docs/terra-5.6-phase-2-official-source-acquisition-2026-08-25.md
  - ?? docs/terra-5.6-phase-3-provenance-safe-extraction-2026-08-25.md
  - ?? docs/terra-5.6-phase-4-family-route-deduplication-2026-08-25.md
  - ?? docs/terra-5.6-phase-5-admin-review-experience-2026-08-25.md
  - ?? docs/terra-5.6-phase-6-local-runtime-wiring-2026-08-25.md
  - ?? docs/terra-5.6-phase-7-live-pilot-readiness-2026-08-25.md
- scripts_tools (5 files)
  - ?? scripts/inspect_app_local_db.py
  - ?? scripts/list_db_info.py
  - ?? scripts/list_tables.py
  - ?? scripts/list_tables2.py
  - ?? scripts/run_probe_smoke.py
- other_app_changes (13 files)
  - M app/cli/seed_verified_opportunities.py
  - M app/core/config.py
  - M app/modules/opportunities/models.py
  - M app/modules/opportunities/repository.py
  - M app/modules/opportunities/routes.py
  - M app/modules/opportunities/schemas.py
  - M app/modules/opportunities/service.py
  - M app/modules/opportunities/source_monitor.py
  - M app/release_policy.json
  - ?? app/cli/catalogue_preflight.py
  - ?? app/cli/probe_catalogue_ai_capability.py
  - ?? app/modules/opportunities/catalogue_identity.py
  - ?? app/modules/opportunities/publication_readiness.py
- untracked_misc (35 files)
  - M .env.example
  - M .gitignore
  - M Dockerfile
  - M compose.yaml
  - M data/seed/verified_opportunities.json
  - M tests/conftest.py
  - M tests/test_browser_e2e.py
  - M tests/test_catalogue_ingestion.py
  - M tests/test_catalogue_ingestion_postgres.py
  - M tests/test_document_conversion.py
  - M tests/test_document_conversion_transport.py
  - M tests/test_frontend.py
  - M tests/test_matching.py
  - M tests/test_opportunities.py
  - M tests/test_seed_opportunities.py
  - M tests/test_source_monitor.py
  - M tests/test_source_routing.py
  - ?? .azure/
  - ?? .classify_worktree.py
  - ?? .env.catalogue.example
  - ?? alembic/versions/20260825_0054_publication_readiness.py
  - ?? alembic/versions/20260825_0055_acquisition_bundle.py
  - ?? alembic/versions/20260825_0056_catalogue_identity.py
  - ?? data/seed/private_priority_scholarship_candidates.v1.json
  - ?? tests/evidence_matrix.json
  - ?? tests/fixtures/catalogue_acquisition/three_family_source_bundles.v1.json
  - ?? tests/fixtures/catalogue_readiness/
  - ?? tests/test_catalogue_acquisition_bundles.py
  - ?? tests/test_catalogue_capability_probe.py
  - ?? tests/test_catalogue_identity.py
  - ?? tests/test_catalogue_preflight.py
  - ?? tests/test_catalogue_readiness_gold.py
  - ?? tests/test_mapping.json
  - ?? tests/test_private_priority_seed.py
  - ?? tests/test_publication_readiness.py
## 2026-08-27 21:00:25 +08:00 - Frontend gates + budget-routing fix
- Actions:
  - Ran frontend typecheck and vitest using existing runtime tools (NodeDir and pnpm). Typecheck passed; Vitest reported esbuild access denied under sandbox and was re-run with approved elevated execution. Vitest: 37 tests passed.
  - Implemented a conservative planned-call budget check inside CatalogueIngestionService._process_candidate to compute the planned objective/artifact call graph and projected cost and to fail early when admitting the candidate would exceed run ceilings.
  - Added class static helper _compute_planned_calls_and_cost(run, candidate, settings) for testing and reuse.
  - Added unit test 	ests/test_budget_routing.py that verifies planned calls and projected cost calculation using fake candidate/artifact/decision objects.
  - Re-ran Ruff, py_compile, and the backend test gates (excluding e2e and rowser_compat) � all tests passed.
- Notes:
  - Agent-created and sensitive backups moved to .catalogue-local/backups/ (ignored). No secrets were printed or staged.
  - No commits or pushes were made.

---
- timestamp: 2026-08-27T21:45:40.2031953+08:00
- action: frontend pnpm typecheck & test; dedupe budget-routing fix
- details:
  - Ran pnpm typecheck and vitest using the provided Codex Node/pnpm paths; tsc passed; vitest initially failed with esbuild access denied and was re-run with elevated filesystem access; vitest: 37 tests passed.
  - Added unit test 	ests/test_budget_routing.py::test_compute_planned_calls_and_cost_deduplicates_across_artifacts to assert deduplicated objective counting.
  - Patched pp/modules/catalogue_ingestion/service.py::_compute_planned_calls_and_cost to deduplicate objectives across artifacts and compute projected cost conservatively per unique objective.
  - Ran focused uff checks and the new unit tests; all focused checks passed.
  - Removed untracked helper/patch files from repo root to avoid tooling noise.
  - No commits or pushes were made.

