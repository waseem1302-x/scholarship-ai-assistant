# Terra 5.6 Phase 3 — Provenance-Safe Multi-Source Extraction

Date: 2026-08-25  
Branch: `codex/phase1b2-crawlee-secure-bridge`  
Prior-phase evidence: `docs/terra-5.6-phase-2-official-source-acquisition-2026-08-25.md`

## Outcome

Phase 3 is complete. Seed and direct-URL extraction now converge on the same bounded
multi-artifact claim pipeline. Extraction remains staged for human review and does not
publish records.

## Extraction contract

- Every routed source artifact is evaluated separately and only for applicable,
  unresolved objectives.
- The twelve versioned objectives cover identity, programmes, programme details,
  routes, eligibility and context, document identity/requirements/counts/format,
  funding, and application timeline.
- Specialized funding, eligibility, deadline, document, and application pages route to
  their narrow objectives. A deterministic URL role takes precedence over a multi-topic
  page body; `/apply` pages contribute route/application-method facts without consuming
  dedicated deadline or document objectives.
- All mandatory objectives must reach a terminal coverage state before a proposal can
  pass validation.

## Claim provenance and scope

Every accepted claim now retains:

- canonical entity type, entity key, and field path;
- one typed value;
- immutable artifact ID, candidate-source ID, final official URL, and content hash;
- exact excerpt offsets into normalized artifact text;
- cycle, route, institution, programme, country, and programme-family scope; and
- objective, objective-specific schema version, prompt hash, provider, and model.

Evidence excerpts that do not exactly match normalized source text continue to be
rejected. Confidence remains review metadata and is not treated as proof.

## Deterministic convergence and caching

Claims are resolved by stable scope and authority rules. Same-tier disagreements remain
blocking conflicts; cycle mixing and ambiguous source roles fail closed. Extraction
attempt cache identity includes normalized content hash, objective-specific schema,
objective-specific prompt hash, provider, and model. Reprocessing unchanged content
reuses persisted attempts instead of issuing another provider call.

## Fixture regressions

The synthetic fixture
`tests/fixtures/catalogue_acquisition/three_family_source_bundles.v1.json` covers one CSC
university route, one DAAD EPOS course, and one Erasmus joint-master route. It contains
no redistributed official text.

For every family, regressions prove:

- six distinct official artifacts participate in extraction;
- all twelve objectives execute exactly once and finish complete;
- the candidate reaches `ready_for_review`;
- resolved values exactly match the fixture's expected identity, programme, route,
  eligibility, funding, deadline, step, and document facts;
- every excerpt and offset exactly matches its immutable artifact text;
- every resolved claim carries country/programme-family/cycle/route scope and complete
  extraction lineage; and
- seed ingestion uses the same bundle pipeline as direct-URL ingestion.

Existing regressions also prove that an unchanged direct source is extracted once per
objective across retries and that changing a prompt hash prevents stale reuse.

## Verification

- Full Ruff check — passed.
- `git diff --check` — passed (Git emitted only LF/CRLF conversion notices).
- Focused routing and acquisition regressions — 15 passed.
- Focused ingestion, queue, evidence, acquisition, and routing regressions — 105 passed.
- Full backend `pytest -m "not e2e"` — 781 selected: 758 passed, 23 skipped, 10
  deselected; no failures.
- Alembic head — `20260825_0055`.
- Frontend Vitest — 9 files, 34 tests passed.
- Frontend TypeScript/Vite production build — passed with one pre-existing mixed
  static/dynamic import warning.

## Cost and safety

- Azure/OpenAI/model calls: 0.
- Estimated and observed model cost: USD 0.
- Live network acquisition: none.
- Deployment, merge, push, production flags, and non-test publication: none.
- The pre-existing dirty worktree was preserved.

## Exit gate

Passed. Synthetic CSC, DAAD, and Erasmus outputs exactly match their expected evidence,
scope, objective coverage, and extraction lineage. Phase 4 has not started.
