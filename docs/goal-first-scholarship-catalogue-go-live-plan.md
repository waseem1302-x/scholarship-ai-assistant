# Goal-first scholarship catalogue go-live plan

Status: proposed implementation plan  
Owner: Wasim  
Created: 2026-08-27  
Primary outcome: launch a trustworthy catalogue covering the major international scholarships available to Pakistani students, with at least 500 distinct scholarship routes when the official-source inventory supports that number.

## 1. Product goal

The immediate goal is not to extend the architecture. It is to produce a useful, live scholarship catalogue that powers:

- the React scholarship catalogue;
- the AI scholarship assistant;
- student-profile matching;
- deadline and document planning;
- future recommendation and application-management features.

The delivery sequence is:

`official programme inventory -> source bundle -> extraction -> evidence validation -> review -> publication -> freshness monitoring`

The number 500 is a scale milestone, not permission to pad the catalogue. A smaller catalogue that covers every major relevant programme accurately is more valuable than 500 duplicated, stale, or incomplete records. Expansion continues until both conditions are met:

1. the major global and government-funded scholarship families relevant to Pakistani applicants are covered; and
2. at least 500 distinct, useful scholarship routes are review-ready or published.

## 2. What counts as one catalogue record

A record represents a distinct applicant decision: a scholarship route with its own meaningful combination of provider, programme or degree scope, eligibility, application method, or deadline.

Examples:

- A single named scholarship with one process is one record.
- An umbrella programme with country, university, degree, or nomination routes may produce multiple records when those routes materially differ.
- The same scholarship translated into multiple languages is still one record.
- Mirrors, duplicate URLs, yearly copies, and marketing pages do not create extra records.
- A closed cycle does not create a duplicate; it becomes historical cycle data under the same canonical route.

This rule prevents an artificial “500” created by duplicating programme pages.

## 3. Definition of a complete scholarship

A scholarship is ready for publication only when all 15 existing publication-readiness dimensions pass using current official evidence:

1. scholarship identity and canonical programme family;
2. provider and destination country or region;
3. degree level and programme/route scope;
4. current application cycle, or an official `not_yet_announced` state;
5. deadline, rolling status, or route/country-specific deadline rule;
6. official application URL and application method;
7. tuition coverage;
8. living stipend, including amount, currency, and frequency when stated;
9. funding classification computed from the supported components;
10. nationality and geographic eligibility, including Pakistan relevance;
11. academic requirements or official programme-specific variation;
12. language and test requirements, including stated exceptions;
13. required documents or the official route where programme-specific documents are defined;
14. fresh, fetchable, hash-backed official source artifacts;
15. no unresolved evidence conflict or duplicate identity.

Optional benefits should also be extracted when officially stated: airfare, insurance, accommodation, visa costs, research allowance, settlement allowance, family allowance, and other programme-specific benefits. `Not stated`, `not applicable`, and `not covered` must remain distinct.

Every public fact must retain its official URL, exact supporting excerpt, retrieval time, source hash, and applicable programme/cycle/route scope. Unsupported values remain review blockers; the model must never fill them from memory.

## 4. Goal-first operating rules

1. Use the existing ingestion, evidence, identity, review, and publication components. Replace or redesign them only when a demonstrated blocker prevents catalogue delivery.
2. Keep AI calls disabled and the worker stop switch armed during code changes and source preparation.
3. Acquire and validate the official source bundle before paying for extraction.
4. Work in measurable catalogue waves. Do not begin a larger wave until the smaller wave meets its exit gate.
5. Keep all generated records private and `needs_review` until the publication gate passes and an administrator approves them.
6. Treat official programme/provider/government/university pages and their official PDFs as fact evidence. Blogs, search snippets, aggregators, and model knowledge are discovery leads only.
7. Measure progress in complete scholarship routes, not code files, migrations, endpoints, or raw candidates.
8. Do not start post-launch architecture projects while a current delivery blocker can be solved in the existing design.

## 5. Delivery scoreboard

The project dashboard should report these numbers after every batch:

| Metric | Meaning |
|---|---|
| Inventory | Unique routes approved for investigation |
| Sources ready | Candidates with a sufficient official source bundle |
| Extracted | Candidates with completed model objectives |
| Review-ready | Candidates passing all 15 readiness dimensions |
| Published | Administrator-approved, public records |
| Pakistan confirmed | Officially eligible for Pakistani nationals |
| Pakistan unresolved | Eligibility needs route/cycle review |
| Blocked | Robots, login, unsupported document, missing evidence, conflict, or duplicate |
| Stale | Published source evidence beyond its freshness window |
| Cost per complete record | Total extraction cost divided by review-ready records |

The headline milestone is `published`, supported by `review-ready`; raw discovered or extracted counts do not constitute success.

## 6. Milestone 0 — preserve the work and restore safe control

Purpose: protect the existing foundation and make the next pilot deliberate.

### Implementation work

- Preserve the current dirty worktree on a dedicated continuation branch before broad edits.
- Review the uncommitted Phase 0–7 changes and separate real implementation from later scratch artifacts.
- Keep `.local/env/catalogue-worker.env`, capability receipts, credentials, Azure CLI state, and runtime artifacts out of Git.
- Remove or repair the malformed generated audit reports and unfinished diagnostic scripts before committing.
- Restore the local `STOP` file or set AI ingestion false before recreating any worker.
- Record the live Azure configuration and the successful capability receipt in a sanitized operator note.
- Do not commit the service-principal secret. Schedule credential rotation before its 2026-09-23 expiry.

### Exit gate

- The intended Phase 0–7 code is recoverable in Git.
- Secret and runtime files remain ignored.
- A worker restart cannot make an unapproved paid call.
- The repository passes formatting/lint checks for production code and tests.

## 7. Milestone 1 — prove one complete DAAD scholarship route

Purpose: obtain the first real end-to-end success before scaling.

### 7.1 Consolidate the evidence bundle

- Select one specific DAAD EPOS route, not the general DAAD umbrella.
- Attach its programme page, official course listing, benefits/funding page, eligibility page, application instructions, deadline information, and required-document source to one canonical candidate.
- Reuse already acquired artifacts by content hash instead of fetching or extracting them again.
- Resolve the robots-blocked source through another official page, an official downloadable document, or an explicit review blocker. Do not bypass robots restrictions.
- Confirm that every source belongs to the same scholarship family, route, and cycle.

### 7.2 Remove extraction blockers

- Make source routing select only the objectives relevant to each artifact.
- Align the hard model-call limit with the actual routed objective count. The current combination—12 objectives, routing off, and an eight-call ceiling—cannot finish.
- Make the worker run the complete preflight and fail closed before claiming a paid extraction run.
- Require a current, matching capability receipt at worker runtime.
- Include prompt, schema, URL/context, source text, and output allowance in pre-call budget reservation.
- Require an accepted terminal response state, no refusal, no content-filter termination, valid usage, and valid strict-schema output for every production call.
- Preserve capability and extraction evidence as append-only run history instead of overwriting the previous result.
- Pin or explicitly review model-version changes so an automatic Azure deployment upgrade cannot silently invalidate the extraction contract.

### 7.3 Run the controlled pilot

1. Run zero-cost acquisition and preflight.
2. Review the exact candidate, sources, objectives, maximum calls, token ceiling, and maximum cost.
3. Obtain explicit owner approval for the paid extraction.
4. Process only that DAAD candidate with zero provider retries.
5. Stop the worker immediately after the candidate completes.
6. Compare every extracted fact with its cited official excerpt.
7. Resolve conflicts and validate the resulting publication-readiness report.

### Exit gate

- One DAAD route completes without an unhandled error.
- All applicable extraction objectives finish within the approved budget.
- Every public fact is supported by exact official evidence.
- All 15 readiness dimensions pass or use an allowed evidence-backed semantic state.
- No duplicate, source conflict, or unsupported value remains.
- The result appears correctly in admin review and can be approved without editing the database manually.
- Actual tokens, calls, latency, cost, and review corrections are recorded.

If this gate fails, fix only the demonstrated failure and repeat the same candidate. Do not expand the architecture or start a larger batch.

## 8. Milestone 2 — ten-scholarship golden cohort

Purpose: prove the pipeline across the most important source and programme patterns.

The initial cohort should contain one canonical route from each family, subject to current official Pakistan eligibility:

1. DAAD EPOS;
2. Chinese Government Scholarship/CSC;
3. Erasmus Mundus Joint Masters;
4. Chevening;
5. Commonwealth Scholarship;
6. Fulbright through USEFP Pakistan;
7. MEXT;
8. Global Korea Scholarship/GKS;
9. Türkiye Scholarships;
10. Stipendium Hungaricum.

This cohort intentionally covers umbrella programmes, programme-specific routes, government nomination, university nomination, PDFs, HTML, multiple deadlines, and varied document requirements.

### Implementation work

- Build a reviewed source manifest for each route before extraction.
- Add captured fixtures for each distinct official-source pattern that caused a parsing or routing change.
- Run candidates individually at first, then as a batch only after individual success.
- Record false positives, missed facts, incorrect scope, evidence mismatches, duplicate suggestions, and manual corrections.
- Convert repeated review corrections into targeted schema, prompt, routing, or resolver improvements.
- Re-run changed logic against the entire golden cohort without new paid calls when cached artifacts and responses are sufficient.

### Exit gate

- Ten routes reach review-ready status.
- There are zero unsupported public facts.
- Every deadline, eligibility rule, funding component, application URL, and required-document claim has correct route/cycle scope.
- Schema-valid response rate is at least 98% across calls.
- All failures are classified and resumable rather than silently discarded.
- The measured cost per complete scholarship is known.
- The administrator can review a scholarship from source artifact through final public preview in one workflow.

## 9. Milestone 3 — build the authoritative Pakistan-relevant inventory

Purpose: decide what must be covered before spending money on bulk extraction.

Create one versioned inventory using the existing private seed mechanism. Each inventory row should include:

- canonical scholarship family and proposed route;
- provider and destination country/region;
- official programme URL;
- other known official source URLs;
- government, multilateral, foundation, or university category;
- degree/research level;
- Pakistan eligibility: `confirmed`, `excluded`, `unclear`, or `varies_by_route`;
- usual application season when officially known;
- priority tier;
- acquisition, extraction, review, publication, and freshness status;
- canonical identity/duplicate notes.

### Priority A — flagship and government programmes

Inventory these first because they have the highest applicant value and broadest recognition:

- Pakistan/HEC and bilateral overseas scholarship routes;
- Chevening, Commonwealth, and Scotland/UK routes currently open to Pakistan;
- Erasmus Mundus and other directly applicable EU-funded study routes;
- DAAD EPOS and other DAAD programme families relevant to international applicants;
- CSC and distinct Chinese university/government routes;
- MEXT and relevant Japanese government/university routes;
- GKS and relevant Korean government routes;
- Türkiye Scholarships;
- Stipendium Hungaricum;
- Fulbright/USEFP Pakistan;
- Australia Awards, Manaaki New Zealand, and other national programmes only where current official Pakistan eligibility is confirmed;
- Saudi, UAE, Qatar, Brunei, and other government/university routes with official international admissions and funding evidence;
- France Eiffel, Italy MAECI, Swiss Government Excellence, Swedish Institute, Belgian and Dutch government-backed routes where applicable;
- Joint Japan/World Bank, ADB–Japan Scholarship Program, Islamic Development Bank, Aga Khan Foundation, and other major multilateral programmes.

### Priority B — globally prominent university scholarships

Include distinct official routes such as:

- Rhodes and Clarendon at Oxford;
- Gates Cambridge and other major Cambridge routes;
- Knight-Hennessy Scholars;
- Schwarzman Scholars and Yenching Academy;
- major named full-cost scholarships at leading universities in the UK, Europe, North America, Asia, Australia, and the Middle East;
- Mastercard Foundation Scholars Program routes at participating universities when each route has distinct official eligibility and application instructions.

### Priority C — breadth expansion

- Add reputable fully funded and high-value partial scholarships from official university catalogues.
- Add discipline-specific, research, doctoral, women-focused, development, climate, health, STEM, and public-policy programmes relevant to Pakistani applicants.
- Exclude low-value tuition discounts, competitions, expired one-off notices, and programmes with no verifiable official source unless product scope explicitly includes them.

The named programmes above are inventory leads, not assertions of current eligibility. Each route enters extraction only after current official sources confirm its scope.

### Exit gate

- Every intended major scholarship family has an inventory decision.
- The list contains no obvious aliases or mirror duplicates.
- At least 500 legitimate routes are identified, or the owner approves a smaller number because comprehensive major-programme coverage has already been reached.
- Every Priority A item has a verified official entry URL and Pakistan-eligibility status or an explicit review task.

## 10. Milestone 4 — create a repeatable catalogue production line

Purpose: turn the golden workflow into steady catalogue output.

### Batch stages

Every batch follows the same gates:

1. **Inventory:** select approved routes and remove duplicates.
2. **Acquire:** fetch official HTML/PDF sources without AI.
3. **Bundle review:** confirm ownership, route, cycle, roles, and coverage.
4. **Extract:** run only candidates with sufficient bundles and approved budgets.
5. **Resolve:** merge claims, preserve conflicts, and calculate readiness.
6. **Review:** inspect evidence and correct/reject proposals through the admin UI.
7. **Publish:** publish only records passing all mandatory dimensions.
8. **Monitor:** track source changes, expiry, deadlines, and stale evidence.

### Scale waves

| Wave | Target | Primary purpose | Review policy |
|---|---:|---|---|
| Golden | 10 | Validate varied source/programme patterns | Full manual evidence review |
| Flagship | 50 total | Cover the best-known programmes first | Full manual evidence review |
| Government | 150 total | Cover national and multilateral programmes | Full manual review; prioritize blockers |
| Breadth | 300 total | Expand strong university and specialist routes | Full publication review with sampled deep re-checks |
| Coverage | 500+ total | Complete major Pakistan-relevant coverage | Risk-based review plus mandatory readiness gate |

Move between waves only when the previous wave meets its quality and operating thresholds.

### Batch controls

- Start with batches of 10, then 25, 50, and at most 100 only after measured stability.
- Set per-batch candidate, model-call, token, and cost limits using golden-cohort measurements.
- Allow zero automatic provider retries initially; retry explicitly from saved objective state.
- Never pay twice for the same content hash, objective, prompt, schema, and model deployment.
- Quarantine candidates with ownership ambiguity, source conflicts, login/CAPTCHA barriers, or repeated schema failures.
- Stop the batch if unsupported facts appear, evidence alignment fails, cost exceeds its ceiling, or error rate exceeds the accepted threshold.
- Keep acquisition and extraction queues separate so free source preparation can continue without authorizing model spend.

### Exit gate

- At least 500 legitimate routes, or the approved comprehensive coverage total, are review-ready/published.
- Priority A coverage is complete.
- At least 95% of selected candidates either become review-ready or have a specific, actionable blocker.
- Every model call is represented in the durable ledger with usage and cost.
- Duplicate and conflict queues are controlled and do not grow faster than review can resolve them.

## 11. Milestone 5 — connect the catalogue to the product

Purpose: make the completed catalogue useful to students.

### React catalogue

- Display only approved records through public endpoints.
- Show funding components rather than only a “fully funded” label.
- Display deadline state, intake/cycle, eligible degree levels, required documents, application link, and last verification date.
- Show official citations without exposing admin-only diagnostics.
- Clearly label `rolling`, `varies by country`, `not yet announced`, `not applicable`, and `not stated`.

### Profile matching

- Match only normalized, evidence-backed eligibility facts.
- Include nationality, residence, age when applicable, degree level, academic requirements, field, work experience, language tests, and destination preferences.
- Explain why a student matches, may match, or does not match.
- Do not turn missing eligibility information into a positive match.

### AI assistant

- Retrieve answers from approved catalogue facts and their official citations.
- Identify the scholarship route and cycle in every answer.
- Abstain when the catalogue lacks current evidence.
- Never use private candidates or unresolved claims as student-facing truth.

### Deadline and document planning

- Generate reminders from supported deadline rules and cycle data.
- Build checklists from supported required-document claims.
- Preserve route-specific and programme-specific distinctions.
- Notify users when a source change makes a saved scholarship stale or requires re-review.

### Exit gate

- A student can discover, evaluate, match, save, and plan for an approved scholarship without encountering unsupported catalogue data.
- Assistant answers link back to the same evidence shown in the catalogue.
- Profile matching and deadline/document features use the canonical route rather than duplicated records.

## 12. Milestone 6 — production launch and catalogue freshness

Purpose: keep the catalogue trustworthy after launch.

### Required launch work

- Separate development, staging, and production secrets/configuration.
- Rotate the pilot service-principal credential and use an appropriate production identity strategy.
- Review public network access, local/key authentication, firewall/private-network requirements, diagnostic settings, and audit retention.
- Enforce preflight and capability-receipt validation on every worker start.
- Configure alerts for failed runs, cost, throttling, stale sources, missed deadlines, queue age, and worker health.
- Back up catalogue, source, evidence, review, and audit data and test restoration.
- Define rollback for bad extraction logic or an unexpected model-version change.
- Keep publication under explicit administrative control during the initial launch.

### Freshness cycle

- Recheck near-deadline and open-cycle scholarships most frequently.
- Recheck recurring government programmes before their normal application season.
- Use content hashes to avoid model calls when official content has not changed.
- When content changes, invalidate only affected claims/objectives and send the record back through review.
- Mark stale records visibly or remove them from recommendations until revalidated.
- Retain historical cycles without presenting their deadlines as current.

### Exit gate

- Production can process a bounded batch without manual database intervention.
- Cost, failure, review, publication, and freshness status are observable.
- A bad batch or model change can be stopped without losing completed work.
- Published information remains traceable to current official evidence.

## 13. Quality thresholds

These thresholds apply before declaring the catalogue goal achieved:

- Unsupported public facts: **0 tolerated**.
- Evidence citation correctness: **100% for published mandatory facts**.
- Mandatory readiness: **15/15 dimensions for every published route**.
- Schema-valid model responses: **at least 98%** after controlled retry/recovery.
- Duplicate identity: **0 unresolved duplicates among published records**.
- Unresolved conflicts: **0 for affected published fields**.
- Model usage ledger coverage: **100% of calls**.
- Source freshness: **100% of published records inside the configured freshness policy or visibly withheld/stale**.
- Priority A inventory coverage: **100% decided**, including documented exclusions.

Completeness does not mean inventing values. An official, evidence-backed semantic state can pass where the programme genuinely uses rolling, varying, not-applicable, or not-yet-announced rules.

## 14. Minimal implementation backlog in execution order

### P0 — required before the next scholarship call

- Restore safe local worker state.
- Preserve and clean the uncommitted Phase 0–7 work.
- Enforce preflight inside the worker.
- Enforce capability receipt at runtime.
- Fix call-budget versus objective-routing mismatch.
- Correct budget reservation to cover the full request.
- Validate all response terminal states consistently.
- Consolidate the DAAD source bundle.
- Fix lint failures in production capability code/tests.
- Run the one-route DAAD pilot.

### P1 — required before the first 50 records

- Complete and approve the ten-scholarship golden cohort.
- Create the authoritative inventory and Pakistan-eligibility classification.
- Add source-pattern fixtures from golden-cohort failures.
- Make probe/call evidence append-only.
- Add a batch scoreboard for inventory-to-publication progress and unit cost.
- Verify admin review can process records efficiently without database work.
- Add explicit model-version drift handling.

### P2 — required before the 500+ catalogue launch

- Run the 50, 150, 300, and 500+ waves through exit gates.
- Integrate approved data with catalogue, matching, assistant, and planning features.
- Establish production identity, networking, diagnostics, alerts, backup, and rollback.
- Establish source refresh scheduling and stale-record handling.
- Measure review throughput and prevent extraction from outrunning human review.

### Post-launch — intentionally deferred

Do not prioritize these until actual usage or measured bottlenecks justify them:

- a second ingestion or crawler architecture;
- autonomous paid web discovery;
- distributed workers beyond demonstrated throughput needs;
- advanced graph expansion unrelated to matching or deduplication;
- broad vector-search infrastructure before the approved catalogue is usable;
- extensive UI redesign beyond the review and student workflows;
- optimization work without measured latency, cost, or quality evidence.

## 15. Final acceptance statement

The project goal is achieved when:

1. the catalogue contains the major government, multilateral, and globally prominent scholarship routes currently relevant to Pakistani applicants;
2. at least 500 legitimate routes are live, unless comprehensive coverage is demonstrably smaller and the owner approves that result;
3. every published route passes the 15-dimension evidence-backed readiness gate;
4. students can use those records through the React catalogue, profile matcher, AI assistant, and deadline/document workflows;
5. the system can refresh changed official sources without repaying for unchanged content or silently publishing stale facts; and
6. routine catalogue growth no longer requires direct database intervention or new architecture work.

Until those conditions are satisfied, engineering work should be selected by one question: **does this task directly increase the number, quality, or usefulness of complete scholarships available to students?**
