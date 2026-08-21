# ADR 0015: Keep source extraction/claims snapshot-owned and bind them to resolution bundles through explicit membership

- Status: Accepted correction before PR6 persistence implementation
- Date: 2026-08-19
- Applies to: PR6 v2 source extraction reuse, immutable claims/evidence, evidence bundles, source authority context, claim assessment, resolver inputs, and persistence schema
- Supersedes in part: ADR 0013 sections 8, 17 and the direct bundle ownership implied by their recommended claim/assessment fields; ADR 0014 table dependency list is refined by this ADR
- Related: ADR 0012, ADR 0013, ADR 0014

## Context

ADR 0013 correctly requires one logical extraction artifact for one immutable source snapshot + complete extraction contract and explicitly permits reuse of a successful extraction without another model request.

It also provisionally placed these columns on every field claim:

```text
bundle_id
bundle_source_id
source_extraction_id
```

and recommended:

```text
UNIQUE(source_extraction_id, ordinal)
```

Those requirements conflict when the same successful extraction must participate in more than one evidence bundle.

Example:

```text
canonical SourceSnapshot S1
        |
        v
SourceExtraction E1
        |
        +-- claim C1: deadline = 20 May
        +-- claim C2: stipend = JPY ...
```

Later workflows may need the same exact E1/C1/C2 in different bounded resolution units:

```text
Bundle B1: deadline freshness objective
Bundle B2: funding completeness objective
Bundle B3: policy replay under new authority rules
```

If C1 belongs directly to B1, then B2 has only bad choices:

1. insert another C1 for E1 and violate `UNIQUE(source_extraction_id, ordinal)`;
2. duplicate E1 and lose logical extraction reuse/idempotency;
3. point B2 assessments at a claim owned by B1 and make bundle/source authority context implicit/non-relational.

A second issue follows from authority context. `CatalogueEvidenceBundleSource` freezes the officiality/authority policy context used for a particular bounded resolution. The same immutable source assertion may legitimately be assessed under different bundle objectives/policy versions. Therefore assessment is not merely a function of `claim_id`; it is a function of **claim membership in a bundle + that bundle's frozen source context + resolver policy**.

The persistence model must represent those facts directly.

## Decision

### 1. `CatalogueSourceExtraction` is snapshot-owned, not bundle-owned

A logical extraction artifact belongs to exactly one immutable source snapshot and one complete extraction contract.

It references exactly one of:

```text
candidate_source_snapshot_id
source_snapshot_id
```

with an XOR constraint.

It does **not** contain `bundle_id` or `bundle_source_id`.

Its identity remains conceptually:

```text
immutable snapshot
+ target context hash
+ claim-family plan hash
+ schema version
+ instruction version
+ prompt hash
+ provider/model
+ complete contract fingerprint
```

A successful extraction can therefore be reused across bounded orchestration/resolution bundles without another provider call.

### 2. `CatalogueFieldClaim` is extraction-owned, not bundle-owned

A field claim is one immutable source assertion emitted by one logical extraction.

Recommended fields are refined to:

```text
id UUID PK
source_extraction_id UUID NOT NULL
ordinal int NOT NULL
claim_type varchar(64) NOT NULL
source_subject_json JSON NULL
scope_hint_snapshot JSON NOT NULL
source_value_json JSON NULL
source_value_hash varchar(64) NULL
value_state varchar(32) NOT NULL
claim_fingerprint varchar(64) NOT NULL
created_at timestamptz NOT NULL
```

Required uniqueness:

```text
UNIQUE(source_extraction_id, ordinal)
UNIQUE(source_extraction_id, claim_fingerprint)
```

There is intentionally **no** bundle-level uniqueness on claim fingerprint.

Claims from two different source extractions may be semantically identical and must both survive for corroboration.

### 3. Claim evidence remains claim/snapshot-owned

`CatalogueClaimEvidence` references `claim_id` only; the source snapshot is obtained through:

```text
claim
 -> source extraction
 -> immutable source snapshot
```

Evidence validation therefore stays reusable with the extraction artifact.

The exact same verified source bytes/excerpt do not need to be re-located because a new resolution bundle wants to consume the claim.

### 4. Add `CatalogueEvidenceBundleClaim` as the explicit reuse/binding layer

Introduce:

```text
catalogue_evidence_bundle_claims
```

Recommended fields:

```text
id UUID PK
bundle_id UUID NOT NULL
bundle_source_id UUID NOT NULL
claim_id UUID NOT NULL
created_at timestamptz NOT NULL
```

Meaning:

> this bounded evidence bundle consumes this immutable source claim under this frozen bundle-source authority/officiality context.

Required uniqueness:

```text
UNIQUE(bundle_id, claim_id)
```

A claim can therefore participate in many different bundles while appearing at most once in a particular bundle.

### 5. Enforce that `bundle_source_id` belongs to the same bundle

Do not rely only on application convention.

`catalogue_evidence_bundle_sources` must expose a composite candidate key equivalent to:

```text
UNIQUE(id, bundle_id)
```

and `catalogue_evidence_bundle_claims` uses a composite FK:

```text
(bundle_source_id, bundle_id)
 -> catalogue_evidence_bundle_sources(id, bundle_id)
 ON DELETE RESTRICT
```

This prevents accidentally binding a claim in bundle B1 to source context owned by bundle B2.

### 6. Enforce snapshot identity between claim extraction and bundle source in the service boundary

The database can prove bundle/source membership, but portable SQL constraints cannot cheaply prove the cross-table XOR identity:

```text
claim.source_extraction.snapshot
==
bundle_source.snapshot
```

The bundle-claim binding service must therefore load both immutable identities and reject mismatches before insert.

Required deterministic invariant:

```text
candidate extraction:
  extraction.candidate_source_snapshot_id
  == bundle_source.candidate_source_snapshot_id

canonical extraction:
  extraction.source_snapshot_id
  == bundle_source.source_snapshot_id
```

Cross-kind binding is always invalid.

This invariant gets dedicated SQLite/service tests and PostgreSQL integration tests.

### 7. `CatalogueClaimAssessment` belongs to bundle-claim membership, not naked claim ID

Refine the assessment FK from:

```text
claim_id
```

to:

```text
bundle_claim_id
 -> catalogue_evidence_bundle_claims.id
 ON DELETE RESTRICT
```

Required uniqueness becomes:

```text
UNIQUE(bundle_claim_id, policy_fingerprint)
```

This is necessary because the same immutable source assertion may be interpreted differently under:

- another acquisition/refresh objective;
- another frozen source-authority context;
- another graph target state;
- another resolver/authority/cycle policy version.

The immutable claim does not change. A new bundle membership/assessment records the new interpretation.

### 8. Assessment scope IDs remain system-resolved outputs

The assessment can still store resolved system identifiers:

```text
candidate_id
scholarship_id
cycle_id
track_id
institution_id
programme_id
canonical_field_path
collection_key
normalized_value_json/hash
claim_key_hash
```

These are resolver outputs, never model output.

The assessment obtains source claim/evidence through `bundle_claim_id` and source authority context through:

```text
bundle_claim
 -> bundle_source
```

### 9. Resolution membership continues to reference assessments

No change to the principle:

```text
CatalogueClaimResolutionMember
 -> CatalogueClaimAssessment
```

A resolution is therefore reproducible as:

```text
bundle
 + frozen bundle-source contexts
 + reusable immutable claims/evidence
 + bundle-specific assessments
 + deterministic resolution policy
```

### 10. Provider retries remain extraction-owned and reusable

`CatalogueSourceExtractionAttempt` continues to reference the logical extraction.

One model call/retry history can support multiple later bundles:

```text
attempt 1 -> RATE_LIMITED
attempt 2 -> SUCCEEDED
                |
                v
             E1/C1/C2
              /  |  \
            B1   B2   B3
```

The platform does not pay again merely because the same reviewed bytes are reconsidered for another bounded objective.

### 11. Reuse does not imply authority carry-forward

Extraction/claim reuse means only:

> the exact source bytes produced these exact validated source assertions under this extraction contract.

It does **not** mean:

- source officiality is forever unchanged;
- the source is authoritative for every bundle objective;
- claim applicability/current-cycle status is unchanged;
- the claim remains effective under a new policy.

Those properties are bundle-specific and are re-evaluated/frozen in `CatalogueEvidenceBundleSource` + `CatalogueClaimAssessment`.

### 12. Evidence validation may be reused; applicability/authority assessment may not be blindly reused

If the snapshot is byte-identical and claim evidence was deterministically matched, exact evidence location remains valid.

However a new bundle must still perform the policy-dependent stages required by its objective:

```text
scope
+ authority
+ cycle/applicability
+ canonicalization policy
+ target-state fingerprint
```

This distinction is central to cheap incremental maintenance:

```text
same bytes -> no new model call / no new excerpt search
new policy/objective -> new assessment/resolution as required
```

### 13. Refined first-slice dependency order

The persistence dependency order becomes conceptually:

```text
1. catalogue_candidate_source_snapshots
2. catalogue_evidence_bundles
3. catalogue_evidence_bundle_sources
4. catalogue_source_extractions
5. catalogue_source_extraction_attempts
6. catalogue_field_claims
7. catalogue_claim_evidence
8. catalogue_evidence_bundle_claims
9. catalogue_claim_assessments
10. catalogue_claim_resolutions
11. catalogue_claim_resolution_members
12. catalogue_conflict_sets
13. catalogue_conflict_claims
14. catalogue_conflict_review_decisions
15. catalogue_snapshot_promotions
16. catalogue_graph_materializations
```

ADR 0014's migration-order gate remains unchanged: do not create a PR6 Alembic revision until the actual integrated upstream head is known.

## Required proof cases

Before persistence is considered ready, prove:

1. one successful extraction can be linked to two separate bundles without another extraction/provider attempt;
2. the same claim ID can participate in B1 and B2 through two bundle-claim rows;
3. B1 and B2 can have different bundle-source authority-policy versions;
4. B1 and B2 assessments are independent and unique by `(bundle_claim_id, policy_fingerprint)`;
5. a bundle claim cannot reference a bundle source from another bundle;
6. a candidate-snapshot claim cannot be bound to a canonical-snapshot bundle source;
7. a claim from snapshot S1 cannot be bound to bundle source S2;
8. two different source extractions can persist the same semantic claim for corroboration;
9. exact matched evidence is reused without another locator/model call when bytes are identical;
10. policy replay creates new assessment/resolution history without rewriting claim/evidence rows.

## Consequences

### Positive

- logical extraction reuse is real rather than aspirational;
- model cost is tied to changed bytes/contracts, not the number of orchestration bundles;
- claims/evidence represent what one immutable source said, independent of later workflow;
- bundle authority/applicability context remains explicit and reproducible;
- policy replay becomes clean: reuse source assertions, append new assessments/resolutions;
- cross-source corroboration and multi-objective reuse both work without duplicate claims.

### Cost

- one additional normalized membership table is required;
- assessment joins traverse bundle claim -> claim and bundle source;
- snapshot-equality binding needs an explicit service invariant because portable cross-table SQL checks cannot express it cleanly;
- ADR 0013's provisional direct bundle ownership for claims/assessments must not be implemented literally.

These costs are accepted because the alternative either wastes model calls or makes bundle authority context implicit, both of which violate PR6's engineering goals.