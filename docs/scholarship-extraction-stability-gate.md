# Scholarship extraction stability gate

## Purpose

This gate answers one question: is the catalogue pipeline ready to expand from a few
successful scholarships to hundreds without adding scholarship-specific code after every
run?

A successful run is evidence for one source shape. It is not proof of general stability.
The system is stable enough to scale only after it succeeds across different source
archetypes, fails visibly when evidence is unavailable, and preserves the same semantics on
cached reruns.

## Representative source archetypes

| Archetype | Main risk | Representative proof |
| --- | --- | --- |
| Multi-page dynamic official site | Important facts split across rendered navigation, schedules, FAQs, and track pages | Open Doors Russia |
| Multi-page editorial official site | Eligibility, timeline, guidance, courses, and country rules live on separate pages | Chevening |
| Official PDF bundle | Tables, footnotes, application forms, and changing annual guidelines | MEXT |
| Government portal plus linked documents | Scholarship umbrella, multiple routes, external application portal, PDFs/images | CSC via HEC |
| Programme database/detail portal | Search results are not scholarship records; detail pages and annual PDFs may differ | A specific DAAD programme |
| Conventional official HTML | Baseline crawl and extraction behaviour | Commonwealth |

Multilingual, blocked, login-only, and heavily client-rendered sources are capability states,
not excuses to create unsupported facts. They must either use an approved acquisition path or
be marked explicitly for review.

## Development, validation, and holdout rule

- Open Doors is the development probe. A failure may justify a generic pipeline change.
- CSC, MEXT, and Commonwealth are regression fixtures. A generic change must not damage them.
- Chevening is an untouched validation case. Do not add Chevening-specific parsing or routing.
- One specific DAAD programme is the holdout. Freeze the implementation before running it.
- A scholarship name, domain, or page-specific selector must never appear in core extraction
  logic. Source adapters are allowed only for reusable content classes such as HTML, rendered
  HTML, PDF, image/OCR, sitemap, or authenticated/manual evidence.

## Gate A: acquisition completeness

A candidate passes acquisition only when:

1. The official entry page is fetched and its canonical URL and fetch status are recorded.
2. Relevant first-party pages and documents are discovered for identity, eligible study
   routes, funding, eligibility, required documents, application process, deadlines, and
   official application links.
3. Dynamic links, downloadable rules, FAQs, and track/subject pages are considered; unrelated
   news, social pages, navigation duplicates, and generic university marketing pages do not
   consume the evidence budget.
4. Every excluded or unreachable high-value source has a machine-readable reason.
5. Page, depth, time, or byte limits cannot silently truncate a candidate. Hitting a limit
   makes the candidate incomplete or review-required.
6. The acquired source manifest is inspectable before any model call.

## Gate B: evidence and semantic completeness

Every objective has one explicit state: `complete`, `not_stated`, `conflicting`,
`unreachable`, or `needs_review`. An empty field is not a valid state.

The review record must cover, where officially stated:

- scholarship identity, sponsor, country, and current intake/status;
- degree levels, programme/subject routes, study mode, and duration;
- funding components with scope, value, currency, cadence, and exclusions;
- eligibility rules, including nationality/residency, age, education, language, experience,
  and route-specific conditions;
- required documents, with stage, route, applicant type, and conditionality;
- application routes, ordered steps, portal/official links, nomination or university stages;
- deadlines and other dated events with timezone and scope;
- official contacts, FAQs, result/selection information, and important applicant warnings.

All accepted facts require an exact, resolvable citation to fetched evidence. Claims must keep
their route, level, subject, stage, and applicant scope; globalising a scoped fact is a failure.
Unsupported URLs and inferred facts are quarantined rather than published.

## Gate C: robustness and repeatability

- No scholarship-specific core logic is introduced.
- Fresh and cached runs produce equivalent normalized meaning.
- Unchanged evidence causes no new extraction call.
- Changed evidence invalidates only affected work where supported; otherwise the reason for a
  full refresh is recorded.
- Network, rendering, conversion, model, budget, and schema failures fail closed and remain
  diagnosable by subsystem.
- Re-running a candidate does not create duplicate programmes, routes, documents, or facts.

## Gate D: product projection

The stored evidence may be rich, but the scholarship detail page must project a clean student
view:

1. Overview and current status
2. Degree levels and available routes
3. Funding
4. Eligibility
5. Required documents
6. How to apply
7. Deadlines and timeline
8. Official links and sources
9. Optional FAQs, selection guidance, and verified applicant advice behind progressive
   disclosure

Storage completeness and page compactness are separate concerns. Do not delete useful evidence
to make the UI shorter.

## Gate E: cost and scale

Record per candidate: pages attempted/fetched/accepted, bytes, model calls, cache hits, cost,
duration, accepted/quarantined facts, objective states, and review reasons.

Cost is optimized after correctness by pruning irrelevant sources, reusing fetched evidence,
hashing normalized content, batching compatible objectives, and extracting only changed or
unresolved evidence. A low-cost incomplete record does not pass.

## Go/no-go rule

Expansion is allowed only when all of the following are true:

- Open Doors passes after generic fixes, if any.
- CSC, MEXT, and Commonwealth still pass their existing regression evidence.
- Chevening passes without Chevening-specific code.
- The frozen implementation passes one specific DAAD holdout without domain-specific code.
- There are zero silently missing critical objectives and zero accepted facts without exact
  citations.

If the holdout exposes a new general capability class, fix it once and choose a new untouched
holdout. If it only exposes a fact absent from official evidence, record `not_stated`; do not
teach the system to guess. If repeated holdouts require scholarship-specific logic, the system
is not ready for a 500-record wave.

After passing, expand in measured canaries: 10, then 25, then 50, with automatic stop conditions
for citation loss, critical objective gaps, crawl-limit truncation, abnormal cost, or a rising
manual-review rate.
