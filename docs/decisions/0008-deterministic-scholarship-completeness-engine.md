# ADR 0008: Make scholarship completeness deterministic, scoped, and evidence-aware

- Status: Accepted for architecture; implementation is staged after the PR5 discovery foundation
- Date: 2026-08-19
- Applies to: canonical scholarship hubs, acquisition objectives, review readiness, freshness monitoring, search ranking, and later autonomous orchestration
- Related: ADR 0002–0007, `docs/scholarship-information-contract.md`, `docs/pr5-web-discovery-spec.md`

## Context

The platform's acquisition engine must know when a scholarship is sufficiently complete and trustworthy. A raw percentage is not safe enough.

Example:

```text
Identity     complete
Funding      complete
Eligibility  complete
Deadline     missing
Documents    complete
```

A naive weighted score might report `90% complete`. For a student deciding whether and when to apply, the missing deadline can be more important than several completed enrichment fields combined.

The live repository already has strong lower-level primitives:

- immutable source snapshots;
- field evidence tied to exact source text spans;
- evidence support and validator states;
- official-source verification status;
- source freshness selection;
- conflict/expired/archive source rejection;
- graph entities for cycles, tracks, institutions, programmes, scoped deadlines, funding, documents, steps, and relationships;
- an `Opportunity.publication_completeness` summary field introduced by the graph migration.

What is missing is a single deterministic policy that turns those lower-level facts into:

1. per-field/per-dimension health;
2. scholarship-level completeness state;
3. exact reason codes;
4. the next discovery objective(s);
5. an auditable explanation of why a record is or is not complete.

The policy must preserve an important distinction:

> Failure to find a fact is not proof that the fact is officially unknown.

An official page that is silent on stipend amount can mean the source is incomplete for that objective. The platform must not convert silence into a confident `unknown` merely to achieve completeness.

## Decision

### 1. Completeness is a policy result, not a stored human/AI opinion

Introduce a deterministic `ScholarshipCompletenessEngine`.

Conceptual interface:

```python
class ScholarshipCompletenessEngine(Protocol):
    def evaluate(
        self,
        scholarship_id: UUID,
        *,
        cycle_id: UUID | None,
        now: datetime,
    ) -> ScholarshipCompletenessAssessment: ...
```

Inputs are reviewed graph/evidence state only.

The engine must not use:

- applicant profile data;
- LLM confidence;
- search-result snippets;
- third-party scholarship descriptions;
- user engagement as truth evidence;
- generated prose;
- arbitrary operator-entered completion percentages.

`Opportunity.publication_completeness` becomes a materialized summary of the engine's latest reviewed/current assessment, not the source of truth for the calculation.

### 2. Use reason-coded dimension verdicts, not a global percentage

Each assessed dimension returns one of:

```text
VERIFIED_CURRENT
VERIFIED_ABSENT
AUTHORITATIVE_UNKNOWN
NOT_APPLICABLE
PARTIAL
MISSING
UNSUPPORTED
STALE
CONFLICTING
SCOPE_MISMATCH
BLOCKED_DEPENDENCY
UNRESOLVED_APPLICABILITY
```

Meaning:

#### `VERIFIED_CURRENT`

The required fact/collection is present, correctly scoped, and backed by adequate current official evidence.

#### `VERIFIED_ABSENT`

An authoritative official source explicitly establishes that the item is not required/not provided/not covered.

Examples:

```text
application fee: no fee required
travel allowance: not covered
IELTS: not required for this route
```

This is different from no information being found.

#### `AUTHORITATIVE_UNKNOWN`

Use narrowly. An authoritative source explicitly establishes uncertainty/variability/no fixed value, or an exhaustive reviewed source bundle is explicitly permitted by policy to establish that the information is not published.

Examples might include official wording such as:

```text
amount varies by institution
no fixed closing date; contact the mission
programme list will be announced later
```

A page simply omitting the field does **not** qualify.

#### `NOT_APPLICABLE`

The scholarship structure or official policy proves the dimension does not apply.

#### `PARTIAL`

Some valid information exists but the required collection/scope is not demonstrably complete.

#### `MISSING`

No usable fact/evidence currently exists for a required dimension.

#### `UNSUPPORTED`

A value exists in the graph but lacks adequate supporting current official field evidence.

#### `STALE`

The value/evidence was acceptable previously but fails the current freshness/cycle policy.

#### `CONFLICTING`

Current applicable official evidence disagrees in a way that cannot be deterministically scoped/reconciled.

#### `SCOPE_MISMATCH`

Evidence exists but at the wrong authority/scope level.

Example: an institution deadline cited as the global scholarship deadline.

#### `BLOCKED_DEPENDENCY`

A prerequisite identity/structure question is unresolved, so a downstream dimension cannot be safely evaluated.

#### `UNRESOLVED_APPLICABILITY`

The engine cannot yet determine whether the dimension should exist for this scholarship.

Example: it is unclear whether an umbrella scheme has a designated institution list.

### 3. Keep value state separate from evidence health

Do not overload `unknown` to mean every kind of problem.

For each fact/dimension, conceptually track:

```text
value_state
  confirmed_value
  confirmed_absent
  authoritative_unknown
  not_applicable
  no_value

evidence_state
  current_supported
  stale
  conflicting
  unsupported
  scope_mismatch
  blocked
```

The public presentation can simplify these, but the engine must preserve the difference internally.

Examples:

```text
stipend amount = NULL
reason = MISSING
```

is very different from:

```text
stipend amount = NULL
reason = AUTHORITATIVE_UNKNOWN
source says "amount varies by host institution"
```

### 4. Evaluate at explicit graph scope

Completeness scope follows:

```text
SCHOLARSHIP
  -> CYCLE
       -> TRACK
            -> INSTITUTION
                 -> PROGRAMME
```

An assessment carries explicit scope identifiers.

A more specific fact cannot satisfy a broader objective unless the domain policy explicitly permits aggregation.

Examples:

- Tsinghua's local deadline cannot satisfy CSC global deadline completeness;
- a provider-wide stipend can satisfy a track/institution child scope if no scoped override exists and the effective-value rules permit inheritance;
- one university's programme list cannot prove the umbrella scheme's complete programme universe.

### 5. Define core completeness dimensions

Initial canonical dimensions:

```text
IDENTITY_AND_AUTHORITY
INDEPENDENCE_AND_RELATIONSHIP
CURRENT_CYCLE_STATUS
APPLICATION_TIMING
FUNDING
ELIGIBILITY
APPLICATION_ROUTE
REQUIRED_DOCUMENTS
APPLICATION_STEPS
PARTICIPATING_INSTITUTIONS
ELIGIBLE_PROGRAMMES
LOCAL_EXCEPTIONS
SOURCE_FRESHNESS
```

Each dimension has:

```text
criticality tier
applicability policy
required field paths / collection rules
accepted authority classes
freshness policy
conflict policy
objective mapping
```

### 6. Tier 0 dimensions block canonical independent scholarship publication

Tier 0:

```text
IDENTITY_AND_AUTHORITY
INDEPENDENCE_AND_RELATIONSHIP
```

`IDENTITY_AND_AUTHORITY` requires, at minimum:

- canonical scholarship identity/name;
- provider/awarding authority;
- appropriate official owner/source relationship;
- adequate official identity evidence.

`INDEPENDENCE_AND_RELATIONSHIP` requires the PR3 relationship/independence gate for records counted as independent scholarships.

Any Tier 0 result other than:

```text
VERIFIED_CURRENT
NOT_APPLICABLE (only where policy explicitly permits)
```

prevents the record from being counted/published as a newly confirmed independent scholarship.

### 7. Tier 1 dimensions define `COMPLETE_CORE`

Tier 1:

```text
CURRENT_CYCLE_STATUS
APPLICATION_TIMING
FUNDING
ELIGIBILITY
APPLICATION_ROUTE
```

For a current/open/upcoming record, `COMPLETE_CORE` requires every applicable Tier 1 dimension to be one of:

```text
VERIFIED_CURRENT
VERIFIED_ABSENT
AUTHORITATIVE_UNKNOWN
NOT_APPLICABLE
```

`MISSING`, `UNSUPPORTED`, `STALE`, `CONFLICTING`, `SCOPE_MISMATCH`, `BLOCKED_DEPENDENCY`, or `UNRESOLVED_APPLICABILITY` blocks `COMPLETE_CORE`.

`PARTIAL` blocks `COMPLETE_CORE` when the missing portion can affect a student's decision.

Historical/archived cycles use a separate historical completeness policy and do not block the current canonical hub if correctly labelled.

### 8. Tier 2 workflow completeness does not automatically block safe publication

Tier 2:

```text
REQUIRED_DOCUMENTS
APPLICATION_STEPS
LOCAL_EXCEPTIONS
```

A record may be `PUBLISHABLE_WITH_GAPS` when Tier 0/critical Tier 1 safety is satisfied but non-critical Tier 2 information remains visibly missing.

However, a Tier 2 field promoted to a hard claim (for example, "these are all mandatory documents") requires the same evidence discipline as Tier 1.

The UI must not convert an incomplete document/step list into an exhaustive checklist without coverage proof.

### 9. Structural graph dimensions define `COMPLETE_GRAPH`

Structural dimensions:

```text
PARTICIPATING_INSTITUTIONS
ELIGIBLE_PROGRAMMES
LOCAL_EXCEPTIONS
```

`COMPLETE_GRAPH` requires:

1. `COMPLETE_CORE`;
2. applicability resolved for graph dimensions;
3. every applicable structural dimension either demonstrably complete or explicitly `NOT_APPLICABLE`;
4. no known structural inflation/duplicate relationship conflict.

A scholarship with no institution/programme structure can reach `COMPLETE_GRAPH` when official evidence/structure policy establishes those dimensions as `NOT_APPLICABLE`.

### 10. Collection completeness needs proof of exhaustiveness

For lists such as:

- participating institutions;
- eligible programmes;
- required documents;
- application routes;

presence of several valid rows is not proof that the collection is complete.

Define collection coverage states:

```text
EXHAUSTIVE_VERIFIED
PARTIAL_VERIFIED
UNKNOWN_COVERAGE
NOT_APPLICABLE
```

`EXHAUSTIVE_VERIFIED` requires one of the following policy-supported proofs:

- an official source explicitly presents the authoritative complete list;
- an official API/download/table is treated as exhaustive and captured in an immutable snapshot;
- multiple scoped official sources together are reviewed as an exhaustive source bundle;
- a deterministic structural rule proves all expected members have been covered.

The following do **not** prove exhaustiveness by themselves:

- crawler reached max depth/pages;
- search returned no more results;
- five universities were found;
- model says "this appears complete";
- source wording says "including"/"such as".

This is critical for honest `COMPLETE_GRAPH` status.

### 11. Use expected cardinality only when official evidence establishes it

If an official source says:

```text
20 participating institutions
```

and the graph has 18 verified institutions, the engine may report:

```text
PARTIAL
verified_count = 18
expected_count = 20
```

If no authoritative denominator exists, do not invent a completion percentage.

The UI/admin can show:

```text
18 verified institutions; total official count not established
```

rather than `90% complete`.

### 12. Freshness is fact/scope-aware, not only source-row-aware

The existing `EvidencePolicy` source freshness logic remains a primitive, but completeness must consider whether the evidence is appropriate for the **current cycle and field**.

Examples:

- a provider page verified yesterday but describing the 2025 cycle cannot satisfy a 2027 deadline objective;
- a long-lived provider identity page may remain adequate for identity longer than a deadline page;
- funding policy may have a different review interval from programme participation.

Introduce policy-level freshness classes, conceptually:

```text
IDENTITY_STABLE
CYCLE_CRITICAL
DEADLINE_CRITICAL
FUNDING_CRITICAL
ELIGIBILITY_CRITICAL
STRUCTURAL_LIST
WORKFLOW_GUIDANCE
```

Each class maps to:

- current-cycle requirement;
- max verification age when appropriate;
- source change monitoring priority.

Do not hardcode one freshness-days value for every field forever.

### 13. Current-cycle evidence outranks old-cycle evidence

For current/open/upcoming facts:

```text
current-cycle explicit evidence
    > undated current provider policy
    > previous-cycle evidence
```

Previous-cycle evidence may be displayed as historical context with a warning, but it does not silently satisfy current-cycle Tier 1 completeness unless an explicit policy proves the rule persists across cycles.

### 14. Conflicts are evaluated by authority and scope before becoming blockers

Two different values are not automatically a conflict.

Example:

```text
provider global deadline: 1 Dec
institution local deadline: 15 Nov
```

This is valid scoped data.

A real conflict occurs when two applicable sources of comparable/expected authority disagree **for the same fact and scope** and no deterministic version/currentness rule resolves them.

Conflict resolution order:

1. verify scope is genuinely identical;
2. verify source ownership/authority class;
3. verify cycle/version/currentness;
4. apply explicit deterministic precedence rule if one exists;
5. otherwise `CONFLICTING` and create a conflict-resolution objective/review exception.

Never use model preference/search rank to choose the winning fact.

### 15. Completeness policy maps directly to discovery objectives

Every non-satisfied verdict maps to a reason-coded objective or terminal exception.

Examples:

```text
IDENTITY_AND_AUTHORITY = MISSING
  -> RESOLVE_PROVIDER_IDENTITY / RESOLVE_CANONICAL_SOURCE

APPLICATION_TIMING = STALE
  -> FRESHNESS_REFRESH scoped to application deadline

FUNDING = UNSUPPORTED
  -> FUNDING_COVERAGE

PARTICIPATING_INSTITUTIONS = PARTIAL
  -> PARTICIPATING_INSTITUTIONS expansion

ELIGIBLE_PROGRAMMES = UNRESOLVED_APPLICABILITY
  -> structural applicability review/discovery

APPLICATION_TIMING = CONFLICTING
  -> CONFLICT_RESOLUTION_SOURCE
```

This closes the loop:

```text
graph/evidence state
  -> completeness assessment
  -> exact reason
  -> objective
  -> discovery/acquisition
  -> evidence update
  -> reassessment
```

### 16. Do not create infinite acquisition loops

A completeness gap does not mean "search forever".

The objective engine from ADR 0005 remains responsible for budgets/retries/terminal outcomes.

After bounded acquisition, a dimension may remain:

```text
MISSING
BLOCKED_DEPENDENCY
CONFLICTING
UNRESOLVED_APPLICABILITY
```

with an exception status such as:

```text
NO_OFFICIAL_SOURCE_FOUND
BLOCKED_SOURCE
CONFLICT_REQUIRES_REVIEW
BUDGET_EXHAUSTED
```

The completeness engine reports the unresolved state; it does not repeatedly reopen the same objective without retry/backoff/freshness policy justification.

### 17. Define public scholarship completeness states precisely

Canonical summary states:

```text
INCOMPLETE
PUBLISHABLE_WITH_GAPS
COMPLETE_CORE
COMPLETE_GRAPH
```

#### `INCOMPLETE`

One or more Tier 0/Tier 1 safety requirements is missing, unsupported, stale beyond allowed policy, conflicting, scope-mismatched, or blocked.

A current record in this state should not be represented as a complete trusted answer.

#### `PUBLISHABLE_WITH_GAPS`

Tier 0 identity is safe and the minimum publication policy is met, but one or more visible non-critical gaps remains. Unknown/missing sections are clearly labelled.

This state is appropriate only when the remaining gaps do not create false confidence about core decision-making.

#### `COMPLETE_CORE`

All applicable Tier 0/Tier 1 dimensions meet accepted verdict states with current/correctly scoped evidence.

Tier 2/structural gaps can still exist and are shown honestly.

#### `COMPLETE_GRAPH`

`COMPLETE_CORE` plus all applicable structural graph dimensions are exhaustively verified or explicitly not applicable, with no unresolved structural inflation/conflict.

### 18. `publication_completeness` is a materialized compatibility field

The graph migration already added:

```text
opportunities.publication_completeness
```

Do not let arbitrary services write this field independently.

When the completeness engine is implemented:

- only the engine/materialization service writes it;
- accepted string values are the four canonical states;
- a future migration may add a check constraint after existing data is audited/backfilled;
- public/search consumers may use it as an indexed summary;
- detailed explanation always comes from an assessment result, not the string alone.

PR5 architecture does not retroactively change legacy publication behavior before the engine is proven.

### 19. Persist versioned assessment snapshots before autonomous orchestration

For reproducibility and operations, introduce later (PR6/PR8 boundary) a small durable assessment record:

```text
scholarship_completeness_assessments
```

Recommended fields:

```text
id UUID PK
scholarship_id UUID NOT NULL
cycle_id UUID NULL
policy_version varchar(100) NOT NULL
input_fingerprint varchar(64) NOT NULL
overall_status varchar(32) NOT NULL
core_status varchar(32) NOT NULL
graph_status varchar(32) NOT NULL
dimension_results JSON NOT NULL
blocking_reason_codes JSON NOT NULL
suggested_objectives JSON NOT NULL
assessed_at timestamptz NOT NULL
```

Unique/reuse boundary:

```text
UNIQUE(scholarship_id, cycle_id, policy_version, input_fingerprint)
```

The JSON payloads use bounded typed schemas, not ORM dumps.

Why persist snapshots:

- explain why a scholarship was marked complete/incomplete at a point in time;
- prove which gap triggered an autonomous discovery run;
- compare policy versions;
- monitor catalogue quality trends;
- avoid recomputing unchanged state repeatedly.

The snapshot is derived/audit state, not primary scholarship truth.

### 20. Input fingerprint must represent truth inputs, not timestamps alone

The completeness input fingerprint should include stable/versioned identifiers for the applicable inputs, such as:

- scholarship/cycle graph row versions;
- relevant track/institution/programme relationship versions;
- applicable source snapshot IDs/content hashes;
- field evidence IDs/validator states;
- source verification/freshness-relevant values;
- relationship/independence decision versions;
- policy version.

Do not include irrelevant applicant/user data.

If truth inputs do not change, reuse the assessment.

### 21. Search ranking uses completeness carefully

Search should prefer:

```text
current + COMPLETE_CORE/COMPLETE_GRAPH
```

over stale/incomplete alternatives when identity relevance is otherwise comparable.

But completeness never outranks exact canonical identity.

Example:

An exact search for a real but incomplete scholarship should return that canonical scholarship with an explicit update-pending/incomplete label rather than hiding it behind a different but more complete scholarship.

### 22. Public UI displays trust state without exposing internal complexity

Recommended user-facing states:

```text
Verified current
Verified, some details unavailable
Update pending
Conflict under review
Not applicable
```

Internally the full reason-coded verdict remains available for acquisition/review/admin diagnostics.

The UI must distinguish:

```text
No application fee
```

from:

```text
Application fee not confirmed
```

and:

```text
No institution list applies
```

from:

```text
Institution list not yet verified
```

### 23. The AI assistant may consume completeness state but cannot override it

The downstream assistant may say:

```text
"The current official sources do not confirm the travel allowance."
```

when the dimension is missing/authoritative-unknown.

It may not infer a value and present the scholarship as complete.

The assistant receives:

- canonical structured facts;
- scoped field evidence;
- completeness verdict/reason;
- explicit unknown/conflict indicators.

Completeness remains deterministic system truth.

### 24. Initial policy version

Use a versioned policy identifier, for example:

```text
scholarship-completeness.v1
```

Any change that alters dimension applicability, accepted verdicts, criticality, freshness class, or roll-up rules creates a new policy version.

Do not silently change old assessment semantics.

### 25. Flagship validation must prove hard structures, not easy cards

Before autonomous catalogue scaling, completeness evaluation must be exercised on structurally different flagship cases:

#### CSC / Chinese Government Scholarship

Must distinguish:

- one umbrella scholarship;
- routes/tracks;
- participating universities;
- local requirements/deadlines;
- institution-owned separate awards;
- partial vs exhaustive university/programme coverage.

#### MEXT

Must distinguish embassy vs university recommendation routes and country-mission deadlines from global provider facts.

#### Chevening

Must distinguish canonical scholarship from country guidance/course/university surfaces.

#### Erasmus Mundus

Must handle programme-level scholarship structures without multiplying one scheme/programme relationship incorrectly.

#### Independent university award

Must prove that an institution-owned named award can reach `COMPLETE_CORE` without requiring an umbrella institution graph when that structure is not applicable.

### 26. Completeness Gold Set

Create a frozen evaluation set separate from discovery/extraction Gold sets.

Recommended initial set: at least 30 scholarship-state fixtures, including:

- fully complete simple award;
- current deadline missing;
- old-cycle deadline only;
- funding value without evidence;
- conflicting same-scope deadlines;
- valid global/local deadline pair;
- explicit no application fee;
- application fee absent from source;
- exhaustive institution list;
- partial institution list with no denominator;
- official expected count with missing members;
- programme dimension not applicable;
- unresolved structural applicability;
- registered route set complete;
- local-source evidence incorrectly used globally;
- stale provider identity vs fresh cycle fact;
- independence unresolved;
- duplicate/same-scheme child;
- authoritative "varies by institution" unknown;
- source silent on stipend amount;
- blocked/login source;
- previous reviewed truth while refresh pending.

Expected output includes:

```text
overall status
each dimension verdict
blocking reasons
suggested objective kinds
```

### 27. Hard acceptance invariants

Implementation must prove:

1. no raw percentage can mark a scholarship complete;
2. missing deadline blocks current `COMPLETE_CORE`;
3. official source silence does not become `AUTHORITATIVE_UNKNOWN` automatically;
4. explicit "not required/not covered" becomes `VERIFIED_ABSENT` when properly evidenced;
5. scoped local deadline does not conflict with a different global deadline merely because values differ;
6. same-scope unresolved conflict blocks the affected critical dimension;
7. stale previous-cycle evidence does not satisfy current-cycle deadline completeness;
8. unsupported non-null value is not considered complete;
9. partial institution/programme discovery cannot become exhaustive from crawler/search exhaustion;
10. no official denominator means no invented list-completion percentage;
11. `NOT_APPLICABLE` requires structural/evidence policy justification;
12. Tier 0 failure blocks canonical independent scholarship completion;
13. Tier 1 failure blocks `COMPLETE_CORE`;
14. applicable structural partial coverage blocks `COMPLETE_GRAPH` but may allow `COMPLETE_CORE`;
15. suggested discovery objectives correspond exactly to unsatisfied reason codes/scopes;
16. unchanged truth inputs reuse the same policy assessment;
17. AI output cannot mutate completeness state;
18. applicant data never participates in completeness evaluation.

## Implementation sequencing

This ADR defines the target contract now but does not force the entire engine into PR5.

Recommended sequence:

```text
PR5
  discovery ledger / objective / owner-domain / safe promotion foundation

PR6
  provenance-safe multi-source evidence bundles
  + effective scoped fact resolution

PR6/PR8 bridge
  ScholarshipCompletenessEngine v1
  + durable assessment snapshot
  + objective derivation from completeness gaps

PR8
  autonomous acquisition orchestrator consumes those objectives

PR9
  flagship -> 30 -> 100 -> 500 scale proof
```

Reason: accurate completeness depends on PR6's multi-source provenance. Implementing an apparently sophisticated completeness score before field-level multi-source evidence resolution would create false precision.

PR5 may still store explicit objective reason/scope snapshots so no later redesign is required.

## Consequences

### Positive

- The acquisition engine knows what "done" means without trusting an AI score.
- Missing high-risk facts cannot be hidden by many completed low-risk fields.
- Official silence cannot be misrepresented as confirmed unknown.
- Institution/programme list completeness becomes honest and measurable.
- Freshness/conflicts/scope errors directly create targeted acquisition objectives.
- Public scholarship pages can expose gaps transparently without losing trust.
- Later autonomous discovery has deterministic stop/continue decisions.

### Cost

- Completeness becomes a real domain subsystem rather than one string/percentage.
- Exhaustive list verification is harder than counting crawled pages.
- Some scholarships will remain `PUBLISHABLE_WITH_GAPS` or `INCOMPLETE` longer, because the platform refuses false certainty.
- Full implementation should wait until provenance-safe multi-source evidence exists.

These costs are accepted because trustworthy incompleteness is better than confidently wrong completeness.
