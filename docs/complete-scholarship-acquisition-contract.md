# Complete Scholarship Acquisition Contract

- Status: Architecture and executable acceptance contract
- Version: `scholarship-acquisition.v1`
- Date: 2026-08-20
- Runtime evidence: none; target scenarios are gates, not capability claims
- Related contracts: `scholarship-information-contract.md`, `pr5-web-discovery-spec.md`

## 1. Outcome

The acquisition system is a repeatable scholarship-intelligence pipeline, not a single-page
scraper. An operator may provide a public scholarship name, one official root URL, or a public seed
document. The system is responsible for finding and maintaining the smallest authoritative source
set that can explain the scholarship's real structure and decision-critical facts.

The target flow is:

```text
name / URL / public document
  -> target identities
  -> official-source discovery
  -> safe source acquisition
  -> routes, documents, institutions, programmes and related awards
  -> per-source structured claims
  -> field evidence with scope
  -> deterministic relationship and completeness decisions
  -> exception-only human review
  -> existing publication workflow
  -> change-driven refresh
```

The normal operating model must not require a person to find every follow-up URL. Human work is
reserved for unresolved ownership, conflicting official evidence, access-controlled sources and
publication approval.

## 2. Current implementation boundary

| Capability | Current state |
| --- | --- |
| Structured JSON/CSV/text seed intake | Implemented |
| Text PDF seed parsing | Implemented, line-oriented and heuristic |
| Scanned/image-only PDF intake | Fail-closed; OCR adapter is not implemented |
| Name-only query/objective planning | Implemented |
| Live name-to-Web-Search provider | Not implemented |
| Durable discovery attempts, budgets and URL leads | Implemented through PR5 Slice 5 |
| Contextual discovery officiality | Next PR5 slice |
| Safe HTTPS fetch with SSRF/redirect/robots/MIME limits | Implemented |
| Bounded relevant same-host crawl | Implemented behind a disabled flag |
| Persist each accepted crawled page | Implemented |
| Multi-source evidence bundle | Not implemented |
| Azure extraction from one selected source | Implemented and calibrated |
| Per-source extraction across the collected source set | Not implemented |
| Graph entities, evidence and relationship rules | Implemented foundation |
| Automatic acquisition-to-graph population | Not complete |
| Change hashes and source monitoring foundation | Implemented |
| Complete change-driven graph refresh | Not complete |
| Azure-hosted worker/database/runtime | Defined in infrastructure code, not deployed |

No later section changes these facts. Passing the contract-schema tests means the target is
well-formed; it does not mean the runtime has passed a CSC, MEXT or PDF acquisition.

## 3. Input contracts

### Name

A name such as `MEXT Scholarship` starts with zero operator-supplied URLs. Deterministic objectives
and provider hints drive a bounded live-discovery adapter. Search output remains untrusted URL leads.

### URL

One URL such as an official CSC root is an initial lead, not permission to trust its contents. It
passes URL policy, contextual ownership, safe fetch, redirect revalidation and target-content checks.
The accepted root becomes the starting frontier for authoritative linked pages and documents.

### Document

A public text PDF/list may enumerate one or many seed identities. Each identity receives an
independent acquisition run and deduplication check. The seed document is discovery context, not
evidence for scholarship facts unless it is separately acquired and verified as an official source.

Scanned PDFs use OCR only after lightweight text extraction proves insufficient. Password-protected,
login-only and CAPTCHA-protected content remains an explicit exception.

## 4. Discovery and traversal

The crawler does not mirror an entire website and it does not use a permanent three-page rule.
Traversal is objective-driven and bounded:

1. start from the strongest verified owner root;
2. parse HTML links, PDF links, tables, pagination and downloadable indexes;
3. rank links against unresolved objectives such as funding, eligibility or institutions;
4. fetch through the shared safe-fetch boundary;
5. classify final owner and scope after every redirect;
6. stop when objectives are satisfied, the frontier is exhausted or a budget ends;
7. retain explicit missing/failure reasons.

Initial limits remain conservative and configurable. Increasing a page limit must never replace
completeness logic. A ten-page crawl that misses the authoritative institution PDF is a failure; a
two-page crawl that resolves every objective can be complete.

Cross-domain expansion is allowed only through a typed relationship. Examples are an embassy route,
a reviewed participating institution or an application portal. A link alone does not establish that
relationship.

## 5. Multi-source extraction

Collected texts must not be blindly concatenated into one prompt. Each source is extracted
independently with:

- immutable source/snapshot identity;
- final URL and owner/scope assessment;
- bounded normalized content;
- structured claims;
- exact evidence excerpts;
- extraction schema/provider/model version;
- cost and content hash.

The deterministic merger then attaches claims to:

```text
SCHOLARSHIP -> CYCLE -> TRACK -> INSTITUTION -> PROGRAMME
```

A global provider page may support global funding. An embassy page may support a country-route
deadline. A university page may support local requirements. A more local source cannot silently
rewrite a global fact.

Conflicting current official claims remain a conflict. Missing information remains unknown. Neither
state is repaired through model memory or third-party text.

## 6. Completeness-driven loop

After each acquisition pass, deterministic completeness produces unresolved objectives. Only those
objectives authorize additional preplanned discovery or crawl work.

```text
acquire -> extract -> merge -> evaluate completeness
              ^                    |
              | unresolved bounded objectives
              +--------------------+
```

The loop is bounded by query, source, byte, model-call, token, time and estimated-cost ceilings. It
cannot generate recursive searches from model prose or search snippets.

Completion means each required objective is either:

- resolved with current scoped official evidence; or
- explicitly unknown after the authoritative source set was checked.

An unresolved conflict is not complete.

## 7. CSC normative scenario

Input is one reviewed CSC root URL. The system must:

1. retain exactly one canonical Chinese Government Scholarship identity;
2. discover current provider pages, route material, guides and authoritative list documents;
3. parse the authoritative participating-institution collection completely, including pagination,
   tables or documents;
4. create institution participation relationships, not additional CSC scholarships;
5. preserve embassy/provider/university authority and fact scope;
6. discover local sources only where the official structure or an unresolved local objective
   requires them;
7. separate a genuinely institution-owned award only after the independence gate passes;
8. resolve or explicitly mark unknown all required core objectives;
9. attach evidence to every resolved Tier 0/1 fact;
10. create no duplicate scholarship, relationship or unchanged-source model call on rerun.

The runtime must not hardcode `280`. It compares the number of unique graph relationships with the
number of unique items parsed from the current authoritative collection. The initial protected
vertical slice requires at least ten representative institutions and full equality with whatever
authoritative collection is exercised. A later production CSC run must process the complete current
collection under the same rule.

## 8. MEXT portability scenario

Input is the public name `MEXT Scholarship` with no URL. The system must resolve the canonical owner,
find official roots, preserve embassy and university recommendation routes beneath one scholarship,
and complete the core fact areas with scoped citations.

This scenario proves the architecture is not hardcoded to CSC pages, labels or Chinese institutions.

## 9. Document intake scenario

A synthetic text PDF contains three scholarship seed identities and no operator-supplied URLs. The
system must enumerate three candidates, run each through independent official-source discovery and
deduplication, and produce three reviewed canonical outcomes without manual URL completion.

This gate covers text-document orchestration. Separate fixtures are required before OCR or table
parsing can be claimed for scanned/complex documents.

## 10. Acceptance invariants

The machine-readable manifest is
`tests/fixtures/catalogue_acquisition/complete_acquisition_v1.json`. The evaluator returns stable
violation codes and requires:

- exact seed and canonical scholarship counts;
- zero structural inflation;
- required owner classes present;
- every required objective complete, source-checked and scope-preserving;
- evidence for every resolved objective;
- no unresolved conflict;
- graph collection counts equal the parsed authoritative collection where required;
- zero duplicate graph items;
- no manual follow-up URL outside the scenario budget;
- zero automatic publication;
- zero new canonical entities, relationships or sources on unchanged rerun;
- zero model calls for unchanged source hashes.

Future local, staging and protected live evaluators must emit `AcquisitionOutcome` from actual runtime
records and pass `evaluate_acquisition_outcome`. Synthetic passing examples test the evaluator only.

## 11. Durable upgrade boundaries

The system remains upgradeable by keeping these interfaces independent:

- seed/document parsers;
- Web Search provider;
- URL policy and safe fetcher;
- HTML/PDF/OCR/browser content adapters;
- owner/scope assessment;
- per-source extraction provider;
- evidence merger and completeness evaluator;
- graph repositories;
- publication review;
- freshness scheduler.

Provider changes, improved parsers and larger budgets must not alter scholarship identity, evidence,
scope or publication rules.

## 12. Implementation order

1. Complete PR5 contextual assessment, known-target binding, authoritative fetch promotion,
   fail-closed configuration, fake-provider integration and protected live discovery proof.
2. Add objective-driven linked-document/table traversal and source-set manifests.
3. Add per-source extraction and deterministic multi-source evidence merge.
4. Feed actual outcomes into this acceptance evaluator.
5. Pass the CSC ten-institution vertical slice, then the complete authoritative collection.
6. Pass MEXT name-only portability.
7. Add OCR and browser fallback behind independent gates.
8. Deploy manual Azure staging jobs and measure quality, cost and correction rate.
9. Enable change-driven refresh only after acquisition and idempotency gates pass.

Bulk catalogue construction begins only after CSC and MEXT pass. A larger manual spreadsheet is not
a substitute for these end-to-end proofs.
