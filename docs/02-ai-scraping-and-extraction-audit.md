# AI, Scraping and Extraction-Layer Audit

Audit date: 24 August 2026  
Repository commit: `f6b3e45dc97c75c7886118d6b972a090ff56bd28`  
Blueprint reviewed: all 26 pages of `scholarship-intelligence-platform-blueprint.pdf`

## 1. Executive verdict

The repository already has a serious evidence-first extraction foundation: safe official-source fetching, immutable artifacts, twelve durable claim objectives, constrained Azure structured output, exact-excerpt validation, scoped claim resolution, conflict/completeness gates and a review-only submission boundary.

It does **not** yet have the complete production extraction layer described by the blueprint. The main missing pieces are:

1. real Crawlee queue/orchestration benefits while retaining the safe fetch boundary;
2. deterministic static-to-browser escalation;
3. canonical semantic evidence blocks for HTML and layout-aware document conversion;
4. source-role, cycle and objective routing before model calls;
5. bundle-level completeness over universal cycle/route/degree/programme scope;
6. a universal graph and approval transaction capable of receiving the expanded result;
7. protected multi-family evaluation beyond the current MEXT-heavy proof.

The correct short-term strategy is to finish this chain in review-only mode first. Enabling a bulk 500-record batch before it passes MEXT, Open Doors and CSC quality gates would create expensive staging data without a trustworthy approval path.

## 2. Current acquisition pipeline

### 2.1 Entry points

Verified entry paths include:

- admin direct URL ingestion through `app/modules/catalogue_ingestion/routes.py`;
- seed ingestion/evaluation through `app/cli/ingest_catalogue_seeds.py` and `evaluate_catalogue_extraction.py`;
- source monitoring through `app/cli/monitor_sources.py`;
- discovery ledger/services under `app/modules/catalogue_ingestion/discovery_*`.

Direct URL input supports a primary official URL and supporting sources. `process_now` defaults to `true`, so the API can perform the entire acquisition/extraction sequence synchronously.

### 2.2 Safe network boundary

The current safe fetch path is a major strength. Source code and tests cover:

- HTTPS-only policy;
- DNS resolution and forbidden IP-range rejection;
- redirect-hop validation;
- robots policy;
- MIME allowlisting;
- byte limits;
- peer-address checks;
- bounded link exploration;
- canonical URL handling.

The relevant implementation is distributed across `url_policy.py`, `sources.py`, `crawler.py`, `safe_multi_url_session.py`, `evidence_acquirer.py` and tests such as `test_bounded_crawler_safe_fetcher.py`, `test_safe_multi_url_session.py` and `test_phase1_security.py`.

The blueprint’s recommendation to retain this as the policy boundary is source-justified. Crawlee must not bypass it.

### 2.3 Bounded crawler

`BoundedOfficialSiteCrawler` ranks scholarship-related linked pages and fetches them sequentially through the injected safe fetcher. Current documented defaults are a small crawl slice: up to ten accepted pages, depth two by default, a hard depth cap of three, a 20 MB total budget and at most 100 considered links per page.

This crawler is safe and predictable, but throughput is inherently limited by serial execution and it has no production browser fallback.

### 2.4 Crawlee status

The current branch is phase `1b.2a`, not the completed Crawlee port.

Verified current:

- `EvidenceAcquirer` interface exists.
- A legacy safe acquirer exists.
- An optional `CrawleeStaticEvidenceAcquirer` exists.
- Multi-URL acquisition can be coordinated while every actual request remains on `SafeSourceFetcher`.
- ADR 0016 explicitly prohibits Crawlee stock HTTP networking until parity is proven.

Not yet implemented/evidenced:

- custom Crawlee HTTP client that performs all network I/O through the safe fetcher;
- multi-page parity with `BoundedOfficialSiteCrawler` fixtures;
- production request-queue worker using Crawlee storage/leases;
- deterministic Playwright fallback;
- calibrated adaptive rendering prediction.

Therefore it is inaccurate to describe Crawlee as the current production acquisition engine. It is an adapter boundary under construction.

## 3. Source artifact and evidence flow

### 3.1 Verified current artifact model

Accepted fetches preserve source URL/final URL, normalized text, content hash, content type, retrieval metadata and excerpts. Extraction attempts are keyed so unchanged compatible work can be reused.

The v3 extraction contract keys an attempt by objective schema, source content hash, prompt hash, provider and model. This allows a successful objective to survive a later failure or budget exhaustion.

### 3.2 Exact evidence validation

Every proposed claim contains a typed value, entity key, explicit scope, exact excerpt and character offsets. The resolver validates the excerpt against the immutable source artifact. Incorrect model-generated spans are rejected; they are not repaired from model memory.

The 23 August MEXT run demonstrates this fail-closed behavior:

- 24 source/objective calls completed;
- 236 claims were accepted with exact evidence;
- invalid spans and unsupported claims were rejected;
- the overall candidate remained `conflict_detected` rather than being presented as complete.

That outcome is a positive trust result, not a failed demo.

### 3.3 Missing target: canonical evidence blocks

The blueprint changes the canonical citation unit from model-authored offsets over flattened text to a stable `EvidenceBlock` with:

- artifact/content hash;
- deterministic block ID;
- structural locator such as DOM path, PDF page/region or table coordinates;
- verbatim text;
- system-computed offsets;
- cycle/route/degree/programme/institution scope hint;
- parser version.

The audited branch has exact artifact/excerpt validation but does not yet implement this complete block contract across HTML and documents. This is the central extraction-layer gap because objective routing, review UI, RAG citations and parser-version reprocessing all depend on it.

## 4. AI/LLM flows

### 4.1 Catalogue claim extraction

When explicitly configured, Azure OpenAI is used through `app/modules/catalogue_ingestion/claim_provider.py`. The provider:

- uses Azure identity/token acquisition rather than exposing credentials to the client;
- requests structured output constrained to the objective-specific schema;
- restricts entity types and field paths by objective;
- enforces response byte/token/cost and retry limits;
- records provider, model, prompt and schema identity;
- treats source content as untrusted data;
- returns claim proposals only.

The model cannot publish, choose arbitrary new URLs, relax validators or repair absent facts from prior knowledge. Deterministic code retains control.

### 4.2 Twelve durable objectives

`ClaimObjective` partitions extraction into:

1. identity;
2. programmes;
3. programme details;
4. application routes;
5. eligibility core rules;
6. eligibility conditions/exclusions;
7. document names/order;
8. document conditions/stage;
9. document original/copy counts and form year;
10. document translation/certification/notes;
11. funding;
12. deadlines, events, steps and official resources.

This decomposition is correct and should be retained. The current orchestration problem is that service loops can attempt every objective for every source. `catalogue_ingestion/service.py` builds coverage for every `ClaimObjective` and iterates objectives within source processing. That multiplies calls and semantic noise.

The blueprint’s correction is to route only unresolved objectives to source roles that can answer them. For example, a funding page should not receive document-copy extraction, and a result notice should not receive programme modelling.

### 4.3 Claim resolution

Verified deterministic resolution includes:

- schema validation;
- exact excerpt/offset membership;
- bounded alias normalization;
- intake-year/cycle mapping;
- deadline versus arrival/screening/result/study-period separation;
- official resource provenance checks;
- programme-scoped fact preservation;
- primary-source priority within an authority tier;
- conflict detection;
- completeness computation;
- partial state when substantive invalid claims are dropped.

Current limitations reproduced in the MEXT proof include competing title variants, coarse entity keys, rejected degree/programme spans, incomplete application steps, delegated local deadlines and flattened overview tables.

### 4.4 Assistant AI flow

The student assistant is not currently a remote generative RAG system. `EvidenceTemplateProvider` returns the backend-composed structured response unchanged. Any other provider name produces `AssistantProviderUnavailable`.

Current assistant retrieval is SQL over active opportunities with token-expanded `ILIKE`, followed by source verification/freshness filtering and citation-first answer construction. This is a safe baseline but not the blueprint target of scoped PostgreSQL FTS + pgvector retrieval over approved evidence blocks.

### 4.5 Document Lab AI flow

Document Lab has a consent-gated provider interface and structured editorial feedback schema. `get_provider()` always returns `UnavailableDocumentProvider`; no production remote adapter is implemented. Thread-based timeout fallback does not stop non-cooperative work after the caller times out.

This provider is separate from scholarship catalogue extraction and must remain in a separate tenant-private storage/index boundary.

### 4.6 Discovery AI flow

Azure web-search discovery provider and durable discovery ledger code exist. They support bounded queries, lead limits, cost accounting, officiality checks and promotion/binding concepts. No production route/CLI/worker was found that turns the full new discovery subsystem into an operating catalogue pipeline. It should be reported as implemented foundation, not deployed behavior.

## 5. Current extraction sequence

The source-verified flow is:

1. Create candidate and candidate source records.
2. Canonicalize and validate the URL.
3. Fetch the primary source through the safe fetch boundary.
4. Optionally crawl a bounded set of linked pages.
5. Persist normalized source artifacts and content hashes.
6. For each source, run objective extraction/attempt reuse.
7. Normalize and validate each claim against its artifact.
8. Resolve identity, scope, ontology and conflicts.
9. Compute objective coverage/completeness.
10. Save the result as review-only staging.
11. Reject expanded submission if it is not compatible with the legacy materializer.
12. Permit explicit review/materialization only for the narrow compatible graph path; never auto-publish.

The target sequence in the blueprint inserts three missing decisions before model extraction:

`source role + cycle classification -> canonical evidence blocks -> objective routing`

and replaces per-page completeness with bundle-and-scope completeness after resolution.

## 6. Scraping and extraction reliability findings

| Severity | Verified finding | Evidence | Effect |
| --- | --- | --- | --- |
| High | Direct URL ingestion defaults to synchronous processing | `catalogue_ingestion/schemas.py:147`, `routes.py:53` | HTTP timeout/retry can duplicate or strand expensive work |
| High | Crawlee currently delegates to legacy safe fetcher | `crawlee_static_acquirer.py`, phase 1b progress/ADR 0016 | Safety is preserved, but queue/concurrency benefits are not delivered |
| High | Source/objective execution is serial and overly broad | `catalogue_ingestion/service.py`, `ClaimObjective` loops | Latency and cost scale with pages x objectives |
| High | Expanded v3 cannot reach universal graph approval | `service.py:853-864`, `_legacy_graph_compatible()` | Review-ready extraction cannot become a complete canonical record |
| High | Flattened PDF text loses table/layout scope | current pypdf path and MEXT result | Wrong programme/degree/document associations or blocked completeness |
| High | Graph materializer is MEXT-specific | `graph_materializer.py` hardcoded MEXT title/Japan/Tokyo values | Unsafe for universal scholarship families |
| Medium | MEXT topic compatibility guard does not prove MEXT identity when root lacks marker | `_crawler_child_matches_root()` | Non-MEXT roots can bypass the marker-specific check |
| Medium | Provider timeout can outlive caller | thread executor patterns | Work/cost may continue after a timeout response |
| Medium | Source-check commit and lease completion are separate | `source_monitor.py:417-435` | Recorded check can coexist with stale lease/failure status |
| Medium | No deterministic static/browser sufficiency checker | no production implementation found | Dynamic sources require manual handling or incomplete data |

## 7. Blueprint target and exact implementation gap

| Blueprint target | Current evidence | Status |
| --- | --- | --- |
| `EvidenceAcquirer` abstraction | Present | Verified current |
| Crawlee static orchestration | Adapter foundation only; safe fetch delegates | Partial |
| Controlled Playwright fallback | Feature flag/dependencies, no catalogue runtime path | Missing |
| Docling document conversion | No production adapter found | Missing |
| OCR after text sufficiency | No complete catalogue path found | Missing |
| Immutable source artifact/version | Strong source artifact/hash foundation | Partial-to-strong |
| Canonical evidence blocks | Exact excerpts exist, structural block model not complete | Partial |
| Source-role and cycle classifier before extraction | Related classification foundations, not wired as complete planner | Partial |
| Objective routing by unresolved completeness | Twelve objectives exist, broad serial loops remain | Missing in orchestration |
| Bundle-level completeness | Deterministic completeness exists, universal scoped bundle contract incomplete | Partial |
| Universal graph approval transaction | Legacy + graph coexist; expanded v3 blocked | Missing |
| Five-family protected suite | MEXT strong; Open Doors lessons documented; full suite not evidenced | Missing |
| 500-record launch operation | No execution evidence | Not evidenced |

## 8. Next-week extraction-layer definition of done

To truthfully say “the extraction layer is finished” next week, the deliverable should be a production-shaped **review-only** pipeline with these gates:

1. All network traffic remains behind the tested safe fetch policy.
2. API requests enqueue durable work instead of executing the long run inline.
3. Static acquisition works through the Crawlee adapter with parity fixtures.
4. HTML and complex documents produce deterministic, versioned evidence blocks.
5. Browser/OCR paths remain off unless deterministic sufficiency checks authorize them.
6. Source role and cycle are assigned before objective selection.
7. Only applicable unresolved objectives call the model.
8. Every accepted claim cites one or more exact block IDs.
9. Resolver represents `resolved`, `unknown`, `delegated`, `not_applicable`, `partial`, `conflict` and `failed` per scope.
10. Rerunning an unchanged source performs zero compatible model calls and creates no duplicate entities.
11. MEXT and Open Doors captured fixtures pass the protected invariants.
12. The output is a review proposal with no automatic public write.

The universal graph approval path can follow immediately, but it should not be faked by expanding the MEXT-specific materializer.

## 9. Recommended extraction architecture

### Acquisition

- Keep `EvidenceAcquirer` stable.
- Finish a custom Crawlee HTTP bridge that calls `SafeSourceFetcher` for every request.
- Store durable requests/jobs in PostgreSQL first; preserve a queue interface for later Service Bus.
- Implement `ContentSufficiencyChecker` with deterministic thresholds.
- Run Playwright in a separately isolated worker with no database credentials.

### Normalization

- Define versioned `SourceArtifact` and `EvidenceBlock` contracts.
- HTML blocks: heading, paragraph, ordered/unordered item, table row, key-value pair and form instruction with DOM locator.
- Document blocks: page/region, reading order, table coordinates and hierarchy.
- Use Docling behind `DocumentConverter`; retain pypdf as preflight/fallback.
- OCR only pages below a measured text-sufficiency threshold.

### Extraction

- Add `SourceRoleClassifier` and cycle classification before model work.
- Build an objective-routing matrix by source role.
- Query completeness state and call only unresolved objectives.
- Keep objective attempts reusable by artifact hash + parser + prompt + schema + provider + model.
- Enforce per-run token/cost/time budgets.

### Resolution and review

- Compute offsets from selected blocks; never accept arbitrary model offsets.
- Strengthen deterministic entity keys for programme, subject area, document, stage and route.
- Resolve at scholarship bundle + scope, not page.
- Present conflicts, invalid claims and missing mandatory objectives first.
- Keep approval and publication as separate explicit transactions.

## 10. Test and evaluation requirements

### Unit/contract

- safe URL, redirect and peer-address policy;
- Crawlee-safe-fetch bridge parity;
- canonical block determinism and parser versioning;
- source-role and cycle classification;
- objective-routing matrix;
- claim block membership and exact excerpts;
- ontology and entity-key validation;
- bundle-level completeness states;
- queue lease, retry, dead-letter and idempotency contracts.

### Fixture integration

- MEXT PDFs and overview tables;
- Open Doors cycles, stages, tests and subject areas;
- CSC institution/provider ownership and duplicate identity;
- at least one GKS/DAAD-style programme structure;
- Erasmus Mundus consortium/programme routes.

### Security/adversarial

- SSRF, DNS rebinding and redirect chains;
- crawler traps and unbounded query URLs;
- prompt injection embedded in HTML/PDF;
- malformed documents, archive/decompression bombs and oversized files;
- stored-XSS strings in reviewer/public projections;
- browser sandbox, egress and secret-isolation tests.

### Acceptance metrics

- zero invented evidence;
- zero cross-cycle leakage in the gold suite;
- exact canonical scholarship count;
- complete applicable document lists with conditions/stages;
- zero unchanged-source compatible model calls;
- zero duplicate graph writes on rerun;
- static/browser block equivalence where both paths are valid;
- measured cost per review-ready record and reviewer correction rate.

## 11. Final assessment

The current extraction layer is credible and safety-oriented, but “complete” currently means **review-only v3 staging with MEXT evidence**, not universal production ingestion. The fastest responsible route to live is to finish canonical evidence blocks, objective routing, durable orchestration and two-family protected proof next week, then complete universal graph approval and the five-family release gate before the 500-record public catalogue.
