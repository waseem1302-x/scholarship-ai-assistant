# ADR 0009: Resolve evidence by field, scope, authority, and version before declaring conflict

- Status: Accepted for architecture; primary implementation belongs to PR6
- Date: 2026-08-19
- Applies to: multi-source evidence bundles, scoped fact resolution, conflict detection, completeness, review queues, and downstream AI answers
- Related: ADR 0002–0008, `docs/scholarship-information-contract.md`, `docs/pr5-web-discovery-spec.md`

## Context

The Scholarship Intelligence Graph already has strong primitives:

- immutable `SourceSnapshot` rows;
- `FieldEvidence` anchored to exact snapshot spans;
- source owner type/ID and officiality status;
- source verification/freshness state;
- scoped deadlines, funding components, eligibility rules, required documents, and application steps;
- scholarship -> cycle -> track -> institution -> programme structure;
- PR3 relationship/independence decisions that fail closed and require review.

However, the current ingestion path is still fundamentally single-root-source. `CatalogueExtractionOutput.conflicts` is a list of strings, candidate conflicts are stored as JSON, and a source can be marked `VerificationStatus.CONFLICTING_INFORMATION` as a whole.

That is insufficient for multi-source scholarship intelligence.

Consider:

```text
Provider page:
  global application deadline = 1 June

Embassy Malaysia page:
  Malaysia embassy nomination deadline = 15 May

Tsinghua page:
  university application deadline = 30 April
```

These values differ but are not necessarily contradictory. They can all be correct because their scopes and authorities differ.

Conversely:

```text
Provider page A, current cycle:
  monthly stipend = CNY 3,000

Provider page B, same authority and same current cycle:
  monthly stipend = CNY 3,500
```

is a genuine same-scope conflict unless deterministic version/supersession evidence resolves it.

The platform therefore needs a layer between extraction and canonical graph mutation that answers:

1. What exactly is the claim?
2. At what graph scope does it apply?
3. Which official owner/authority made it?
4. Which immutable snapshot and excerpt support it?
5. Is another claim actually contradictory, or merely broader/narrower/different-route?
6. Is one claim an old version of another?
7. Which value, if any, may be used as the effective fact without human judgment?

## Decision

### 1. Never concatenate multiple official pages into one synthetic source

PR6 must not build one giant text blob from multiple pages and ask extraction to return one answer.

That would destroy provenance and make it impossible to know which source supports which field.

Instead:

```text
Source A -> immutable snapshot -> field claims
Source B -> immutable snapshot -> field claims
Source C -> immutable snapshot -> field claims
                                   |
                                   v
                         deterministic resolver
                                   |
             +---------------------+--------------------+
             |                     |                    |
         corroborated        scope-specific        conflict/review
             |                     |                    |
             +---------------------+--------------------+
                                   |
                            canonical graph proposal
```

Every claim retains its original source snapshot and exact evidence span.

### 2. Add a durable pre-graph claim layer

PR6 should introduce a normalized staging representation rather than relying only on one opaque `proposed_payload` JSON.

Recommended entities:

```text
CatalogueEvidenceBundle
CatalogueFieldClaim
CatalogueConflictSet
```

The exact table prefix may follow repository conventions, but their semantics are required.

#### `CatalogueEvidenceBundle`

Represents the bounded set of official snapshots evaluated together for one candidate/opportunity acquisition objective.

Recommended fields:

```text
id UUID PK
candidate_id UUID NULL
opportunity_id UUID NULL
objective_kind varchar(64) NOT NULL
objective_scope JSON NOT NULL
resolver_policy_version varchar(100) NOT NULL
status varchar(32) NOT NULL
input_fingerprint varchar(64) NOT NULL
source_snapshot_ids JSON NOT NULL
created_at timestamptz NOT NULL
completed_at timestamptz NULL
```

Rules:

- exactly one acquisition target contract is active according to lifecycle policy;
- snapshots are immutable IDs, deduplicated and bounded;
- bundle membership never implies all sources have equal authority;
- unchanged fingerprint/policy may reuse a prior resolved bundle.

#### `CatalogueFieldClaim`

One row means:

> This source snapshot explicitly/partially/contradictorily supports this normalized value for this exact field and scope.

Recommended fields:

```text
id UUID PK
bundle_id UUID NOT NULL
source_snapshot_id UUID NOT NULL
field_path varchar(255) NOT NULL
scholarship_id UUID NULL
cycle_id UUID NULL
track_id UUID NULL
institution_id UUID NULL
programme_id UUID NULL
collection_key varchar(255) NULL
value_json JSON NULL
value_hash varchar(64) NULL
value_state varchar(32) NOT NULL
evidence_support_type varchar(32) NOT NULL
validator_status varchar(32) NOT NULL
excerpt text NOT NULL
excerpt_start int NOT NULL
excerpt_end int NOT NULL
source_authority_class varchar(32) NOT NULL
source_owner_type varchar(32) NOT NULL
source_owner_id UUID NULL
claim_status varchar(32) NOT NULL
created_at timestamptz NOT NULL
```

The claim is staging/proposal truth only. It does not mutate the public graph by itself.

### 3. Claim identity includes scope and collection identity

Two values are comparable for conflict only when they refer to the same semantic claim key.

Conceptual claim key:

```text
(
  scholarship identity,
  cycle,
  track,
  institution,
  programme,
  field_path,
  collection_key
)
```

Examples of `collection_key`:

```text
funding component -> tuition / stipend / travel / insurance
scoped deadline   -> application / nomination / institution / programme
required document -> normalized document_key
application step  -> step_code or reviewed semantic step identity
eligibility rule  -> rule_type + operator/unit/subject identity
```

A global deadline and a Tsinghua deadline therefore have different claim keys because institution scope differs.

A scholarship stipend amount and accommodation allowance have different claim keys because component identity differs.

### 4. Scope comparison happens before value comparison

The resolver must never compare values first.

Order:

```text
same scholarship identity?
  -> same cycle applicability?
      -> same track?
          -> same institution?
              -> same programme?
                  -> same field/collection key?
                      -> compare authority/version/value
```

If scopes differ legitimately, the claims coexist.

They may participate in inheritance/effective-value resolution for a more specific consumer scope, but they are not automatically conflicts.

### 5. Use exact-scope facts before inherited broader facts

For a requested effective scope:

```text
scholarship
  -> cycle
      -> track
          -> institution
              -> programme
```

resolve from most specific applicable scope to broader ancestors, subject to field policy.

Example:

```text
provider global language requirement = IELTS 6.5
programme-specific requirement       = IELTS 7.0
```

For that programme, `IELTS 7.0` is the effective local requirement if the programme/institution authority is accepted for that field.

The broader `IELTS 6.5` remains valid for scopes where no approved more-specific override applies.

Specificity does not itself prove authority. Both scope and authority class must be accepted.

### 6. Define field-specific authority policy; do not use one universal source rank

ADR 0007 introduced authority relationships such as:

```text
canonical_owner
co_owner
delegated_official
application_portal
country_mission
supporting_institution
```

PR6 adds a versioned `FieldAuthorityPolicy` that declares which authority classes can establish which field categories at which scope.

Initial examples:

#### Scholarship identity / awarding authority

Preferred/accepted:

```text
canonical_owner
co_owner (when reviewed relationship proves shared ownership)
```

A supporting institution cannot redefine the umbrella scholarship identity.

#### Global funding

Preferred/accepted:

```text
canonical_owner
co_owner
```

Institution/mission sources may support local supplements or institution-owned awards, but cannot silently change global provider funding.

#### Global application timing

Preferred/accepted:

```text
canonical_owner
co_owner
delegated_official when delegation covers application timing
```

#### Country/embassy route timing

Accepted:

```text
country_mission
delegated_official
canonical_owner when it explicitly publishes that local route
```

#### Institution/programme deadlines and requirements

Accepted at matching scope:

```text
supporting_institution
canonical_owner if it explicitly publishes the local rule
co_owner where applicable
```

#### Application URL / portal workflow

Accepted:

```text
application_portal
delegated_official
canonical_owner
```

but application-portal authority does not automatically extend to funding or eligibility prose.

Policy changes are versioned; no hidden ranking change.

### 7. Source officiality is necessary but not sufficient

A claim may enter trusted resolution only when all required checks pass:

- source is active;
- source officiality is `OFFICIAL` or accepted `SUPPORTING_OFFICIAL` for the field scope;
- source verification/freshness policy is adequate;
- snapshot is immutable and valid;
- excerpt matches snapshot text;
- evidence validator passes;
- source authority class is accepted for this field/scope;
- cycle/currentness applicability is established.

A row existing in `scoped_deadlines`, `funding_components`, or another graph table is not itself proof that the value is currently trustworthy.

### 8. Distinguish source health from field conflict

`VerificationStatus.CONFLICTING_INFORMATION` is source-level and therefore too coarse to represent ordinary multi-source field disagreements.

PR6 policy:

- **field conflict** is the normal mechanism for differing claims about one field/scope;
- do not mark an entire source conflicting merely because one extracted field disagrees with another source;
- source-level `CONFLICTING_INFORMATION` is reserved for cases where the source itself is internally contradictory, broadly unreliable for the relevant record, or a curator intentionally blocks the entire source pending review.

This prevents one disputed deadline from invalidating unrelated identity/funding evidence from the same official page.

`EvidencePolicy.has_disqualifying_official_source()` must therefore not become the sole PR6 field-resolution mechanism.

### 9. Define deterministic resolution outcomes

For a set of comparable claims, return one of:

```text
CORROBORATED
RESOLVED_SINGLE_SOURCE
RESOLVED_BY_SCOPE
RESOLVED_BY_AUTHORITY
RESOLVED_BY_SUPERSESSION
PARTIAL_SUPPORT
UNSUPPORTED_AUTHORITY
STALE_ONLY
CONFLICT_REVIEW_REQUIRED
UNRESOLVED
```

#### `CORROBORATED`

Two or more valid comparable claims normalize to the same value.

#### `RESOLVED_SINGLE_SOURCE`

One valid claim exists and no applicable competing claim exists.

#### `RESOLVED_BY_SCOPE`

Different values apply to different legitimate scopes; no conflict.

#### `RESOLVED_BY_AUTHORITY`

A field policy clearly establishes that one source is authoritative for the target scope and the competing source is not authorized for that field/scope.

The lower-authority disagreement remains visible in diagnostics; it is not silently deleted.

#### `RESOLVED_BY_SUPERSESSION`

A later authoritative version explicitly supersedes an older version for the same scope/cycle.

#### `PARTIAL_SUPPORT`

Evidence supports only part of the proposed structured value/collection.

#### `UNSUPPORTED_AUTHORITY`

The source is official in some context but cannot establish this field at this scope.

#### `STALE_ONLY`

Only stale/old-cycle otherwise-valid claims exist.

#### `CONFLICT_REVIEW_REQUIRED`

Two or more current, applicable, adequately authoritative claims disagree for the same semantic claim key and no deterministic rule resolves them.

#### `UNRESOLVED`

Required identity/scope/version information is insufficient to decide safely.

### 10. Equality/canonicalization is field-specific

Do not compare arbitrary JSON/text with one generic similarity score.

Use typed canonicalizers:

#### Dates/deadlines

- normalize to timezone-aware instant when the source provides sufficient timezone semantics;
- preserve original label/timezone;
- calendar-date-only deadlines remain date semantics rather than inventing midnight UTC;
- exact target scope/deadline type required.

#### Currency amounts

- decimal normalization;
- uppercase ISO currency where explicit;
- amount frequency/unit is part of value identity;
- `3000 CNY/month` is not equal to `3000 CNY/year`.

#### Coverage enums/booleans

- compare explicit canonical enum state.

#### Eligibility rules

- compare canonical rule type/operator/value/unit/grading scale plus scope.

#### URLs

- use the shared normalized URL policy; redirects/safe canonical URLs remain provenance.

#### Free text

- safe deterministic normalization can remove harmless whitespace/Unicode differences;
- semantic paraphrase similarity is not enough to auto-resolve a decision-critical conflict;
- where possible, extract text into structured typed rules/components instead of comparing paragraphs.

AI may propose that two text claims are semantically equivalent, but it cannot settle a Tier 0/Tier 1 conflict without deterministic support/review.

### 11. "Newer fetch" is not automatically "newer policy"

`SourceSnapshot.fetched_at` means when we fetched the source, not when the policy took effect.

Supersession requires stronger evidence such as:

- same source URL/content lineage changed from old value to new value and the source is current;
- explicit current-cycle/version/date marker;
- source publication/update metadata when reliable;
- reviewed successor/source relationship.

A snapshot fetched today containing an archived 2025 PDF cannot supersede a 2027 current page merely because its `fetched_at` is newer.

### 12. Cycle applicability is mandatory for volatile Tier 1 facts

Deadlines, current funding, current eligibility, and application routes require current-cycle applicability according to completeness/freshness policy.

Claims from different cycles coexist historically and do not conflict.

Example:

```text
2026 stipend = 2,500
2027 stipend = 3,000
```

is versioned cycle history, not a conflict.

If cycle applicability cannot be established, the resolver returns `UNRESOLVED`/`STALE_ONLY` rather than guessing.

### 13. Different languages from the same authority do not get special trust

Official translations/local-language pages can corroborate one another after typed normalization.

If official language versions disagree materially for the same scope/current version:

- do not let machine translation choose the winner;
- check version/publication/currentness first;
- if still unresolved, create a conflict set.

A generated translation never becomes conflict-resolution evidence.

### 14. Persist real conflict sets, not only strings

PR6 should replace/augment opaque candidate conflict strings with durable structured conflict records.

Recommended `CatalogueConflictSet` fields:

```text
id UUID PK
bundle_id UUID NOT NULL
claim_key_hash varchar(64) NOT NULL
field_path varchar(255) NOT NULL
scope_snapshot JSON NOT NULL
collection_key varchar(255) NULL
severity varchar(32) NOT NULL
status varchar(32) NOT NULL
reason_code varchar(100) NOT NULL
claim_ids JSON NOT NULL
resolution_kind varchar(64) NULL
selected_claim_id UUID NULL
resolution_notes text NULL
reviewer_id UUID NULL
reviewed_at timestamptz NULL
created_at timestamptz NOT NULL
resolved_at timestamptz NULL
```

Status:

```text
open
resolved_deterministically
resolved_by_review
superseded
```

Conflict rows are audit history. Resolution appends/records the decision rather than deleting disagreeing claims.

### 15. Human review cannot erase losing evidence

When a reviewer resolves a genuine conflict:

- preserve every claim and evidence snapshot;
- record selected claim/value and reason;
- record reviewer/time;
- materialize only the approved effective fact into public graph state;
- mark non-selected claims as non-effective/superseded/rejected for this resolution, not deleted.

Future source changes can reopen a field by creating a new bundle/conflict assessment.

### 16. Deterministic resolutions should also be auditable

Not every differing value needs human review. Scope/authority/version rules can resolve many safely.

Even then, store reason codes such as:

```text
LOCAL_SCOPE_OVERRIDE
DIFFERENT_CYCLE
CANONICAL_OWNER_AUTHORITY
EXPLICIT_SOURCE_SUPERSESSION
DUPLICATE_CORROBORATION
```

so the platform can explain why a value was chosen.

### 17. Materialize graph facts only after resolution

Recommended PR6 flow:

```text
safe official snapshots
  -> per-source extraction proposals
  -> claim normalization
  -> field evidence validation
  -> scope + authority + cycle resolution
  -> conflict detection
  -> review where required
  -> canonical graph materialization
  -> completeness reassessment
```

Do not overwrite a reviewed canonical fact directly from a new extraction before the resolver runs.

### 18. Materialization preserves effective scope, never flattens child facts globally

Examples:

- provider global deadline -> scholarship/cycle `ScopedDeadline`;
- embassy deadline -> track/country-mission route representation, not global deadline;
- university deadline -> institution-scoped `ScopedDeadline`;
- programme IELTS -> programme-scoped eligibility rule;
- provider stipend -> scholarship/cycle funding component;
- institution-specific top-up -> institution-scoped funding component if official evidence supports it.

Legacy top-level `Opportunity.application_deadline`, stipend, and text fields may remain compatibility projections during migration, but the graph resolver becomes authoritative for multi-source truth.

### 19. Compatibility projections must have one deterministic producer

If legacy top-level fields continue to serve public/search consumers during transition:

- only a graph projection/materialization service writes them from resolved current effective facts;
- extraction services do not write them independently;
- local/institution facts never project into global fields;
- projection policy is versioned/tested;
- eventual removal is possible once all consumers use scoped graph reads.

This prevents graph truth and legacy columns from diverging.

### 20. Completeness consumes resolver outcomes, not raw row presence

ADR 0008's completeness engine must use effective/resolved claim states.

Examples:

```text
Deadline row exists + unsupported evidence
  -> APPLICATION_TIMING = UNSUPPORTED

Two same-scope current provider deadlines conflict
  -> APPLICATION_TIMING = CONFLICTING

Global + institution deadline differ legitimately
  -> both VERIFIED_CURRENT at their own scopes

Only previous-cycle funding evidence exists
  -> FUNDING = STALE
```

This keeps discovery objectives tightly connected to actual trust gaps.

### 21. AI assistant reads resolved facts plus conflict metadata

The downstream assistant may explain:

```text
"The scholarship provider lists 1 June as the global deadline, while the Malaysian embassy route closes on 15 May. If you are applying through the Malaysian embassy route, use 15 May."
```

because these are resolved scope-specific facts.

For a genuine unresolved same-scope conflict, it must say the information is under review/official sources disagree rather than selecting one.

The assistant may not override `CONFLICT_REVIEW_REQUIRED`.

### 22. Source changes invalidate only affected claims/facts when possible

When source monitoring detects a content hash change:

- create a new immutable snapshot;
- determine which prior claim field paths came from the changed source;
- re-extract/revalidate those fields under bounded policy;
- rerun only affected claim keys/scopes plus dependent completeness dimensions;
- do not invalidate unrelated facts from other unchanged sources automatically.

This is essential for cost-efficient freshness monitoring at scale.

### 23. Conflict severity is based on criticality, not source count

Initial severity mapping:

```text
Tier 0 identity/independence conflict -> critical
Tier 1 deadline/funding/eligibility/route conflict -> high
Tier 2 documents/steps/local workflow -> medium unless deadline/safety implication elevates it
Tier 3 enrichment wording -> low
```

One critical two-source conflict matters more than ten matching low-risk enrichment claims.

### 24. No majority voting over official sources

Three official pages saying X and one official page saying Y does not automatically make X true.

Official sources are not independent votes. They may copy from each other, be stale, or have different scopes.

Resolution is based on:

```text
scope
+ authority
+ cycle/version
+ evidence quality/currentness
+ explicit deterministic policy
```

not source count.

Corroboration count may improve diagnostics but never replaces authority reasoning.

### 25. No universal numeric confidence score for truth selection

A model or heuristic may provide extraction confidence for routing/review, but a score such as `0.91` must not choose between conflicting official values.

Truth selection uses discrete policy outcomes and evidence.

### 26. PR6 implementation should be additive

Do not rewrite PR2/PR3 evidence/classification history.

Likely PR6 work:

- additive evidence-bundle/claim/conflict structures;
- resolver service;
- field authority policy;
- typed canonicalizers;
- graph materializer/projection bridge;
- tests/Gold fixtures;
- read-only admin conflict/evidence diagnostics;
- existing publication boundary remains human-controlled.

PR5 discovery continues to produce high-quality official leads/sources; it does not take over PR6's fact resolution.

## Resolution algorithm

Conceptual deterministic algorithm:

```text
for each bundle:
  validate every claim's snapshot + excerpt + source
  normalize typed value
  derive exact graph scope
  derive source authority for field/scope
  derive cycle/version applicability

  group claims by semantic claim key

  for each group:
    discard/reclassify invalid or unauthorized claims from effective set

    partition by exact scope + applicable cycle/version

    if zero valid claims:
      unresolved/unsupported/stale

    if all valid claims normalize equal:
      corroborated/resolved

    else if values belong to legitimately different scopes:
      resolve by scope; keep all

    else if explicit supersession/current-version rule applies:
      resolve by supersession; retain history

    else if authority policy accepts one claim and rejects the competitor for this field/scope:
      resolve by authority; surface disagreement diagnostically

    else:
      create CONFLICT_REVIEW_REQUIRED
```

The resolver never asks a model which official value "looks right."

## Required tests

PR6 implementation must prove at least:

1. global provider deadline and institution deadline coexist without conflict;
2. two different institution deadlines coexist when institution IDs differ;
3. two current same-scope provider deadlines create a conflict;
4. same value from two accepted sources becomes corroboration;
5. previous-cycle value does not conflict with current-cycle value;
6. a current explicit superseding source can resolve an old version without deleting history;
7. newer fetch time alone cannot establish supersession;
8. application portal cannot override global funding;
9. country mission can establish country-route deadline but not global funding by default;
10. institution source can establish institution/programme requirements at matching scope;
11. supporting institution cannot redefine umbrella scholarship identity;
12. field conflict does not automatically mark the entire source conflicting;
13. source-level conflicting status still blocks source use when the whole source is curator-blocked;
14. free-text similarity cannot automatically settle critical conflicting claims;
15. currency frequency/unit mismatch is treated as different values;
16. date/timezone normalization preserves date-only semantics;
17. losing/rejected claims and evidence remain auditable after review resolution;
18. no majority voting determines truth;
19. graph materialization occurs only after resolution;
20. local facts cannot project into global compatibility columns;
21. changed source re-evaluation can target affected fields without invalidating unrelated-source facts;
22. completeness receives `CONFLICTING`, `STALE`, `UNSUPPORTED`, or verified scoped outcomes correctly;
23. AI cannot override an unresolved conflict.

## Gold cases

Conflict/evidence Gold evaluation should include at minimum:

- MEXT global guidance + Malaysia embassy deadline + university recommendation deadline;
- CSC global provider funding + Tsinghua local application requirements;
- Chevening global scholarship page + country guidance page;
- an official source that changes deadline between cycles;
- two current official provider pages with an actual same-scope disagreement;
- an application portal whose workflow data is valid but funding prose is not authoritative;
- multilingual official pages with equivalent facts;
- multilingual official pages with materially different current facts;
- explicit "no application fee" vs another page silent on fee;
- programme-specific language threshold stricter than global scholarship threshold.

## Consequences

### Positive

- Multiple official pages become an advantage rather than a source of accidental corruption.
- Legitimate local/global differences are preserved and explained.
- Genuine conflicts become structured, reviewable, and auditable.
- One disputed field no longer poisons an entire otherwise-useful official source.
- Completeness and autonomous acquisition can target the exact unresolved claim.
- The AI assistant can explain route/institution differences without inventing a winner.

### Cost

- PR6 becomes a real evidence-resolution subsystem rather than text concatenation.
- Field-specific authority/canonicalization policies require careful tests.
- Some conflicts will remain unresolved longer because the platform refuses majority voting or model preference.
- Legacy top-level catalogue fields need a controlled projection bridge during migration.

These costs are accepted because provenance-safe multi-source resolution is necessary for complete scholarship information without false certainty.
