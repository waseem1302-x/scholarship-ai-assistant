# Scholarship Detail Extraction v3

## Milestone

This branch implements a generic, evidence-first extraction layer for a direct official URL and
explicit supporting official sources. It is designed to represent scholarship identity,
programme and degree categories, application routes, eligibility, complete document lists,
funding components, deadlines and other timeline events, application steps, and official
resources without publishing or forcing the result into the current canonical graph.

The extraction result remains review-only cited staging data. Frontend work, public endpoints,
canonical graph redesign, publication, discovery-provider work, and Azure infrastructure changes
are outside this milestone.

## Implemented Contract

`catalogue-claims.v3` partitions each official source into twelve independently durable
objectives:

1. identity
2. programmes
3. programme details
4. application routes
5. eligibility core rules
6. eligibility conditions and exclusions
7. document names and order
8. document requirement conditions and submission stage
9. document original/copy counts and form year
10. document translation, certification, and notes
11. funding components
12. deadlines, events, steps, and official resources

Each model attempt is keyed by objective schema, source content hash, prompt hash, provider, and
model. Successful objectives can be reused after a later objective fails or reaches a budget.
Reused output is passed through the current deterministic normalizer before resolution.

Every claim contains one typed value, an entity key, programme/route/cycle/institution scope, an
exact source excerpt, and character offsets. Azure structured-output schemas are constrained per
objective to the allowed entity types and field names. Long sources use objective-aware evidence
masks that preserve the original source length and character offsets.

## Deterministic Gates

The resolver now:

- validates every excerpt against the immutable fetched artifact;
- normalizes bounded field aliases without accepting arbitrary fields;
- maps intake years to cycle entities and arrival/departure windows to events;
- rejects arrival, departure, screening, result, and study-period dates presented as deadlines;
- accepts a resource URL only when it was fetched from official page link metadata or is the
  source URL itself;
- keeps compatible narrative facts instead of creating false scalar conflicts;
- preserves programme-scoped facts with the same document or funding key;
- gives the primary source deterministic priority over supporting sources at the same authority
  tier;
- marks an objective partial when a substantive invalid claim is dropped;
- drops null placeholders with a warning but never treats them as facts;
- requires core identity, cycle, programme/degree mapping, route, eligibility, documents,
  funding, deadline type, steps, and complete objective coverage;
- requires eligibility, documents, funding, and steps for every programme when a record contains
  multiple programmes.

Expanded v3 records cannot be submitted through the legacy graph materializer. Submission returns
`catalogue_detail_extraction_review_only`; no opportunity, evidence graph, source snapshot, or
publication record is written.

No database migration was required. Objective durability uses the existing extraction-attempt
schema with an objective-qualified schema version, and the expanded result uses the existing JSON
staging payload.

## Live MEXT Validation

Validation ran on 2026-08-23 in an isolated SQLite database against these official 2027 sources:

- MEXT Research Students application guidelines PDF
- MEXT Undergraduate Students application guidelines PDF

The existing Azure `gpt-5-mini` deployment was used read-only. No Azure resource, deployment,
capacity, role, secret, branch, PR, or production database was changed.

The focused run completed all 24 source/objective calls. It consumed 71,559 input tokens and
58,480 output tokens. The harness reported a configured estimate of `0.188519`; this is a test
pricing estimate, not an Azure invoice or asserted production cost.

Deterministic resolution accepted 236 claims whose excerpts and offsets all matched the immutable
source artifacts:

| Entity | Accepted claims |
| --- | ---: |
| Scholarship | 7 |
| Programme | 16 |
| Application route | 15 |
| Institution | 2 |
| Eligibility | 41 |
| Document | 109 |
| Funding | 36 |
| Event | 5 |
| Official resource | 5 |

The accepted document data contains 37 document entities and 20 cited name claims across Research
and Undergraduate scopes. It includes academic transcripts, graduation/degree certificates,
recommendation letters, medical certificates, application forms, the Research Plan, employer
recommendations, thesis abstracts, enrollment certificates, and conditional language/direct
placement documents. Original/copy counts, required/conditional status, translation,
certification, form-year, stage, and notes are represented separately when explicit.

Accepted Research funding includes monthly allowance values of JPY 143,000 for preparatory or
non-regular students, JPY 144,000 for master's/professional regular students, and JPY 145,000 for
doctoral regular students, plus regional supplements, education-fee waiver, and travel components.
Undergraduate fee-waiver, regional supplement, and travel facts were also represented. Facts with
bad evidence spans, including the generated Undergraduate monthly allowance amount, were rejected
rather than repaired from general knowledge.

## Verified Limitations

The focused candidate correctly remained blocked. It was not materialized or published.

Remaining live issues are evidence and extraction-quality issues, not hidden as success:

- Research and Undergraduate source titles produce competing scholarship-name variants.
- Some programme degree-level claims had non-exact generated excerpts and were rejected.
- Some eligibility claims reused a coarse entity key, creating real same-key conflicts.
- Several eligibility, funding, and timeline claims had non-exact excerpts and were rejected.
- The Ministry guidelines delegate application cutoffs to diplomatic missions, so these two PDFs
  do not establish one universal dated application deadline.
- No complete application-step set survived the evidence gate in the focused run.
- Identity, programme core, eligibility core, document-count, and application/timeline coverage
  remained partial in at least one source.
- The general MEXT overview contains a flattened seven-column table. It is suitable for discovering
  programme names and routes, but its flattened text is not reliable enough to assign every degree,
  duration, and funding cell without layout-aware table extraction.

These conditions are why the candidate status is `conflict_detected`, not `ready_for_review`.

## Test Evidence

The catalogue-ingestion suite covers objective isolation and reuse, more than twelve documents,
objective-aware offset-preserving masks, strict objective schemas, invalid-claim salvage,
programme-scoped completeness, deadline/event separation, fetched-link provenance, compatible
narrative evidence, v2 staging compatibility, cost-budget resume, and the review-only submission
gate.

Final verification completed with 637 passing tests and 29 expected skips. Ruff lint passed, all
313 Python files passed Ruff's formatting check, and `git diff --check` reported no whitespace
errors.

## Deferred Work

- Layout-aware PDF table extraction for multi-column overview tables.
- A canonical programme-scoped graph and migration for v3 review approval.
- Public/admin API projection and a universal scholarship detail page.
- Human review workflow for reconciling title variants and coarse model entity keys.
- Embassy-country source bundles for exact local deadlines and forms.
- University-recommendation source bundles for programme-specific route requirements.
- CSC and other scholarship-family gold evaluations after the MEXT contract is accepted.
- Catalogue-scale throughput/cost tuning and batch operations after quality gates are met.
