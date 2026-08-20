# ADR 0013: Use an immutable typed claim ledger with append-only assessments and deterministic family resolvers

- Status: Accepted for PR6 architecture
- Date: 2026-08-19
- Applies to: PR6 v2 extraction, evidence bundles, claim normalization, scope/authority resolution, conflicts, materialization, refresh, and auditability
- Related: ADR 0008, ADR 0009, ADR 0010, ADR 0012

## Context

ADR 0009 establishes the required truth policy:

```text
source-local extraction
 -> field claims
 -> exact evidence
 -> scope
 -> authority
 -> version/cycle
 -> conflict resolution
 -> graph materialization
```

ADR 0012 establishes the pre-publication trust boundary:

- candidate source bytes must be preserved immutably before graph identity exists;
- candidate evidence must not create a draft `Opportunity` merely to obtain canonical evidence storage;
- accepted exact bytes may later be promoted into canonical `SourceSnapshot`/`FieldEvidence` without re-fetching;
- extraction v2 is source-relative and may not emit canonical graph UUIDs.

The remaining implementation question is how to represent claims and resolution without creating a second, mutable truth database.

A naive table such as:

```text
field_path
scope_json
value_json
confidence
status
```

is not sufficient.

It would create several problems:

1. model-generated `field_path` can silently expand the ontology;
2. one mutable `status` loses the history of why a claim was accepted/rejected under a particular policy version;
3. one excerpt per claim cannot represent values whose applicability/scope is established by a second source sentence;
4. different domain families do not have the same conflict semantics;
5. a generic JSON equality test cannot safely resolve eligibility constraints, ordered steps, funding units, dates, or set membership;
6. retry/provider-call history must remain distinct from the logical extraction artifact;
7. conflict membership should use real foreign keys rather than JSON arrays of claim IDs;
8. graph mutation needs an auditable mapping back to the resolution that authorized it.

The PR6 implementation therefore needs one common evidence/claim ledger while preserving typed domain semantics.

## Decision

### 1. PR6 is a ledger + deterministic resolver pipeline, not another catalogue

The durable layers are:

```text
Candidate/Canonical immutable snapshot
             |
             v
      Source Extraction
             |
             v
      Immutable Claims
             |
             v
   Exact Evidence Validation
             |
             v
  Append-only Claim Assessment
             |
             v
 Typed Claim-Set Resolution
             |
       +-----+------+
       |            |
    resolved     conflict
       |            |
       v            v
 materialization   review
```

Only the canonical Scholarship Intelligence Graph is publication truth.

PR6 staging rows are audit/proposal/resolution history.

### 2. Use a normalized `CatalogueEvidenceBundle`

A bundle is one bounded resolution unit for one acquisition/refresh objective.

Recommended table:

```text
catalogue_evidence_bundles
```

Fields:

```text
id UUID PK
candidate_id UUID NULL
opportunity_id UUID NULL
objective_kind varchar(64) NOT NULL
objective_scope_snapshot JSON NOT NULL
target_identity_snapshot JSON NOT NULL
resolver_policy_version varchar(100) NOT NULL
status varchar(32) NOT NULL
input_fingerprint varchar(64) NOT NULL
created_at timestamptz NOT NULL
started_at timestamptz NULL
completed_at timestamptz NULL
failure_code varchar(100) NULL
```

Target constraint:

```text
(candidate_id IS NOT NULL) XOR (opportunity_id IS NOT NULL)
```

Meaning:

- candidate bundle = pre-canonical acquisition;
- opportunity bundle = published/draft canonical refresh/enrichment.

Do not mutate a candidate bundle into an opportunity bundle later.

Snapshot promotion/materialization creates the cross-boundary history.

Recommended uniqueness:

```text
UNIQUE(target kind, target id, objective kind, input_fingerprint, resolver_policy_version)
```

or equivalent explicit columns/partial indexes.

### 3. Bundle workflow state is mutable; truth claims are not

Bundle status is orchestration state, not truth.

Initial state machine:

```text
PENDING
  -> EXTRACTING
  -> READY_FOR_RESOLUTION
  -> RESOLVING
  -> RESOLVED
```

Exceptional/terminal states:

```text
REVIEW_REQUIRED
BLOCKED
BUDGET_EXHAUSTED
FAILED
```

Allowed transitions are explicit and tested.

Do not infer truth from bundle status alone.

### 4. Replace JSON snapshot membership with `CatalogueEvidenceBundleSource`

Recommended table:

```text
catalogue_evidence_bundle_sources
```

Fields:

```text
id UUID PK
bundle_id UUID NOT NULL
candidate_source_snapshot_id UUID NULL
source_snapshot_id UUID NULL
source_context_hash varchar(64) NOT NULL
normalized_url varchar(2048) NOT NULL
domain varchar(255) NOT NULL
source_owner_type varchar(32) NOT NULL
source_owner_id UUID NULL
officiality_status varchar(32) NOT NULL
authority_class varchar(64) NOT NULL
authority_scope_snapshot JSON NOT NULL
authority_policy_version varchar(100) NOT NULL
created_at timestamptz NOT NULL
```

Snapshot constraint:

```text
(candidate_source_snapshot_id IS NOT NULL)
XOR
(source_snapshot_id IS NOT NULL)
```

Uniqueness:

```text
UNIQUE(bundle_id, candidate_source_snapshot_id)
UNIQUE(bundle_id, source_snapshot_id)
```

with partial indexes where necessary.

The row freezes the authority/officiality context used by this resolution.

Later changes to a source registry do not silently rewrite why a historical claim was accepted.

### 5. Separate logical extraction from provider request attempts

V1 `CatalogueExtractionAttempt` remains historical and unchanged.

PR6 v2 introduces two concepts.

#### `CatalogueSourceExtraction`

One logical extraction artifact for one immutable snapshot and one extraction contract.

Recommended fields:

```text
id UUID PK
candidate_source_snapshot_id UUID NULL
source_snapshot_id UUID NULL
target_context_hash varchar(64) NOT NULL
claim_plan_hash varchar(64) NOT NULL
schema_version varchar(100) NOT NULL
instruction_version varchar(100) NOT NULL
prompt_hash varchar(64) NOT NULL
provider varchar(100) NOT NULL
model varchar(255) NOT NULL
contract_fingerprint varchar(64) NOT NULL
status varchar(32) NOT NULL
accepted_output_json JSON NULL
created_at timestamptz NOT NULL
completed_at timestamptz NULL
```

Snapshot XOR constraint is required.

Logical status:

```text
PENDING
RUNNING
SUCCEEDED
FAILED
```

Uniqueness is based on the immutable snapshot plus complete extraction contract.

Conceptually:

```text
snapshot identity
+ target context hash
+ allowed claim-family plan
+ schema version
+ instruction/prompt version
+ provider/model
```

The same successful artifact may be reused without another model request.

#### `CatalogueSourceExtractionAttempt`

One row per outbound provider request.

Recommended fields:

```text
id UUID PK
extraction_id UUID NOT NULL
attempt_number int NOT NULL
status varchar(32) NOT NULL
request_fingerprint varchar(64) NOT NULL
provider_response_id varchar(255) NULL
input_tokens int NULL
output_tokens int NULL
estimated_cost numeric(12,6) NOT NULL default 0
latency_ms int NULL
error_code varchar(100) NULL
started_at timestamptz NOT NULL
completed_at timestamptz NULL
```

Uniqueness:

```text
UNIQUE(extraction_id, attempt_number)
```

Attempt lifecycle:

```text
IN_PROGRESS
  -> SUCCEEDED
  -> RATE_LIMITED
  -> TIMEOUT
  -> PROVIDER_FAILED
  -> SCHEMA_FAILED
  -> ABANDONED
```

Insert the attempt before network I/O.

Terminal attempts are immutable.

Retries create a new attempt number rather than overwriting history.

This mirrors ADR 0006's discovery durability principle.

### 6. Provider success and evidence validity are separate concepts

A provider request can successfully return schema-valid JSON while one proposed excerpt does not exist in the source snapshot.

Therefore:

```text
provider request status != evidence validation status
```

Do not mark the provider request `VALIDATION_FAILED` merely because a later deterministic claim check fails.

This makes extraction-provider reliability metrics meaningful.

### 7. Define a closed `ClaimType` enum; models cannot invent field paths

Initial PR6 claim types:

```text
SCHOLARSHIP_NAME
PROVIDER_NAME
HOST_COUNTRY
DEGREE_LEVEL
CYCLE_LABEL
CYCLE_STATUS
TRACK_ROUTE
APPLICATION_OPENING
APPLICATION_DEADLINE
APPLICATION_URL
APPLICATION_METHOD
FUNDING_COMPONENT
APPLICATION_FEE
ELIGIBILITY_RULE
REQUIRED_DOCUMENT
APPLICATION_STEP
INSTITUTION_PARTICIPATION
PROGRAMME_PARTICIPATION
```

Relationship/independence evidence may be emitted as bounded relationship signals for PR3, but PR6 does not create a new independent scholarship from a claim.

New claim types require a code/schema/policy change and tests.

No arbitrary model-generated canonical `field_path` is accepted.

### 8. Claims are immutable source assertions

Recommended table:

```text
catalogue_field_claims
```

Fields:

```text
id UUID PK
bundle_id UUID NOT NULL
bundle_source_id UUID NOT NULL
source_extraction_id UUID NOT NULL
ordinal int NOT NULL
claim_type varchar(64) NOT NULL
collection_key_hint varchar(255) NULL
scope_hint_snapshot JSON NOT NULL
source_value_json JSON NOT NULL
source_value_hash varchar(64) NOT NULL
value_state varchar(32) NOT NULL
claim_fingerprint varchar(64) NOT NULL
created_at timestamptz NOT NULL
```

Uniqueness:

```text
UNIQUE(source_extraction_id, ordinal)
UNIQUE(bundle_id, claim_fingerprint)
```

`value_state` is restricted to source-assertion semantics:

```text
ASSERTED_VALUE
ASSERTED_ABSENT
ASSERTED_UNKNOWN
ASSERTED_NOT_APPLICABLE
```

Important:

- a model cannot use `ASSERTED_UNKNOWN` because it failed to find text;
- `ASSERTED_UNKNOWN` requires explicit source wording expressing uncertainty/no fixed value;
- ordinary silence produces no claim.

Claims never contain canonical graph UUIDs from model output.

Claims do not have a mutable `claim_status`.

### 9. Claim value JSON uses a discriminated typed schema

Do not store arbitrary JSON accepted from the provider.

Pydantic/application schema must use a discriminated union by claim type/value kind.

Conceptual examples:

```text
TextValue
EnumValue
DegreeLevelValue
TemporalValue
MoneyComponentValue
CoverageValue
EligibilityPredicateValue
DocumentValue
ApplicationStepValue
ParticipationValue
UrlValue
```

Each type has explicit max lengths, enums, numeric bounds, and required combinations.

The stored `source_value_json` is the validated typed representation, not raw model JSON.

### 10. Temporal claims preserve source precision

`TemporalValue` must not invent precision.

Conceptual shape:

```text
kind: temporal
precision: DATE | DATETIME
calendar_date: YYYY-MM-DD | null
datetime_value: ISO-8601 offset-aware | null
timezone: IANA zone | null
source_label: string | null
```

Constraints:

- `DATE` => `calendar_date` required, `datetime_value` null;
- `DATETIME` => `datetime_value` required;
- timezone is required only when the source semantics require/establish it;
- a source saying `20 May 2027` must never become invented `2027-05-20T00:00:00Z`.

Rolling/no-fixed-date state belongs in a typed application-window/status claim, not a fabricated timestamp.

### 11. Funding values preserve unit/frequency

A funding amount identity includes at least:

```text
component_type
amount/range
currency
frequency/unit
coverage_status
```

Example:

```text
CNY 3,000 per month
```

is not equal to:

```text
CNY 3,000 per year
```

A one-time grant must not normalize to monthly stipend.

### 12. Degree levels are set-membership claims, not one scholarship scalar

A source supporting:

```text
Bachelor
Master
PhD
```

emits three `DEGREE_LEVEL` membership claims at the proper scope.

It does not choose one `Opportunity.degree_level`.

Whether the source proves the *complete* supported-level set is a separate completeness/applicability question; page silence does not imply absence of another level.

### 13. Scope hints are typed and bounded

The extraction model may return only source-derived public hints such as:

```text
cycle_label
track_name
route_country_code
institution_name
programme_name
```

No IDs.

No applicant/profile data.

No free-form arbitrary dictionary.

Maximum lengths/counts are enforced.

The system canonicalizes the typed hint snapshot and hashes it.

### 14. A claim can have multiple evidence items

One semantic claim may need:

- value evidence;
- scope/applicability evidence;
- supersession/current-cycle evidence.

Introduce:

```text
catalogue_claim_evidence
```

Recommended fields:

```text
id UUID PK
claim_id UUID NOT NULL
ordinal int NOT NULL
role varchar(32) NOT NULL
excerpt text NOT NULL
section_label varchar(255) NULL
locator varchar(255) NULL
validation_status varchar(32) NOT NULL
excerpt_start int NULL
excerpt_end int NULL
failure_code varchar(100) NULL
created_at timestamptz NOT NULL
validated_at timestamptz NULL
```

Evidence roles:

```text
VALUE
SCOPE
APPLICABILITY
NEGATION
SUPERSESSION
```

Uniqueness:

```text
UNIQUE(claim_id, ordinal)
```

All evidence for a claim must refer to the same `bundle_source_id`/immutable snapshot as the claim.

### 15. Evidence validation has a one-way state machine

Evidence starts:

```text
PENDING
```

and transitions exactly once to:

```text
MATCHED
NOT_FOUND
AMBIGUOUS
INVALID
```

For `MATCHED`:

```text
excerpt_start IS NOT NULL
excerpt_end IS NOT NULL
snapshot_text[excerpt_start:excerpt_end] == excerpt
```

For other terminal states offsets are null.

After terminal transition, the evidence row is immutable.

A critical claim with missing/ambiguous required evidence cannot become effective.

### 16. Claims themselves are never edited after persistence

If parsing/canonicalization rules improve:

- keep the original claim;
- create a new extraction artifact/claim set under the new contract, or
- create a new assessment under the new resolver policy when source assertion did not change.

Do not rewrite historical source assertions.

### 17. Append `CatalogueClaimAssessment` instead of mutating claim status

Recommended table:

```text
catalogue_claim_assessments
```

One row records deterministic interpretation of one immutable claim under one complete policy fingerprint.

Fields:

```text
id UUID PK
claim_id UUID NOT NULL
supersedes_assessment_id UUID NULL
policy_fingerprint varchar(64) NOT NULL
scope_resolver_version varchar(100) NOT NULL
authority_policy_version varchar(100) NOT NULL
canonicalizer_version varchar(100) NOT NULL
cycle_policy_version varchar(100) NOT NULL
evidence_status varchar(32) NOT NULL
scope_status varchar(32) NOT NULL
authority_status varchar(32) NOT NULL
applicability_status varchar(32) NOT NULL
canonical_field_path varchar(255) NOT NULL
collection_key varchar(255) NULL
candidate_id UUID NULL
scholarship_id UUID NULL
cycle_id UUID NULL
track_id UUID NULL
institution_id UUID NULL
programme_id UUID NULL
normalized_value_json JSON NULL
normalized_value_hash varchar(64) NULL
claim_key_hash varchar(64) NULL
reason_codes JSON NOT NULL
created_at timestamptz NOT NULL
```

Uniqueness:

```text
UNIQUE(claim_id, policy_fingerprint)
```

Assessment rows are append-only.

A new policy version creates a new assessment linked by `supersedes_assessment_id`.

### 18. Scope resolution status is explicit

Initial `scope_status`:

```text
RESOLVED_EXISTING
PROPOSED_NEW_SCOPE
AMBIGUOUS_SCOPE
UNRESOLVED_SCOPE
OUT_OF_TARGET_SCOPE
```

`PROPOSED_NEW_SCOPE` is staging only.

It does not create graph entities by itself.

For a candidate bundle, the scholarship target is the immutable candidate target contract. Canonical `scholarship_id` remains null until graph identity exists.

### 19. Authority resolution status is explicit

Initial `authority_status`:

```text
AUTHORIZED
UNSUPPORTED_AUTHORITY
UNRESOLVED_AUTHORITY
SOURCE_BLOCKED
```

Authority is derived from `CatalogueEvidenceBundleSource` context + versioned `FieldAuthorityPolicy`.

The model cannot set this field.

### 20. Applicability/version status is explicit

Initial `applicability_status`:

```text
CURRENT_APPLICABLE
HISTORICAL_APPLICABLE
FUTURE_APPLICABLE
STALE
UNRESOLVED_APPLICABILITY
NOT_APPLICABLE
```

Fetch time alone cannot choose currentness.

### 21. Claim key is system-derived after scope resolution

Conceptual scalar key:

```text
(
  target scholarship identity,
  cycle,
  track,
  institution,
  programme,
  canonical field path,
  collection key
)
```

`claim_key_hash` is calculated only after the resolver knows enough scope/field semantics.

The model never supplies the hash.

### 22. Do not use one universal resolver for every claim type

PR6 provides one resolution orchestration interface with typed family resolvers.

Initial resolver families:

```text
ScalarClaimResolver
TemporalClaimResolver
SetMembershipResolver
MoneyComponentResolver
EligibilityConstraintResolver
OrderedStepResolver
ParticipationResolver
```

#### Scalar

Identity/status/simple enum/text where exact same claim key expects one effective value.

#### Temporal

Opening/deadline with date-vs-datetime precision and timezone semantics.

#### Set membership

Degree levels, required documents, institution/programme participation.

A different set member is not automatically a conflict.

#### Money component

Funding component + amount/currency/frequency/coverage semantics.

#### Eligibility constraint

Eligibility is a set of predicates. Generic scalar equality is not enough.

Examples:

```text
IELTS >= 6.5
IELTS >= 7.0
```

may be a scoped override/conflict depending authority/scope.

```text
Nationality IN {...}
Nationality NOT_IN {...}
```

requires predicate/set reasoning, not string similarity.

#### Ordered steps

Application steps have sequence semantics. Two different steps can both be valid; ordering/identity must be resolved deterministically.

### 23. Resolver output is a durable `CatalogueClaimResolution`

Recommended table:

```text
catalogue_claim_resolutions
```

Fields:

```text
id UUID PK
bundle_id UUID NOT NULL
supersedes_resolution_id UUID NULL
claim_key_hash varchar(64) NOT NULL
canonical_field_path varchar(255) NOT NULL
collection_key varchar(255) NULL
scope_snapshot JSON NOT NULL
resolver_family varchar(64) NOT NULL
policy_fingerprint varchar(64) NOT NULL
outcome varchar(64) NOT NULL
effective_value_json JSON NULL
effective_value_hash varchar(64) NULL
reason_codes JSON NOT NULL
created_at timestamptz NOT NULL
```

Initial outcomes retain ADR 0009 semantics:

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

Resolution rows are append-only.

A new resolver policy creates a superseding resolution; historical results remain.

### 24. Normalize resolution membership instead of storing claim IDs in JSON

Introduce:

```text
catalogue_claim_resolution_members
```

Fields:

```text
resolution_id UUID NOT NULL
claim_assessment_id UUID NOT NULL
role varchar(32) NOT NULL
created_at timestamptz NOT NULL
```

Roles:

```text
EFFECTIVE
CORROBORATING
COMPETING
REJECTED_AUTHORITY
STALE
OUT_OF_SCOPE
PARTIAL
```

Uniqueness:

```text
UNIQUE(resolution_id, claim_assessment_id)
```

This preserves FK integrity and makes diagnostics queryable.

### 25. Genuine conflicts get a structured review object

`CONFLICT_REVIEW_REQUIRED` creates/reuses:

```text
catalogue_conflict_sets
```

Recommended fields:

```text
id UUID PK
bundle_id UUID NOT NULL
resolution_id UUID NOT NULL
claim_key_hash varchar(64) NOT NULL
severity varchar(32) NOT NULL
status varchar(32) NOT NULL
reason_code varchar(100) NOT NULL
created_at timestamptz NOT NULL
resolved_at timestamptz NULL
```

Use normalized membership:

```text
catalogue_conflict_claims
  conflict_set_id
  claim_assessment_id
  role
```

Do not store the authoritative conflict membership only as JSON IDs.

### 26. Human conflict decisions are append-only

Introduce:

```text
catalogue_conflict_review_decisions
```

Recommended fields:

```text
id UUID PK
conflict_set_id UUID NOT NULL
supersedes_decision_id UUID NULL
decision varchar(32) NOT NULL
selected_claim_assessment_id UUID NULL
resolution_notes text NOT NULL
reviewer_id UUID NOT NULL
created_at timestamptz NOT NULL
```

Possible decisions:

```text
SELECT_CLAIM
CONFIRM_SCOPE_SPLIT
CONFIRM_SUPERSESSION
KEEP_UNRESOLVED
REJECT_ALL
```

A decision never deletes losing evidence.

### 27. Conflict-set status is workflow state, not evidence mutation

Status:

```text
OPEN
RESOLVED_DETERMINISTICALLY
RESOLVED_BY_REVIEW
SUPERSEDED
```

Claims/assessments remain immutable regardless of conflict workflow.

### 28. Materialization has its own immutable audit mapping

Introduce:

```text
catalogue_graph_materializations
```

Fields:

```text
id UUID PK
resolution_id UUID NOT NULL
materializer_version varchar(100) NOT NULL
operation varchar(32) NOT NULL
entity_type varchar(64) NOT NULL
entity_id UUID NOT NULL
field_path varchar(255) NOT NULL
previous_materialization_id UUID NULL
created_at timestamptz NOT NULL
```

Operations:

```text
CREATE
UPDATE
NOOP
SUPERSEDE
DEACTIVATE
```

The table records what canonical graph mutation was authorized by which resolution.

It does not replace canonical `FieldEvidence`.

### 29. Canonical graph evidence always points to canonical `SourceSnapshot`

For candidate acquisition:

```text
candidate snapshot
 -> accepted resolution/review
 -> exact snapshot promotion
 -> canonical SourceSnapshot
 -> canonical graph fact
 -> FieldEvidence
```

For canonical refresh:

```text
canonical SourceSnapshot
 -> accepted resolution/review
 -> graph fact
 -> FieldEvidence
```

`FieldEvidence` never points to AI output, extraction attempt, bundle, or claim as the source of truth.

### 30. Graph materializers are typed and closed

Initial materializers correspond to real graph models, for example:

```text
IdentityMaterializer
CycleMaterializer
TrackMaterializer
ScopedDeadlineMaterializer
FundingComponentMaterializer
EligibilityRuleMaterializer
RequiredDocumentMaterializer
ApplicationStepMaterializer
InstitutionParticipationMaterializer
TrackProgrammeMaterializer
```

No generic function may take arbitrary model `field_path` and setattr ORM rows.

### 31. Materialization is transactional

For one accepted resolution transaction:

1. lock/recheck target canonical identity/version as required;
2. create/update the typed graph entity/fact;
3. promote/reuse exact canonical snapshot;
4. create required `FieldEvidence` rows;
5. create `CatalogueGraphMaterialization` audit row;
6. update compatibility projection only through the projection service;
7. commit.

If evidence/materialization fails, none of the graph mutation is committed.

### 32. Optimistic stale-write protection is required

A resolution created from graph version/state X cannot blindly overwrite graph state that changed to Y before materialization.

Materializer input must include a deterministic target-state/version fingerprint.

Before write:

```text
current target fingerprint == resolution target fingerprint
```

or the materialization is rejected as stale and the affected claim key is re-resolved.

This protects concurrent refresh/review work.

### 33. Resolver reads are deterministic snapshots

A bundle resolution freezes:

```text
input claims
claim assessment policy versions
source authority context
current graph target/version fingerprint
```

Do not let a long-running resolver silently observe different graph states halfway through and mix them into one decision.

Use one transaction/repeatable read strategy or explicit input snapshots/fingerprints according to implementation constraints.

### 34. No majority voting and no numeric truth confidence

The ledger may record corroborating claim count for diagnostics.

It never selects truth because `3 sources > 1 source`.

No `confidence=0.97` chooses the effective claim.

Truth resolution remains:

```text
scope
+ authority
+ version/cycle
+ exact evidence
+ typed domain policy
+ human review where deterministic rules stop
```

### 35. No model is called by the resolver

The resolver/materializer layer must have no dependency on an LLM provider.

This is an important testable architecture boundary.

A future AI tool may explain a conflict to a reviewer, but its output is not a resolver input.

### 36. Source extraction content is still untrusted data

The extraction provider receives:

```text
system instruction
+ public target context
+ one bounded source snapshot text
```

No web/discovery tools.

No applicant/private context.

No instruction found inside source text may change the extraction contract.

### 37. JSON columns are typed snapshots, not dumping grounds

Every JSON field in this ADR must have:

- a dedicated Pydantic/schema model;
- `extra=forbid`;
- maximum string/list lengths;
- explicit enums;
- no applicant/private fields;
- deterministic canonical serialization before hashing.

Never store arbitrary ORM `model_dump()` or unrestricted provider output in target/scope/value snapshots.

### 38. Retention favors provenance

Recommended FKs after evidence exists:

```text
bundle -> candidate/opportunity RESTRICT or SET NULL + immutable target snapshot according to target lifecycle
bundle source -> snapshot RESTRICT
claim -> bundle/source/extraction RESTRICT
claim evidence -> claim RESTRICT
assessment -> claim RESTRICT
resolution member -> assessment RESTRICT
conflict -> resolution RESTRICT
materialization -> resolution RESTRICT
```

Do not use broad cascade deletion as the provenance retention policy.

Exact final FK choices must be migration-tested on PostgreSQL and SQLite where supported.

### 39. Existing v1 ingestion remains readable during migration

PR6 does not rewrite:

```text
catalogue_extraction_attempts
candidate.proposed_payload
candidate.conflicts
```

for old history.

New v2 candidates/bundles use the normalized ledger.

An admin compatibility response may summarize v2 resolution into existing candidate fields for UI continuity, but those JSON fields are not the PR6 source of truth.

### 40. PR6 does not yet automate publication

`APP_CATALOGUE_AUTO_PUBLISH_ENABLED=false` remains mandatory.

PR6 automates:

- source-local extraction;
- exact span location;
- claim canonicalization;
- scope/authority checks;
- corroboration;
- deterministic non-conflicting resolution;
- conflict routing;
- safe graph proposal/materialization at the existing review boundary.

It does not permit model-driven publication.

## Database invariants to prove

At minimum:

1. bundle target XOR candidate/opportunity;
2. bundle source snapshot XOR candidate/canonical snapshot;
3. source extraction snapshot XOR candidate/canonical snapshot;
4. one extraction contract cannot have duplicate successful logical artifacts;
5. provider attempts preserve `429 -> retry -> success` as separate rows;
6. terminal provider attempts cannot be edited/deleted;
7. claims cannot be updated/deleted after insert;
8. model cannot persist unknown claim type;
9. JSON typed schema rejects extra/private keys;
10. evidence terminal state is one-way;
11. `MATCHED` evidence requires valid exact offsets;
12. assessment is unique per claim/policy fingerprint and append-only;
13. resolution membership uses FK rows, not unvalidated JSON IDs;
14. conflict review cannot delete losing claims;
15. graph materialization references an accepted resolution;
16. stale target fingerprint blocks materialization;
17. no graph fact is committed without canonical `FieldEvidence` when policy requires evidence;
18. candidate snapshot promotion preserves exact content hash/text.

## Family-resolver proof cases

### Scalar

- same scholarship/provider current-cycle identity value from two accepted sources -> corroborated;
- same scope/current authority conflicting scalar -> review.

### Temporal

- global 1 June vs embassy Malaysia 15 May -> different scopes, no conflict;
- date-only 20 May remains date-only;
- two same-scope current provider deadlines with different dates -> conflict;
- previous-cycle deadline does not conflict with current-cycle deadline.

### Set membership

- Bachelor + Master + PhD coexist as three supported levels;
- one page omitting PhD does not prove PhD absent;
- explicit `PhD not eligible` can create an exclusion/negative claim when the typed policy supports it.

### Funding

- monthly CNY 3,000 != annual CNY 3,000;
- global provider stipend + institution local top-up coexist at correct scopes;
- institution page cannot redefine global funding without authority.

### Eligibility

- programme IELTS 7.0 can override/increase a broader IELTS 6.5 requirement at programme scope when authority is valid;
- conflicting same-scope eligibility predicates route to review;
- descriptive/typical wording does not become a mandatory eligibility predicate.

### Ordered steps

- two distinct steps coexist;
- exact duplicate steps corroborate/dedupe;
- ordering changes are preserved as workflow/version data rather than treated as arbitrary text conflict.

## Consequences

### Positive

- one auditable PR6 substrate serves initial acquisition and refresh;
- immutable source assertions are separated from mutable workflow state;
- policy changes can be replayed without rewriting history;
- retry/cost/provider reliability remains auditable;
- evidence can express value + scope + applicability instead of one ambiguous snippet;
- domain-specific conflict semantics are explicit;
- conflict membership and materialization history have real relational integrity;
- no generic model JSON can mutate arbitrary graph fields.

### Cost

- PR6 requires more normalized tables than a flat staging payload;
- typed resolver/materializer families require more engineering/tests;
- policy replay creates additional assessment/resolution history rows;
- eligibility and collection semantics cannot be solved by one generic comparator.

These costs are accepted because the alternative would create an opaque mutable staging database whose decisions could not be reproduced or trusted at scale.
