# Scholarship-Directed Convergence Design

## Goal

Extract all important facts published for one scholarship, with exact official-source evidence,
without crawling the provider's entire website or repeatedly paying to extract the same content.

## Product contract

A run starts from one operator-supplied official URL. It must collect the scholarship identity and
provider, degree levels/programmes/subjects, application routes and steps, eligibility including
language requirements, required documents, funding, opening/deadline/selection schedule,
participating institutions when published, and useful official guidance such as FAQs, purpose, and
selection criteria. Every structured fact remains tied to an immutable source excerpt. Full source
text remains available for later RAG use.

`Complete` means that the relevant official-source frontier for each required objective has
converged. It never means that every URL on the host was fetched. A field may be `not stated` only
after all discoverable sources relevant to that objective have been processed. Safety ceilings are
emergency guards, not normal completeness targets.

## Architecture

### 1. Relevant frontier

The crawler classifies each discovered link against unresolved objectives. It queues only links
with a positive scholarship-information signal. News, social, authentication, static assets,
generic navigation, and institution detail sites are excluded unless explicitly supplied as an
authorized supporting source. Ranking determines processing order; a relevance threshold
determines admission.

The supplied URL is always fetched. A sitemap is a fallback discovery source, not an instruction
to fetch every sitemap entry. Sitemap entries pass through the same objective relevance gate.

### 2. Incremental convergence

Acquisition operates in small rounds. Each round persists accepted artifacts plus the remaining
ranked frontier. Extraction then updates objective coverage. The next round re-ranks the persisted
frontier using only unresolved objectives. Processing stops when every required objective is
complete/not-applicable, or when no relevant URL remains. Emergency request, byte, time, model-call,
and cost ceilings still fail closed.

### 3. Scholarship information model

Keep the existing twelve extraction objectives. Add reliable support for scholarship-level
participating institutions and guidance facts. Guidance covers FAQ answers, programme purpose,
selection criteria, and candidate-profile statements without pretending that advice was published
when it was not. Large official enumerations retain an expected count when the source states one;
the list is complete only when the count is met or its relevant source frontier is closed.

### 4. Extraction convergence

Jobs remain grouped by compatible objectives, but split recovery routes objectives to the actual
text slice instead of copying every block-level objective to both children. Successful objective
results remain cached. Initial output allowance is large enough for the expected entity count and
never silently capped below the run allowance for a known large enumeration.

The model supplies a block key and verbatim excerpt. The backend binds offsets deterministically;
provider offsets are accepted only when correct and are repaired from unique excerpt occurrence.
Ambiguous evidence remains reviewable rather than being invented.

### 5. Conditional capabilities and provider health

Native HTML is used directly. Playwright runs only for a detected JavaScript shell. Native PDF
text extraction runs first; Docling OCR runs only for sparse/scanned PDFs. Extraction truncation or
schema validation triggers local re-planning and does not open the Azure health circuit. Provider
circuits are isolated by endpoint and deployment and respond only to transport, throttling, timeout,
or server failures.

### 6. Evidence-only persistence

Materialization never defaults a missing degree to `masters`, a missing required flag to `true`, or
an unknown timezone to `UTC` as if sourced. Unsupported values remain unknown and block automatic
publication where required. Existing exact evidence and human-review gates remain intact.

## Ten acceptance behaviors

1. The supplied official page is always fetched.
2. Only links relevant to unresolved scholarship objectives enter the crawl frontier.
3. News, generic site navigation, and unapproved university websites are not crawled.
4. Pages are acquired and persisted in resumable rounds before paid extraction continues.
5. Coverage is recalculated after each extraction round.
6. Additional pages are fetched only for objectives that remain unresolved.
7. The run stops when the objective-specific relevant frontier converges, not when the domain ends.
8. Published enumeration counts are used to validate lists such as participating universities.
9. Truncation recovery does not duplicate unrelated objectives across text slices.
10. Native PDF and HTML handling remain primary; OCR and browser rendering remain conditional.

## Non-goals

- Crawling every participating university's website.
- Replacing the crawler, browser, database, Azure provider, or document libraries.
- Publishing automatically without the existing review gates.
- Guaranteeing facts that the official scholarship sources do not publish.
