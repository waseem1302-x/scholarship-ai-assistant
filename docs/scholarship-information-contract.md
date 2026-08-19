# Canonical Scholarship Information Contract

- Status: Architecture contract for Scholarship Intelligence Graph delivery
- Date: 2026-08-19
- Scope: discovery, canonical scholarship hubs, institution funding pages, evidence, search, and downstream AI entry points

## 1. Product outcome

Scholarship discovery is the platform's primary acquisition surface. A user who lands on the product through a scholarship search must be able to answer the important scholarship questions without reconstructing the answer from blogs, PDFs, university pages, government portals, and conflicting local instructions.

The scholarship layer therefore has two jobs:

1. **Acquire the right user** by resolving scholarship, provider, country, university, programme, and alias searches to the right canonical destination.
2. **Earn enough trust to unlock the rest of the platform** by presenting complete, current, scoped, official-source-backed information in a clean structure that naturally leads into eligibility, planning, document, application, reminder, and assistant workflows.

The product is not successful when it merely finds many URLs or publishes many scholarship cards. It is successful when a user can understand what the scholarship is, whether it is relevant, what it funds, what rules apply to them, how and when to apply, and which official source supports every decision-critical statement.

## 2. Non-negotiable truth model

```text
Official provider / government / resolved institution source
                      ↓
Immutable source snapshot
                      ↓
Field-level evidence + explicit scope
                      ↓
Deterministic validation
                      ↓
Reviewed canonical Scholarship Intelligence Graph
                      ↓
Search / eligibility / application workflows / AI explanation
```

Rules:

- Search results are discovery leads, never evidence.
- One scholarship identity is counted once unless independence is proven.
- Unknown is a valid user-facing value; guessed facts are not.
- A fact is never detached from its scope.
- Institution or programme rules cannot silently override global scholarship rules.
- Current-cycle claims require current evidence.
- AI may explain published facts but may not silently manufacture missing scholarship facts or publish them.

## 3. The user-facing information hierarchy

The page must be deep without feeling dense. Information is presented in progressive layers.

### Layer A — decision summary (visible immediately)

The first screen answers:

- canonical scholarship name and important alias/acronym;
- provider / awarding authority;
- destination country or region;
- current cycle/status: open, upcoming, closed, rolling, or official update pending;
- next relevant deadline and whose deadline it is;
- eligible study levels;
- funding classification;
- a concise verified funding summary;
- high-level nationality/target group eligibility;
- last verified date and freshness state;
- completeness state;
- primary actions: Check eligibility, How to apply, Save, Compare, Track deadline.

The summary must not flatten route/institution-specific information into global claims.

### Layer B — complete scholarship answer

The canonical hub then contains these ordered sections:

1. **Overview**
   - what the award is;
   - awarding/funding authority;
   - destination and intended study type;
   - canonical aliases/translations;
   - current cycle and status.

2. **What it funds**
   - tuition;
   - stipend/living allowance;
   - accommodation;
   - travel;
   - health/insurance;
   - fees/application fees;
   - other official benefits;
   - explicit `confirmed`, `partial`, `not covered`, and `unknown` states;
   - amount/currency/frequency only when the source explicitly supports them.

3. **Who can apply**
   - nationality/residence;
   - target degree/study level;
   - field/programme restrictions;
   - academic thresholds;
   - language requirements;
   - standardized tests;
   - work experience;
   - intake/current-education restrictions;
   - other structured official conditions;
   - clear separation between mandatory, conditional, and unknown requirements.

4. **Application routes / tracks**
   - route name and code;
   - who runs the route;
   - application method;
   - route-specific requirements;
   - route-specific deadlines;
   - route-specific application URL;
   - decision authority where known;
   - side-by-side comparison when there are multiple routes.

5. **Participating institutions**
   - verified participation for the relevant cycle/track;
   - institution-specific status;
   - local application URL;
   - local deadline or extra requirement indicators;
   - filters/search rather than loading all institutions at once.

6. **Eligible programmes**
   - institution;
   - programme;
   - degree level/field;
   - track;
   - programme-level eligibility/funding state;
   - official programme/application URL;
   - pagination/filtering for large schemes.

7. **Deadlines**
   - global/provider deadline;
   - route deadline;
   - institution deadline;
   - programme deadline where applicable;
   - timezone and scope label;
   - no single "deadline" field when more than one deadline legitimately applies.

8. **Required documents**
   - document name;
   - whether required/conditional;
   - route/institution/programme scope;
   - supporting notes;
   - ordered checklist display.

9. **How to apply**
   - ordered application steps;
   - actor/portal/URL where known;
   - route/institution scope;
   - prerequisite sequencing;
   - no inferred step that lacks official support.

10. **Institution-specific exceptions**
    - local deadlines;
    - local documents;
    - local academic/language requirements;
    - local nomination/application sequence;
    - explicitly labelled as local, never presented as universal scholarship rules.

11. **Related funding**
    - same-scheme tracks are not extra scholarships;
    - participating-institution pages are not extra scholarships;
    - independently proven university/government/foundation awards are shown as separate related scholarships;
    - unresolved related awards remain review-only.

12. **Official sources and evidence**
    - official source title/domain;
    - ownership/scope label;
    - last fetched/verified information;
    - field citations for decision-critical claims;
    - conflicts shown rather than silently reconciled.

13. **Known unknowns**
    - important facts the current official sources do not state;
    - stale/current-cycle pending fields;
    - unresolved conflicts;
    - clear distinction between "not required/not covered" and "not confirmed".

### Layer C — platform activation

Once the user trusts the scholarship record, the page becomes an entry point into the platform's higher-value capabilities:

- personalized eligibility check;
- fit/readiness explanation;
- saved scholarship and comparison;
- deadline reminders;
- application command centre;
- required-document checklist and Document Lab;
- citation-first AI assistant restricted to the published scholarship graph and evidence;
- next-action playbook.

These capabilities should never compensate for an incomplete or unreliable scholarship record. They sit on top of it.

## 4. Fact scope is first-class

Every structured fact that can vary must resolve against this scope hierarchy:

```text
SCHOLARSHIP
  └── CYCLE
       └── TRACK / ROUTE
            └── INSTITUTION
                 └── PROGRAMME
```

A more specific fact may supplement or override a broader fact only when the domain rule allows it and the UI labels the scope.

Examples:

- global eligibility: "Bachelor's degree required";
- route rule: "Embassy route requires nomination";
- institution rule: "Tsinghua deadline is 15 December";
- programme rule: "Programme X requires IELTS 7.0".

The effective-value resolver must return both the value and the source scope. The public API must preserve that scope rather than flattening the result.

## 5. Information criticality and evidence requirements

### Tier 0 — identity-critical

Must be supported before a record can be treated as a canonical independent scholarship:

- official scholarship/scheme identity;
- provider/awarding authority;
- independence status;
- canonical official source relationship.

Missing/conflicting Tier 0 information blocks publication as a new independent scholarship.

### Tier 1 — decision-critical

Examples:

- current cycle/status;
- application deadline/opening date;
- funding/tuition/stipend claims;
- nationality/residence eligibility;
- degree/academic/language/test requirements;
- application route/method;
- required documents when represented as mandatory;
- institution/programme-specific deadline or requirement.

Every non-null Tier 1 value requires exact current official evidence and the correct scope. Conflict blocks review-ready status until resolved or explicitly represented as a conflict.

### Tier 2 — workflow-critical

Examples:

- ordered application steps;
- route comparison;
- application URLs;
- institution participation;
- programme participation;
- reminder dates;
- document notes.

These require official support but a non-critical gap can be shown as unknown if core safety remains intact.

### Tier 3 — enrichment

Examples:

- short explanatory summaries;
- aliases/translations;
- navigation hints;
- non-decision-critical context.

Generated explanatory copy must remain downstream of verified structured facts and never introduce new hard claims.

## 6. Completeness contract

Completeness is deterministic, not an AI confidence score.

### `INCOMPLETE`

Any required Tier 0 field is missing/conflicting, or a current decision-critical claim lacks appropriate evidence/scope. Not publishable as a current trusted scholarship record.

### `PUBLISHABLE_WITH_GAPS`

Canonical identity and safe core facts are verified. Some non-critical Tier 2/3 information is unknown and visibly labelled. No unsupported confident claim is present.

### `COMPLETE_CORE`

At minimum, all relevant core areas are verified or explicitly confirmed as unknown where the source truly does not state them:

- identity/provider;
- current cycle/status;
- funding;
- eligibility;
- deadline/application timing;
- application route/method;
- required documents/application steps where applicable;
- official evidence and freshness.

### `COMPLETE_GRAPH`

`COMPLETE_CORE` plus sufficiently verified coverage of the scholarship's real structure:

- tracks/routes;
- participating institutions;
- eligible programmes where applicable;
- scoped local exceptions;
- related independently proven awards;
- no known structural inflation.

A scholarship that inherently has no participating-institution or programme graph can still reach `COMPLETE_GRAPH` when those dimensions are explicitly not applicable.

## 7. Unknown, absent, and not-applicable semantics

The user experience must distinguish at least four states:

- `confirmed(value)` — official evidence supports the value;
- `confirmed_absent` — official evidence explicitly states it is not required/not covered/not offered;
- `unknown` — current official evidence does not establish the answer;
- `not_applicable` — the field/dimension does not apply to this scholarship or scope.

Do not map `unknown` to false, zero, "No", or an empty string.

## 8. Freshness contract

A scholarship page displays freshness as part of trust.

- show `last_verified_at` for the canonical hub;
- track source-level fetch/verification dates;
- current-cycle Tier 1 facts should have current-cycle evidence;
- unchanged source hashes update freshness without paying for unnecessary re-extraction;
- material deadline/funding/eligibility/route changes return affected facts to review;
- stale/incomplete records are demoted in search and labelled;
- previous reviewed truth may remain visible with a stale/pending-update warning when policy permits, rather than being silently replaced by unreviewed extraction.

## 9. Search and landing contract

### Search resolution

Ranking priority:

1. exact canonical scholarship name;
2. exact alias/acronym/translation;
3. exact institution;
4. prefix/fuzzy scholarship match;
5. provider/programme/country relevance;
6. stale/incomplete records demoted and labelled.

A query such as `Tsinghua scholarship` may resolve to an institution funding page that groups:

- national/umbrella schemes available at Tsinghua;
- Tsinghua-owned independent scholarships;
- provincial/state awards;
- faculty/research funding;
- programme-specific funding;
- local deadlines/requirements.

It must not manufacture a canonical `Tsinghua Scholarship` merely to satisfy the query.

### Indexable landing pages

Primary indexable surfaces are:

- canonical independent scholarship hubs;
- resolved institution funding pages;
- selected stable country/provider discovery surfaces only when backed by reviewed graph data.

Alias URLs redirect to the canonical hub. Filter combinations and raw discovery results are not independently indexable truth pages.

Zero-result queries are logged and clustered into the discovery backlog. They must not trigger a live unreviewed Web Search answer on a canonical truth page.

## 10. Discovery-to-information feedback loop

PR5 discovery quality is measured not only by whether it finds an official URL, but by whether the acquired official source helps close a real information gap.

The acquisition planner should eventually prioritize missing dimensions such as:

- identity/provider evidence;
- current cycle/deadline;
- funding;
- eligibility;
- application route;
- participating institutions/programmes;
- documents/steps;
- unresolved scope conflicts.

This creates a goal-directed catalogue:

```text
Search demand / known scholarship
          ↓
Discovery
          ↓
Official source acquisition
          ↓
Completeness evaluation
          ↓
Missing information dimensions
          ↓
Targeted official-source expansion
          ↓
Re-evaluate completeness
```

The system should not keep crawling merely because more pages exist. It should stop when the information objective is met, hard budgets are reached, or only unresolved/blocked sources remain.

## 11. Representation gap analysis

The current graph already directly represents:

- canonical scholarships and aliases;
- cycles/status;
- tracks/routes;
- institutions and participation;
- programmes;
- scoped eligibility rules;
- scoped deadlines;
- scoped funding components;
- required documents;
- ordered application steps;
- source ownership/officiality;
- immutable source snapshots;
- field-level evidence;
- related-scholarship classification.

Before declaring the catalogue information model complete, later schema work must explicitly decide how to represent these common dimensions if official sources provide them:

- award/support duration or maximum funded period;
- number/quota of awards when officially stated;
- selection/interview/nomination stages distinct from application steps;
- post-award obligations, return-home/service/bond conditions;
- official contact/help channel scoped to provider/track/institution;
- age limits and other eligibility types not covered by the present rule enum;
- frequency/unit semantics for non-monthly funding amounts;
- application/nomination fees that vary by route/institution;
- renewal/continuation conditions for multi-year support.

These are **not PR5 discovery blockers**. They are documented model gaps so acquisition does not silently dump them into generic notes or invent structures. They should be handled in a later information-model enrichment PR after real flagship evidence demonstrates which fields deserve first-class schema.

## 12. Acceptance cases

### CSC / Tsinghua

The platform must show one canonical Chinese Government Scholarship identity, route/category structure, participating universities, and Tsinghua-specific deadline/requirements without creating extra CSC scholarships. A separately named Tsinghua-owned award becomes a separate scholarship only after independence evidence passes.

### MEXT

Embassy and university-recommendation routes are tracks of one MEXT scholarship unless an official independent award is proven. Route-specific requirements and country procedures remain scoped.

### Chevening

Country guidance and eligible university/course information enrich one canonical scholarship instead of creating country/course variants as scholarships.

### Independent university award

A university-owned named award with its own authority, application path, decision, and current official evidence may become a separate canonical scholarship.

### Incomplete official source

If the official page names the award but does not state stipend amount or deadline, the public page shows those fields as unknown/pending official update; search snippets/blogs do not fill them.

## 13. Success metrics

Do not optimize catalogue success around raw page or URL count.

Track:

- confirmed-independent scholarship count;
- `COMPLETE_CORE` rate;
- `COMPLETE_GRAPH` rate where graph dimensions apply;
- decision-critical evidence coverage;
- stale Tier 1 fact rate;
- unresolved conflict rate;
- duplicate/inflation incident rate;
- search zero-result rate;
- search-to-scholarship-hub success rate;
- search-to-eligibility-check / save / application-plan activation;
- cost per promoted official lead;
- cost per `COMPLETE_CORE` scholarship;
- human exception minutes per scholarship;
- freshness SLA/queue lag.

The eventual acquisition system is successful when it improves these quality and user-journey metrics while reducing routine operator work.

## 14. Release principle

The first scholarship experience must be good enough that a student can reasonably prefer the platform over searching several third-party scholarship pages and manually reconciling official sources.

That requires **complete structure without false certainty**:

- clean enough to scan;
- deep enough to make a decision;
- scoped enough not to mix rules;
- current enough to trust;
- cited enough to verify;
- connected enough to move naturally into the platform's AI-powered eligibility, planning, document, and application capabilities.
