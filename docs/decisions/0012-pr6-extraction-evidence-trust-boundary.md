# ADR 0012: Keep extraction source-local and cross the canonical graph boundary only through promoted evidence

- Status: Accepted for PR6 architecture
- Date: 2026-08-19
- Applies to: PR6 multi-source extraction, pre-publication evidence, exact provenance, graph materialization, refresh extraction, and legacy ingestion migration
- Related: ADR 0003, 0004, 0008, 0009, 0010, 0011

## Context

The current catalogue ingestion pipeline is deliberately conservative, but it is still organized around one root source producing one flat scholarship proposal:

```text
candidate
 -> one selected official source
 -> safe fetch / bounded crawl
 -> CatalogueExtractionOutput v1
 -> deterministic validation
 -> OpportunityCreate
 -> draft review workflow
```

The current extraction prompt already has good safety rules:

- use only supplied official source text;
- do not infer unsupported facts;
- require verbatim evidence for decision-critical values;
- report conflicts instead of silently resolving them.

The problem is architectural, not prompt quality.

`CatalogueExtractionOutput v1` is a single-source, flat scholarship object. It requires/assumes fields such as one provider, one country, one degree level, one opening/deadline pair, one funding summary, one application method, and a list of evidence snippets. The validator then turns that object directly into `OpportunityCreate`.

That works for simple single-page awards. It is not a safe substrate for MEXT, CSC, Chevening, Erasmus-style programme structures, embassy routes, institution-specific requirements, or incremental multi-source refresh.

The graph/evidence layer already contains stronger primitives:

- immutable canonical `SourceSnapshot`;
- exact-offset `FieldEvidence`;
- scoped deadlines/funding/documents/steps/eligibility;
- scholarship -> cycle -> track -> institution -> programme scope;
- deterministic inheritance for at least scoped deadlines.

However, canonical `SourceSnapshot` belongs to an approved/draft `Opportunity` source. A pre-publication candidate intentionally does not yet have a canonical scholarship identity. Creating a draft `Opportunity` merely to obtain a place to store evidence would let storage mechanics create identity too early. Conversely, keeping only a content hash/excerpt in candidate staging loses the exact source text needed for reproducible field evidence.

PR6 therefore needs an explicit trust-boundary bridge.

## Decision

### 1. PR6 remains per-source extraction; it never concatenates official pages

Every safe-fetched source is extracted independently.

```text
Source A snapshot -> extraction A -> claims A
Source B snapshot -> extraction B -> claims B
Source C snapshot -> extraction C -> claims C
                                  |
                                  v
                         deterministic resolver
```

Do not concatenate source text into one model prompt.

Do not ask a model to reconcile source A against source B.

Do not ask a model which official source is more trustworthy.

Multi-source intelligence is a deterministic post-extraction concern.

### 2. Preserve exact pre-publication source content in an immutable staging snapshot

Introduce:

```text
catalogue_candidate_source_snapshots
```

A staging snapshot is the exact normalized content that was used for candidate extraction before a canonical `Opportunity`/`Source` exists.

Recommended fields:

```text
id UUID PK
candidate_source_id UUID NOT NULL
fetched_at timestamptz NOT NULL
requested_url varchar(2048) NOT NULL
final_url varchar(2048) NOT NULL
http_status int NOT NULL
content_hash varchar(128) NOT NULL
normalized_text text NOT NULL
storage_reference varchar(2048) NULL
extraction_method varchar(64) NOT NULL
language_code varchar(16) NULL
byte_count int NOT NULL
character_count int NOT NULL
fetch_metadata JSON NOT NULL
created_at timestamptz NOT NULL
```

Constraints:

```text
UNIQUE(candidate_source_id, content_hash)
CHECK(http_status between 100 and 599)
CHECK(byte_count >= 0)
CHECK(character_count >= 0)
```

FK:

```text
candidate_source_id
 -> catalogue_candidate_sources.id
 -> ON DELETE RESTRICT
```

Once exact candidate evidence exists, routine cascade deletion must not silently erase it.

The staging snapshot is immutable after insert. PostgreSQL/application guards should mirror the existing `SourceSnapshot` immutability principle.

### 3. Staging snapshots are not canonical evidence

A `CatalogueCandidateSourceSnapshot` means:

> this exact safe-fetched content was evaluated while deciding whether/how to add information to the catalogue.

It does **not** mean:

- the scholarship exists independently;
- the source is publication-authoritative for every field;
- the candidate is approved;
- the claims extracted from it are true;
- the source is canonical graph evidence yet.

That distinction preserves the publication boundary.

### 4. Do not create a draft Opportunity merely to store candidate evidence

The current `stage_opportunity_for_review()` path creates canonical draft rows after flat validation. PR6 must not move this earlier just to gain access to `SourceSnapshot`.

For a new independent scholarship candidate:

```text
candidate source snapshots
 -> source-local claims
 -> deterministic scope/authority/value resolution
 -> identity/relationship review boundary
 -> create canonical draft Opportunity
 -> promote accepted exact evidence
```

For an already-existing scholarship enrichment/refresh:

```text
canonical SourceSnapshot
 -> source-local claims
 -> deterministic resolution
 -> controlled graph update/review
```

The same resolver semantics operate on both paths.

### 5. V1 flat extraction remains legacy; PR6 introduces a source-relative V2 contract

Do not keep expanding `CatalogueExtractionOutput v1` until it becomes a giant ambiguous object.

Introduce a versioned contract, conceptually:

```text
catalogue-source-extraction.v2
```

V2 is source-relative and target-bound. It returns zero or more typed claims from **one** source snapshot.

It does not return one final scholarship record.

### 6. V2 extraction does not repeat mandatory global identity on every supporting page

The current v1 validator requires root identity fields such as scholarship name/provider/country/degree from the same source.

That is wrong for supporting official pages.

Example:

```text
Japanese Embassy Malaysia page
  -> may contain local MEXT deadline and route instructions
  -> may not restate every global funding component or provider identity detail
```

PR6 source extraction receives an already-bounded public target context from PR5/ingestion:

```text
target candidate/scholarship identity snapshot
authorized acquisition objective
known cycle/track/institution/programme scope hints
```

This context tells the extractor what to focus on. It is not evidence and is never copied into a claim unless the source itself supports the value.

A supporting page can therefore legitimately produce only:

```text
local deadline claim
local route claim
required document claims
```

without failing because `country` or global funding is absent.

### 7. AI never emits canonical graph UUIDs

The extractor must not decide canonical identity by outputting:

```text
scholarship_id
cycle_id
track_id
institution_id
programme_id
source_owner_id
```

Those are system identities.

The extractor may emit bounded source-derived **scope hints**, for example:

```text
cycle_label: "2027 Embassy Recommendation"
track_name: "Embassy Recommendation"
institution_name: "University of Tokyo"
programme_name: "Master of ..."
country_route: "Malaysia"
```

A deterministic `ClaimScopeResolver` maps those hints against reviewed/known graph identities and objective context.

Outcome:

```text
RESOLVED_EXISTING
PROPOSED_NEW_SCOPE
AMBIGUOUS_SCOPE
UNRESOLVED_SCOPE
OUT_OF_TARGET_SCOPE
```

No fuzzy/first-row/model-selected UUID binding is allowed.

### 8. Scope hints may narrow the acquisition target but never silently change scholarship identity

If PR5 bound the source to candidate/scholarship A, a claim cannot use a scope hint to become scholarship B.

An apparent different named award inside the page becomes:

```text
relationship/independence investigation
```

not another PR6 claim under the current target.

### 9. V2 uses typed claim families, not arbitrary model-generated `field_path`

The model must choose from a closed schema.

Initial claim families should correspond to actual domain structures, for example:

```text
identity assertions
cycle observations
track/route observations
application openings/deadlines
funding components
eligibility rules
required documents
application steps/application URLs
institution participation
programme participation
```

Each family has a typed value schema.

The system—not the model—maps the family/value to canonical graph `entity_type` / `field_path` / materializer behavior.

Do not let a model invent fields such as:

```text
"special_requirement_47"
```

and silently persist them as truth.

### 10. V2 contains no truth confidence score

Do not ask the extraction model for:

```text
confidence = 0.93
```

as a truth-selection mechanism.

Routing diagnostics may have model/parse confidence if needed, but source truth uses:

```text
exact evidence
scope
source authority
typed validation
cycle/version
resolver policy
review decision where necessary
```

### 11. Every proposed claim carries verbatim evidence from the same snapshot

A claim includes one or more evidence items:

```text
excerpt
section_label/locator when available
support basis
```

The model-provided excerpt is only a locator proposal.

A deterministic `EvidenceLocator` must locate the verbatim text in the immutable snapshot and calculate:

```text
excerpt_start
excerpt_end
```

before the claim can participate in resolution.

Zero matches -> evidence validation failure.

### 12. Critical evidence must be semantically self-contained enough to locate safely

For Tier 0/Tier 1 claims, a bare token such as:

```text
"20 May 2027"
```

is weak evidence if the same date appears under multiple routes/scopes.

The extraction instruction should request the shortest complete sentence/clause that identifies the semantic subject where possible:

```text
"Embassy Recommendation applications must be submitted by 20 May 2027."
```

If an exact excerpt occurs multiple times and section/locator metadata cannot deterministically identify the intended occurrence, return:

```text
AMBIGUOUS_EVIDENCE_SPAN
```

for critical auto-resolution rather than arbitrarily choosing one occurrence.

For identical repeated non-critical wording, policy may allow a deterministic occurrence if the semantic claim is unaffected, but the rule must be explicit/versioned.

### 13. Extraction source association is system-owned

V1 includes `source_url` inside each evidence item.

V2 should not trust the model to repeat the source URL.

The extraction attempt is already bound to exactly one immutable snapshot/source.

Therefore source identity, owner, officiality, and authority are attached by the system, not generated by the model.

### 14. Source authority is never an extraction field

The model does not output:

```text
"this embassy is authoritative"
```

Authority comes from PR5/ADR 0007 reviewed owner-domain/source relationships and contextual source assessment.

Each evidence-bundle source stores an immutable source-context snapshot including at least:

```text
source/candidate-source ID
normalized URL/domain
owner type/ID where resolved
officiality status
authority relationship/class
objective scope
assessment/policy version
```

Resolver behavior remains reproducible if source metadata changes later.

### 15. Add a bundle-source abstraction so the resolver works before and after publication

Introduce conceptually:

```text
CatalogueEvidenceBundle
CatalogueEvidenceBundleSource
```

A bundle source references exactly one of:

```text
candidate_source_snapshot_id
canonical_source_snapshot_id
```

with an XOR constraint.

Claims reference `bundle_source_id`, not two different snapshot columns.

This avoids duplicating PR6 resolver logic for initial acquisition versus published refresh.

### 16. Candidate and canonical snapshots remain distinct trust objects

Do not mutate a candidate snapshot into a canonical snapshot by changing its FK.

On accepted materialization, create/reuse the canonical `Source` and canonical `SourceSnapshot` using the **exact normalized text/hash already reviewed**.

No re-fetch is required.

Then persist an immutable mapping:

```text
catalogue_snapshot_promotions
```

Recommended fields:

```text
id UUID PK
candidate_source_snapshot_id UUID NOT NULL
source_snapshot_id UUID NOT NULL
candidate_id UUID NOT NULL
opportunity_id UUID NOT NULL
promoted_at timestamptz NOT NULL
promotion_reason varchar(100) NOT NULL
```

Constraints:

```text
UNIQUE(candidate_source_snapshot_id, source_snapshot_id)
```

This proves the exact candidate bytes that crossed into canonical evidence.

### 17. Promotion validates exact content identity

Before promotion:

```text
candidate_snapshot.content_hash == source_snapshot.content_hash
candidate_snapshot.normalized_text == source_snapshot.normalized_text
```

must hold.

If canonical source content must be re-fetched for URL/security reasons and it no longer matches, promotion stops and a new candidate/current snapshot goes through resolution.

Never silently promote claims from old bytes onto new bytes.

### 18. Materialized `FieldEvidence` is created from accepted claim evidence spans

For an accepted claim promoted to a canonical graph fact:

1. resolve/create canonical graph entity/fact;
2. resolve the promoted canonical `SourceSnapshot`;
3. copy the exact validated excerpt offsets from candidate snapshot (same normalized text) or canonical refresh claim;
4. create canonical `FieldEvidence` using the existing `EvidenceStore` invariant;
5. record resolver/materialization audit reason.

The canonical graph never cites an extraction attempt or AI answer as evidence. It cites official source snapshot text.

### 19. PR6 generalizes the existing scoped-deadline inheritance principle

The existing graph resolver already proves an important rule:

```text
more-specific fact can override a broader fact only when explicit passed evidence exists
```

PR6 preserves this behavior and moves it before graph mutation.

The pre-materialization resolver should produce the same effective truth semantics later used by graph queries.

Do not build a second contradictory precedence system.

### 20. Preserve all corroborating evidence; do not select one source merely for convenience

If two accepted sources support the same normalized claim:

```text
CORROBORATED
```

The effective graph fact may be one row, but it can have multiple `FieldEvidence` rows.

Do not discard the second evidence source because a deterministic resolver only needs one value.

### 21. Unsupported source authority is a resolution result, not an extraction hallucination

An official university page can explicitly state a global-looking stipend amount. Extraction may correctly capture that sentence.

If the source is not accepted authority for global provider funding, resolution returns:

```text
UNSUPPORTED_AUTHORITY
```

The claim remains auditable but does not materialize as global truth.

This separates:

```text
"the source said it"
```

from:

```text
"the source can establish it at this scope"
```

### 22. Keep v1 extraction attempts for historical compatibility; do not rewrite applied history

The existing `catalogue_extraction_attempts` table remains intact for v1 ingestion history.

PR6 may add a generalized v2 evidence-extraction attempt table rather than making old rows pretend they had source snapshots/scope semantics they never possessed.

No destructive rewrite of historical extraction attempts.

### 23. V2 extraction attempts are keyed to immutable snapshot + extraction contract

Recommended idempotency input:

```text
snapshot kind + snapshot ID/content hash
extraction schema version
provider
model
prompt/instruction version
allowed claim family plan
```

If the exact snapshot and exact extraction contract were already successfully processed, reuse the extraction artifact.

Do not pay the model again because the same bytes were reached through another orchestration run.

### 24. Refresh uses canonical snapshots directly

For a published scholarship source changed by ADR 0010/0011 monitoring:

```text
new canonical SourceSnapshot
 -> v2 source extraction
 -> claims
 -> compare with prior effective claims
 -> resolver
 -> affected graph materialization/review
```

No candidate snapshot is needed because the canonical source identity already exists.

This keeps initial acquisition and maintenance on one claim/resolution model while preserving their different trust boundaries.

### 25. Source text is untrusted model input even when the source is official

The v2 system instruction must explicitly treat fetched source content as data, not instructions.

The model must ignore any instructions embedded in source text and must have no discovery/web/tool authority during extraction.

Official websites can contain user-generated text, scripts, compromised content, or instruction-like prose. Officiality is a provenance property, not prompt-safety immunity.

### 26. Claim extraction cannot publish or directly update graph facts

Required boundary:

```text
model output
 -> schema validation
 -> exact evidence validation
 -> scope resolution
 -> authority policy
 -> canonicalization
 -> conflict/resolution
 -> review/materialization policy
 -> graph
```

No path may skip directly from model JSON to `Opportunity`, `ScopedDeadline`, `FundingComponent`, `EligibilityRule`, `RequiredDocument`, `ApplicationStep`, `InstitutionParticipation`, or `TrackProgramme` writes.

### 27. PR6 does not change the publication kill switch

```text
APP_CATALOGUE_AUTO_PUBLISH_ENABLED=false
```

remains false.

PR6 may automate evidence acquisition, extraction, validation, corroboration, and safe resolution. Material Tier 0/Tier 1 changes still respect the review/publication boundary.

## Required tests

PR6 implementation must prove at least:

1. two official source texts are never concatenated into one extraction request;
2. a supporting source can produce a local deadline without restating global identity/funding;
3. candidate source snapshot is immutable and exact-text reproducible;
4. no candidate snapshot creates an Opportunity merely by existing;
5. model cannot emit/choose canonical graph UUIDs;
6. arbitrary model field paths are rejected by schema;
7. evidence excerpt absent from snapshot rejects the claim;
8. ambiguous critical excerpt span fails closed when locator cannot disambiguate;
9. authority metadata comes from system context, never model output;
10. a university source can be extracted correctly but rejected for global funding authority;
11. same claim from two sources preserves both evidence items;
12. identical candidate snapshot/extraction contract is not re-extracted;
13. candidate snapshot promotion creates exact equivalent canonical `SourceSnapshot` without re-fetch;
14. content mismatch prevents promotion;
15. canonical `FieldEvidence` offsets match promoted canonical snapshot text;
16. published refresh uses canonical `SourceSnapshot` and the same resolver semantics;
17. v1 extraction history remains readable/unchanged;
18. no extraction output can directly publish or mutate canonical graph facts.

## Consequences

### Positive

- multi-source behavior becomes deterministic engineering rather than a larger prompt;
- exact provenance survives the pre-publication trust boundary;
- supporting pages no longer fail because they omit unrelated global fields;
- candidate evidence does not create canonical identity prematurely;
- initial acquisition and future refresh share one resolver architecture;
- canonical graph evidence remains source snapshot text, not AI output;
- model responsibilities stay narrow: structured extraction from one bounded source.

### Cost

- PR6 adds an immutable candidate snapshot layer and explicit snapshot promotion mapping;
- v2 extraction requires a new contract rather than endlessly extending v1;
- the resolver must handle candidate/canonical bundle-source origins through a common abstraction;
- some normalized text is duplicated when candidate evidence is promoted into canonical snapshot storage.

These costs are accepted because the alternative either pollutes canonical identity early or loses the exact evidence needed to justify every graph fact.
