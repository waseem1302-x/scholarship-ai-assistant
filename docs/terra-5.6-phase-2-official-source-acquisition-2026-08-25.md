# Terra 5.6 Phase 2 â€” Official-Source Acquisition Bundle

Date: 2026-08-25  
Branch: `codex/phase1b2-crawlee-secure-bridge`  
Prior-phase evidence: `docs/terra-5.6-phase-1-publication-readiness-2026-08-25.md`

## Outcome

Phase 2 is complete. Seed and direct-URL candidates now produce the same versioned,
durable official-source bundle before extraction. The workflow remains private and
candidate-only compatible; no AI provider is needed to acquire or review a bundle.

## Acquisition contract

- Policy version: `official-source-bundle.v1`.
- Hard maximum: six accepted artifacts per candidate and crawl depth two.
- Requests remain sequential and use the configured per-host delay.
- Every request, redirect, MIME check, byte limit, DNS/IP check, and robots decision
  remains behind `SafeSourceFetcher` (or its byte-bounded adapter).
- Crawling is same-host by default. A cross-domain host is admitted only when it is the
  candidate's deterministically resolved provider or university host.
- Accepted artifacts are deduplicated by canonical URL, redirect destination, and
  normalized content hash.
- Every accepted artifact is immutable and retains final URL, normalized content hash,
  retrieval/parser lineage, and one deterministic acquisition role.

## Source roles and gaps

The bundle classifier records one primary role per artifact:

- identity/overview;
- funding/benefits;
- eligibility;
- dates/cycle;
- application process;
- required documents;
- country route; or
- programme/course annex.

The six general roles are required for a complete base bundle. Country-route and
programme/course-annex artifacts are retained when applicable. Ambiguous pages fail
closed as `unknown`.

Candidate records now persist an `acquisition_bundle` snapshot containing the policy
version, accepted artifacts, covered roles, blocked sources, and stable gap codes. Gaps
distinguish absence from a blocked candidate source, including
`funding_source_missing`, `deadline_source_blocked`, `source_role_unresolved`, and
`acquisition_budget_exhausted`. The operator status API exposes both the bundle and each
artifact's role decision without exposing source text.

## Document path

PDFs enter through the same safe fetch boundary as HTML. Ordinary PDFs with a sufficient
local text layer use the bounded local pypdf parser. Insufficient or image-like PDFs are
sent to the isolated, offline Docling worker; OCR remains separately gated and recorded.
Parser version, page count, and OCR outcome are retained in immutable artifact metadata.

## Fixtures and regressions

`tests/fixtures/catalogue_acquisition/three_family_source_bundles.v1.json` contains only
synthetic minimal text. It represents one CSC university route, one DAAD EPOS course,
and one Erasmus joint-master route. The Erasmus path includes a cross-domain consortium
page whose provider ownership is resolved before crawling.

Regressions prove:

- all three paths yield six-artifact, complete, reviewable bundles;
- both seed and direct-URL entry paths use the bundle contract;
- no model calls occur;
- the six-artifact ceiling is enforced even when the prior setting allows more;
- missing and blocked objectives produce explicit gap codes;
- identical normalized content under different URLs is not accepted twice;
- acquisition roles and policy versions appear in the operator lineage API; and
- sufficient PDF text stays local while scan-like input follows the isolated worker
  path.

## Verification

- `uv run ruff check` on all changed Phase 2 Python files â€” passed.
- `git diff --check` â€” passed (Git emitted only existing LF/CRLF conversion notices).
- Phase 2 acquisition regressions â€” 6 passed.
- Focused crawler, routing, document, and ingestion regressions â€” passed.
- Migration suite â€” 19 passed.
- `python -m alembic heads` â€” `20260825_0055 (head)`.
- Full backend `pytest -m "not e2e"` â€” 787 selected: 754 passed, 23 skipped, 10
  deselected; no failures.
- Frontend Vitest â€” 9 files, 34 tests passed.
- Frontend TypeScript/Vite production build â€” passed with one pre-existing mixed
  static/dynamic import warning.

## Cost and safety

- Azure/OpenAI/model calls: 0.
- Estimated and observed model cost: USD 0.
- Live network acquisition: none.
- Deployment, merge, push, production flags, and non-test publication: none.
- The pre-existing dirty worktree was preserved.

## Exit gate

Passed. Synthetic CSC, DAAD, and Erasmus paths each produce a reviewable official-source
bundle with immutable per-source artifacts, deterministic roles, explicit gaps, and no
AI extraction. Phase 3 is implemented — see `docs/terra-5.6-phase-3-provenance-safe-extraction-2026-08-25.md` for details. Key code anchors: `app/modules/catalogue_ingestion/claim_schemas.py:11` (CLAIM_SCHEMA_VERSION = "catalogue-claims.v3") and `app/modules/catalogue_ingestion/graph_materializer.py:58`.

