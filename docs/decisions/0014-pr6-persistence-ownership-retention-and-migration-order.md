# ADR 0014: Freeze PR6 persistence ownership, provenance retention, and migration ordering

- Status: Accepted for PR6 persistence implementation
- Date: 2026-08-19
- Applies to: PR6 evidence-ledger persistence, immutable candidate evidence, extraction attempts, field claims, assessments, resolutions, conflicts, promotions, materialization audit, compatibility projections, and Alembic integration
- Related: ADR 0008, ADR 0009, ADR 0010, ADR 0011, ADR 0012, ADR 0013

## Context

PR6 now has a deterministic typed claim contract and a pure resolver core. The remaining highest-risk boundary is persistence.

The repository currently contains several generations of catalogue/evidence storage:

```text
legacy Opportunity scalar/JSON fields
legacy Source + SourceExcerpt
v1 CatalogueCandidate + CatalogueExtractionAttempt JSON staging
canonical SourceSnapshot + FieldEvidence
scoped Scholarship Intelligence Graph facts
PR6 typed claim/resolution architecture
```

These layers cannot all become independent truth producers.

The canonical publication truth remains the reviewed Scholarship Intelligence Graph backed by canonical source evidence. PR6 staging records are durable evidence, interpretation, resolution, and audit history; they are not a second catalogue.

The current database head on the PR6 foundation branch is `20260817_0040_relationship_classification`. PR5 runtime discovery persistence is architecturally intended to integrate before PR6 persistence. Creating an independent PR6 revision from 0040 now would create an avoidable Alembic branch-head collision.

ADR 0013 intentionally left several exact foreign-key and retention decisions open pending inspection of the repository's existing schema. That inspection also identified one provisional uniqueness recommendation that must be narrowed: identical semantic claims from two different official sources must coexist so the resolver can prove corroboration.

This ADR freezes the database contract before any PR6 Alembic migration is created.

## Decision

### 1. Do not create a PR6 Alembic revision from the current 0040 head

PR6 persistence must be based on the **actual integrated Alembic head** after the required upstream PR5 runtime schema has landed and the PR6 branch has been rebased or recreated from that integrated state.

Required sequence:

```text
current integrated head
        |
        v
PR5 runtime discovery persistence
        |
        v
verify exactly one Alembic head
        |
        v
rebase/recreate PR6 runtime branch
        |
        v
read actual Alembic head
        |
        v
create next PR6 revision
```

The next PR6 revision is expected to be `0042` only if PR5 is exactly `0041`. That number is **not reserved as truth** and must not be hard-coded before integration.

Release gate:

```text
alembic heads -> exactly one head
```

A multiple-head migration graph is a failed integration gate, not something to hide with a merge revision created after the fact unless the branch topology genuinely requires one and is explicitly reviewed.

### 2. The first PR6 persistence migration is additive and staging-only

The first PR6 persistence slice may create the new ledger/staging tables and supporting indexes/constraints required by ADR 0012/0013.

It must **not** in the same migration:

- destructively alter `opportunities`;
- rewrite existing `sources`;
- rewrite existing `source_snapshots`;
- rewrite existing `field_evidence`;
- rewrite existing scoped graph facts;
- backfill PR6 claims from old flat JSON as if historical extraction had PR6 semantics;
- change existing publication state;
- enable automatic refresh materialization;
- enable automatic publication.

Existing v1 catalogue history remains readable and unchanged.

This keeps the first persistence proof focused on the new provenance substrate rather than combining storage, migration, graph mutation, and compatibility conversion into one blast radius.

### 3. PR6 ledger models belong to catalogue ingestion, not the canonical opportunities domain

New PR6 staging/audit models belong under the catalogue-ingestion module, conceptually in a dedicated file such as:

```text
app/modules/catalogue_ingestion/evidence_ledger_models.py
```

or an equivalently explicit PR6 persistence module.

Canonical graph/source models remain owned by `app/modules/opportunities/`.

This boundary means:

```text
catalogue ingestion owns:
  candidate evidence
  source extraction
  claims
  deterministic assessments
  resolutions
  conflicts
  promotion/materialization audit

opportunities owns:
  canonical Source
  canonical SourceSnapshot
  canonical FieldEvidence
  Scholarship Intelligence Graph entities/facts
  publication-facing projections
```

All new ORM models must be imported through `app/db/models.py` so Alembic sees complete metadata.

### 4. Evidence-bearing staging history must not inherit v1 cascade-deletion semantics

V1 ingestion intentionally uses broad cascade deletion for run/candidate/source staging.

PR6 evidence is different: once exact source bytes or downstream claims depend on a row, routine parent deletion must not erase provenance.

The first immutable boundary is:

```text
catalogue_candidate_source_snapshots.candidate_source_id
  -> catalogue_candidate_sources.id
  ON DELETE RESTRICT
```

Consequences are intentional:

- a v1 run/candidate with no PR6 evidence can retain historical deletion behavior;
- once a candidate source has immutable PR6 evidence, deleting the candidate/run through cascades is blocked;
- operational cleanup becomes archive/retention-policy work, not silent evidence destruction.

### 5. Freeze exact target-retention semantics for evidence bundles

`catalogue_evidence_bundles` references exactly one target:

```text
candidate_id XOR opportunity_id
```

Both target references use `ON DELETE RESTRICT` once a bundle exists.

Reason:

- bundle target identity is part of the explanation for why evidence was acquired/resolved;
- deleting the target while retaining the bundle would weaken reproducibility;
- cascading bundle deletion would destroy provenance.

The bundle also stores immutable typed target/objective snapshots, but those snapshots are audit context and do not justify making relational target identity disposable.

Canonical scholarships should normally be archived/superseded, not physically deleted after evidence-bearing workflow exists.

### 6. Bundle-source context is immutable and retained

`catalogue_evidence_bundle_sources` references:

```text
bundle_id -> catalogue_evidence_bundles.id ON DELETE RESTRICT

exactly one of:
  candidate_source_snapshot_id -> catalogue_candidate_source_snapshots.id ON DELETE RESTRICT
  source_snapshot_id           -> source_snapshots.id ON DELETE RESTRICT
```

The XOR constraint is mandatory.

The row freezes the source authority/officiality context used for one resolution, including a typed authority-scope snapshot and policy version.

Later source-registry edits cannot rewrite historical authority reasoning.

### 7. Logical extraction artifacts and provider attempts have different retention/state semantics

`catalogue_source_extractions` references its immutable source snapshot/bundle-source context with `ON DELETE RESTRICT`.

The logical extraction row may transition only through its explicit workflow until terminal:

```text
PENDING -> RUNNING -> SUCCEEDED | FAILED
```

After terminal state it is immutable.

`catalogue_source_extraction_attempts` references extraction with `ON DELETE RESTRICT`.

Each provider request is inserted **before network I/O** and has one terminal result such as:

```text
SUCCEEDED
RATE_LIMITED
TIMEOUT
PROVIDER_FAILED
SCHEMA_FAILED
ABANDONED
```

Retries create new rows.

A sequence such as:

```text
attempt 1: RATE_LIMITED
attempt 2: SUCCEEDED
```

must remain queryable forever as two attempts.

### 8. Claims are retained source assertions, not mutable staging rows

`catalogue_field_claims` references all of the provenance needed to explain the assertion:

```text
bundle_id            -> bundle RESTRICT
bundle_source_id     -> bundle source RESTRICT
source_extraction_id -> source extraction RESTRICT
```

After insertion, a claim cannot be updated or deleted.

If extraction/canonicalization changes, create a new logical extraction/claim set under a new contract. Do not rewrite history.

### 9. Correct ADR 0013 claim uniqueness: dedupe within a source extraction, not across the bundle

ADR 0013 provisionally recommended:

```text
UNIQUE(bundle_id, claim_fingerprint)
```

That is too strong and is superseded by this ADR.

Two independent official sources may legitimately emit the same semantic claim:

```text
Source A -> deadline = 20 May 2027
Source B -> deadline = 20 May 2027
```

Both claims must persist so the resolver can return `CORROBORATED` and retain both evidence chains.

Required uniqueness:

```text
UNIQUE(source_extraction_id, ordinal)
```

Recommended additional duplicate guard:

```text
UNIQUE(source_extraction_id, claim_fingerprint)
```

if one extraction contract must never emit the same logical assertion twice.

Do **not** create a uniqueness constraint on `(bundle_id, claim_fingerprint)`.

Cross-source equivalence is resolver input, not a database duplicate.

### 10. Claim evidence is append-only after one-way validation

`catalogue_claim_evidence` references its claim with `ON DELETE RESTRICT`.

Required uniqueness:

```text
UNIQUE(claim_id, ordinal)
```

Workflow:

```text
PENDING
  -> MATCHED
  -> NOT_FOUND
  -> AMBIGUOUS
  -> INVALID
```

This is a one-way transition.

After any terminal state, the row cannot be edited/deleted.

For `MATCHED`:

```text
excerpt_start IS NOT NULL
excerpt_end IS NOT NULL
excerpt_start >= 0
excerpt_end >= excerpt_start
snapshot_text[excerpt_start:excerpt_end] == excerpt
```

The exact substring equality remains an application invariant because cross-table text slicing is not portable as a simple SQL check. Database constraints still enforce all locally expressible offset/state shape invariants.

### 11. Assessments are immutable interpretations under a complete policy fingerprint

`catalogue_claim_assessments` references:

```text
claim_id -> catalogue_field_claims.id ON DELETE RESTRICT
supersedes_assessment_id -> catalogue_claim_assessments.id ON DELETE RESTRICT
```

Required uniqueness:

```text
UNIQUE(claim_id, policy_fingerprint)
```

Assessment rows are append-only.

Changing scope/authority/canonicalization/cycle policy creates a new assessment. It does not mutate the old one.

A supersession link is history, not permission to delete the earlier assessment.

### 12. Resolutions and membership are relational, append-only history

`catalogue_claim_resolutions` references:

```text
bundle_id -> catalogue_evidence_bundles.id ON DELETE RESTRICT
supersedes_resolution_id -> catalogue_claim_resolutions.id ON DELETE RESTRICT
```

Required uniqueness is scoped to a deterministic resolution input, conceptually:

```text
UNIQUE(bundle_id, claim_key_hash, policy_fingerprint)
```

If a future family resolver needs more than one resolution artifact for one claim key, the schema must add an explicit typed discriminator rather than weakening uniqueness ad hoc.

`catalogue_claim_resolution_members` references:

```text
resolution_id       -> resolution RESTRICT
claim_assessment_id -> assessment RESTRICT
```

with:

```text
UNIQUE(resolution_id, claim_assessment_id)
```

Membership is never stored only as JSON claim IDs.

### 13. Conflict membership and review history are normalized and retained

`catalogue_conflict_sets` references its triggering resolution with `ON DELETE RESTRICT`.

One resolution can create at most one current conflict set in the initial implementation:

```text
UNIQUE(resolution_id)
```

If later policy needs multiple conflict dimensions for one resolution, an explicit conflict-dimension key must be introduced.

`catalogue_conflict_claims` references conflict + assessment with `ON DELETE RESTRICT` and:

```text
UNIQUE(conflict_set_id, claim_assessment_id)
```

`catalogue_conflict_review_decisions` is append-only and references its prior decision with `ON DELETE RESTRICT`.

Human review never deletes losing claims/evidence.

### 14. Reviewer identity must not force mutation of immutable review decisions

A conventional reviewer FK with `ON DELETE SET NULL` would mutate historical review evidence when a user account is erased.

The repository already avoids that pattern for append-only audit history.

PR6 review decisions therefore store the reviewer UUID as an immutable identity snapshot rather than relying on a mutable `SET NULL` foreign key.

Initial implementation:

```text
reviewer_id UUID NOT NULL
reviewer_identity_snapshot JSON NOT NULL
```

`reviewer_id` is historical data, not a cascading account relationship. It does not require a database FK whose account-deletion behavior could mutate the decision row.

The snapshot is a bounded admin/public identity representation only; it must not contain secrets or unrelated personal data.

If privacy/account-erasure policy later requires pseudonymization, that must be designed as an explicit compliance mechanism rather than hidden FK side effects.

### 15. Candidate-to-canonical snapshot promotion is immutable lineage

`catalogue_snapshot_promotions` references:

```text
candidate_source_snapshot_id -> candidate snapshot RESTRICT
source_snapshot_id           -> canonical SourceSnapshot RESTRICT
candidate_id                 -> candidate RESTRICT
opportunity_id               -> Opportunity RESTRICT
```

Required uniqueness:

```text
UNIQUE(candidate_source_snapshot_id, source_snapshot_id)
```

Promotion is append-only.

Before insertion:

```text
candidate.content_hash == canonical.content_hash
candidate.normalized_text == canonical.normalized_text
```

must hold.

A promotion row proves which exact pre-canonical bytes crossed the trust boundary.

### 16. Graph materialization audit is immutable and idempotent

`catalogue_graph_materializations` references its authorizing resolution with `ON DELETE RESTRICT`.

The target graph entity is polymorphic (`entity_type`, `entity_id`), so the initial table does not pretend that one generic FK can enforce every target table.

The row stores:

- resolution ID;
- materializer version;
- operation;
- target entity type/ID;
- field path;
- target-state fingerprint used before write;
- resulting target-state fingerprint;
- previous materialization ID where applicable;
- creation time.

A materialization retry must not double-apply the same authorized mutation.

Use a deterministic idempotency key/unique constraint derived from the resolution + materializer version + intended operation/target identity. The exact serialized key is created by the typed materializer, never supplied by model output.

### 17. Database immutability is required in PostgreSQL; ORM guards alone are insufficient

The repository currently uses an append-only PostgreSQL trigger pattern for `audit_logs`. PR6 adopts the same principle.

For PostgreSQL, immutable/terminal PR6 history must be protected by database triggers in addition to ORM/service guards.

Rows immutable immediately after insert include:

- candidate source snapshots;
- bundle-source context;
- claims;
- claim assessments;
- claim resolutions;
- resolution members;
- conflict membership;
- conflict review decisions;
- snapshot promotions;
- graph materialization audit rows.

Rows that are mutable only until terminal include:

- source extraction;
- provider attempt;
- claim evidence.

Workflow rows with explicit controlled mutable state include:

- evidence bundle orchestration status;
- conflict-set workflow status.

Their transition methods must be enumerated and tested. A generic ORM update is not the state machine.

SQLite remains supported for portable tests with application/ORM immutability guards, matching the repository's established portability pattern. PostgreSQL is authoritative for database-level trigger proof.

### 18. Do not harden existing canonical SourceSnapshot in the first PR6 ledger migration

Current `SourceSnapshot` already has `ON DELETE RESTRICT` and ORM mutation guards, but not the same PostgreSQL append-only trigger protection.

That should be hardened in a dedicated follow-up migration **after** compatibility tests prove no current maintenance/admin path depends on direct SourceSnapshot mutation.

Do not combine that existing-table behavior change with creation of the first PR6 ledger schema.

This is a blast-radius decision, not acceptance of mutable provenance.

### 19. JSON columns are frozen typed snapshots, not relational identity or arbitrary dumping grounds

Every PR6 JSON column defined by ADR 0012/0013 must have a dedicated strict schema with:

- `extra=forbid`;
- bounded lengths/counts;
- explicit enums;
- no applicant/private context unless a future ADR explicitly allows it;
- canonical deterministic serialization before hashing.

JSON may snapshot:

- target identity context;
- objective scope;
- source authority context;
- typed source value;
- normalized resolved value;
- bounded reason codes.

JSON must **not** replace relational membership where rows have stable identity.

For example:

```text
resolution members -> join table, not JSON IDs
conflict members   -> join table, not JSON IDs
```

### 20. Legacy Opportunity fields are compatibility projections, never a second PR6 truth source

The existing `Opportunity` row still contains legacy/global fields for deadlines, funding, eligibility, required documents, application URLs, and catalogue-window filtering.

PR6 does not read those fields as authoritative truth when the reviewed graph/evidence layer is available.

They are compatibility/query projections.

Only one explicit projection service may write them from accepted canonical graph/resolution state.

The first PR6 persistence slice does **not** write these compatibility fields.

Likewise:

```text
CatalogueCandidate.proposed_payload
CatalogueCandidate.conflicts
```

remain v1/admin compatibility history. PR6 normalized claims/resolutions do not use them as source of truth.

### 21. Direct legacy source/excerpt links remain compatibility provenance, not PR6 canonical evidence

Existing `EligibilityRule` can point directly to:

```text
Source
SourceExcerpt
```

with `SET NULL` behavior.

PR6 canonical evidence remains:

```text
SourceSnapshot -> FieldEvidence -> canonical fact
```

The first PR6 persistence slice does not destructively rewrite legacy eligibility rows or source excerpts.

A later compatibility/materialization slice may populate legacy links for UI continuity only if one producer owns that projection and canonical FieldEvidence remains authoritative.

### 22. Existing FieldEvidence polymorphism requires a refresh-materialization gate

`FieldEvidence` currently stores:

```text
entity_type
entity_id
field_path
source_snapshot_id
```

`entity_id` is intentionally polymorphic and therefore has no database FK to every possible graph fact table.

At the same time, several scoped graph fact tables use `ON DELETE CASCADE` from parent graph entities and can be updated/versioned independently.

Therefore PR6 must not assume that an existing FieldEvidence row automatically proves that a mutated/deleted/recreated graph fact is still the same current fact.

Before PR6 enables automatic canonical refresh UPDATE/DELETE operations, a later persistence/materialization slice must prove a fact/evidence lineage policy that answers:

- how an old fact version is superseded;
- how historical FieldEvidence remains historical;
- how current effective evidence is selected;
- how a recreated fact cannot accidentally inherit old evidence by identifier/path assumptions;
- how completeness consumes current evidence only.

Until that gate passes:

```text
automatic destructive refresh materialization = disabled
```

This does not prevent PR6 from persisting candidate evidence/claims/resolutions. It prevents us from pretending that an unresolved canonical-lineage question is safe because the resolver itself is correct.

### 23. Physical deletion is not the normal lifecycle for evidence-bearing catalogue records

Once PR6 provenance exists, operational lifecycle should use states such as:

```text
archived
superseded
rejected
blocked
stale
```

rather than physical deletion.

Database `RESTRICT` errors are expected safety behavior when an operator attempts to erase evidence-bearing parents.

A future retention/privacy purge feature must enumerate the exact legal/product conditions under which evidence can be cryptographically/physically removed. It must not be implemented as broad ORM cascade behavior.

### 24. Canonical graph mutation remains behind a separate proof gate

The first PR6 persistence release proves:

```text
immutable snapshot
 -> extraction history
 -> typed claims
 -> exact evidence validation
 -> append-only assessments
 -> deterministic resolutions
 -> conflict history
```

It does **not** by itself prove:

- canonical graph materialization;
- compatibility projections;
- completeness recomputation;
- publication;
- recurring autonomous refresh.

Those are later gates.

`APP_CATALOGUE_AUTO_PUBLISH_ENABLED=false` remains mandatory.

### 25. Migration downgrade must remove only PR6-owned additive schema

The first PR6 migration downgrade may drop the new PR6-owned tables/triggers/indexes in dependency-safe reverse order.

It must not attempt to reconstruct or rewrite pre-existing canonical data because the upgrade did not mutate it.

This keeps downgrade semantics honest:

```text
pre-PR6 database
 -> PR6 additive upgrade
 -> PR6 downgrade
 == pre-PR6 canonical tables/data
```

Any later migration that changes existing canonical tables must define its own explicit downgrade/data-preservation policy.

## Initial table dependency order

The first persistence implementation should create tables in a dependency order equivalent to:

```text
1. catalogue_candidate_source_snapshots
2. catalogue_evidence_bundles
3. catalogue_evidence_bundle_sources
4. catalogue_source_extractions
5. catalogue_source_extraction_attempts
6. catalogue_field_claims
7. catalogue_claim_evidence
8. catalogue_claim_assessments
9. catalogue_claim_resolutions
10. catalogue_claim_resolution_members
11. catalogue_conflict_sets
12. catalogue_conflict_claims
13. catalogue_conflict_review_decisions
14. catalogue_snapshot_promotions
15. catalogue_graph_materializations
```

Exact creation order may vary for self-referential supersession constraints, but no table may weaken retention merely to make DDL ordering convenient.

Self-referential FKs may be created after table creation where required.

## Required database constraints

At minimum prove:

1. bundle target is candidate XOR opportunity;
2. bundle source is candidate snapshot XOR canonical snapshot;
3. source extraction snapshot/context identity is unambiguous;
4. source snapshot byte/count/status constraints are enforced;
5. duplicate candidate snapshot hash for same candidate source is rejected;
6. same claim emitted twice in one extraction is rejected;
7. identical semantic claim from two different source extractions in one bundle is allowed;
8. evidence ordinal is unique per claim;
9. matched evidence has non-null valid offsets;
10. assessment is unique per claim + policy fingerprint;
11. resolution is unique per bundle + claim key + policy fingerprint;
12. resolution membership pair is unique;
13. conflict set/membership pair is unique;
14. provider attempt number is unique per extraction;
15. materialization idempotency key is unique;
16. provenance parents cannot be cascade-deleted after immutable children exist.

## Required migration/integration tests

Before calling PR6 persistence migration-ready, prove all of the following.

### Alembic topology

```text
alembic heads == exactly one
```

Test on the actual integrated upstream head, not an assumed revision number.

### Fresh database

- SQLite fresh upgrade to head succeeds;
- PostgreSQL fresh upgrade to head succeeds;
- metadata imports include every PR6 table;
- no unexpected autogenerate drift for the PR6 schema.

### Existing database upgrade

Starting from the real pre-PR6 integrated head:

- upgrade succeeds;
- existing Opportunity rows are byte/field-equivalent for all unaffected columns;
- existing Source/SourceSnapshot/FieldEvidence/scoped facts remain unchanged;
- v1 ingestion history remains readable;
- v1 ingestion tests remain green.

### Downgrade

- PR6 head -> previous integrated head succeeds where supported;
- PR6-owned tables disappear;
- pre-existing canonical tables/data remain unchanged.

### Retention

- a candidate/run without PR6 evidence follows historical deletion semantics;
- once a candidate source snapshot exists, parent cascade deletion is blocked;
- bundle/source/claim/resolution provenance cannot be deleted through ordinary parent cleanup.

### PostgreSQL immutability

Direct SQL `UPDATE`/`DELETE` against immutable PR6 rows is rejected.

Direct SQL invalid state mutation of terminal attempt/evidence rows is rejected according to the trigger/state contract.

### Corroboration

- Source A claim X persists;
- Source B claim X persists;
- both participate in one resolution;
- resolution can become `CORROBORATED`;
- database uniqueness does not collapse one source into the other.

### Retry history

Persist:

```text
attempt 1 -> RATE_LIMITED
attempt 2 -> SUCCEEDED
```

and prove both remain immutable/queryable.

### No publication side effect

Creating/resolving PR6 ledger rows cannot transition an Opportunity to ACTIVE/PUBLISHED and cannot invoke an auto-publish path.

## Release gates

The PR6 persistence foundation is not complete until all gates below are true:

```text
[ ] branch rebased onto actual integrated PR5/runtime head
[ ] one Alembic head
[ ] additive migration only
[ ] ORM metadata parity
[ ] SQLite migration proof
[ ] PostgreSQL migration proof
[ ] PostgreSQL immutable-history trigger proof
[ ] retention/delete-behavior proof
[ ] cross-source corroborating duplicate proof
[ ] retry-history proof
[ ] v1 ingestion regression proof
[ ] canonical tables unchanged by first slice
[ ] no automatic materialization
[ ] auto-publish remains false
```

## Explicit non-goals of the first persistence slice

Do not include:

- PR5 migration integration by guesswork;
- Azure provisioning;
- live Azure/OpenAI calls;
- automatic source discovery;
- canonical refresh mutation;
- graph fact deletion/replacement;
- compatibility projection rewrites;
- completeness-engine persistence;
- automatic publication;
- bulk migration of legacy flat catalogue data into PR6 claims;
- arbitrary `OTHER` typed claim escape hatches.

## Consequences

### Positive

- PR6 can add durable provenance without destabilizing the existing catalogue;
- identical claims from independent sources can genuinely corroborate;
- evidence-bearing candidate history cannot disappear through old cascade paths;
- policy changes remain replayable because claims/assessments/resolutions are retained;
- database-level PostgreSQL protection guards against maintenance scripts bypassing ORM rules;
- migration ordering avoids an artificial PR5/PR6 Alembic branch collision;
- canonical graph mutation is delayed until its evidence-version lineage is actually proven.

### Cost

- some old cleanup operations will fail once PR6 evidence exists and must use archive semantics;
- the schema contains more normalized history tables;
- PostgreSQL trigger tests add implementation work;
- canonical refresh materialization needs a later dedicated lineage design/proof;
- PR6 cannot simply reuse v1 cascade/delete behavior or flat `Opportunity` projections.

These costs are accepted. The persistence layer exists to preserve truth and explainability over years of catalogue refreshes; convenience deletion and premature graph writes are not more important than provenance.