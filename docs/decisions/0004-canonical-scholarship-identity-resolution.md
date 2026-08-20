# ADR 0004: Resolve scholarship identity without composite-name invention

- Status: Accepted for PR5 design
- Date: 2026-08-19
- Applies to: PR5 discovery targets, alias resolution, duplicate prevention, and future autonomous acquisition
- Related: ADR 0002, ADR 0003, `docs/pr5-web-discovery-spec.md`, `docs/scholarship-information-contract.md`

## Context

The Scholarship Intelligence Graph contract defines a scholarship as **one independently awarded funding scheme**. Cycles, application tracks, participating institutions, programmes, deadlines, eligibility rules, and funding components are linked graph dimensions beneath that scholarship; they do not create new scholarship identities.

The existing repository contains several useful but different identity-like fields:

- `Opportunity.id` — durable database identity for a reviewed/staged opportunity;
- `Opportunity.canonical_slug` — unique public locator when populated;
- `Provider.id` and `Provider.canonical_id` — provider identities;
- `ScholarshipAlias` — reviewed search aliases, unique within a scholarship but not globally unique;
- `programme_family_id`, `cycle_id`, degree, and funding type — legacy duplicate/collision dimensions;
- `CatalogueCandidate.id` — one ingestion work item tied to one ingestion run;
- `CatalogueCandidate.idempotency_key` — current seed-ingestion collision key, which includes the possible official URL.

These cannot safely be collapsed into one synthetic "master key".

In particular:

1. the same scholarship can have multiple cycles, study levels, tracks, institutions, programmes, funding components, and official URLs;
2. the same short alias/acronym can legitimately be used by more than one scholarship;
3. a scholarship may change its official URL without changing identity;
4. a provider can administer several independent scholarships;
5. a cycle/year or funding variation must not create a second canonical scholarship merely because a legacy duplicate key differs;
6. a newly discovered award cannot be declared independent by a normalized name hash.

PR3 already correctly refuses fuzzy similarity as proof and requires stronger provider/application/source evidence for `SAME_SCHOLARSHIP`, while new independence requires explicit official identity, authority, separate application, independent decision, and current official evidence.

## Decision

### 1. The canonical scholarship identity is the reviewed graph entity, not a computed string

Once a scholarship exists in the reviewed graph, its canonical identity is:

```text
Opportunity.id
```

subject to the record representing `entity_kind = scholarship` and the reviewed relationship/independence state.

`canonical_slug` is a stable public locator/search route, not the fundamental identity key. It may be assigned or changed through reviewed catalogue governance without creating a new scholarship.

Do not derive canonical scholarship identity from:

- normalized scholarship name;
- alias/acronym;
- official URL;
- provider + name hash;
- provider + cycle + degree + funding tuple;
- search-result title;
- model-generated entity ID.

### 2. Before graph creation, PR5 uses an explicit acquisition target, not inferred identity

For PR5's live identity-resolution frontier, the automatic binding target is an existing:

```text
CatalogueCandidate.id
```

The candidate represents the known acquisition objective. Web discovery finds possible sources **for that target**; it does not independently decide which scholarship the search result should become.

A discovery run that is allowed to bind a root source must therefore have `target_candidate_id` populated.

Provider-only and institution-only discovery may populate the ledger without a candidate target, but cannot create/bind a scholarship candidate automatically in PR5.

### 3. Add an immutable target identity snapshot to each discovery run

To keep discovery auditable when names, aliases, domains, or registry records change later, each run stores a deliberately small public-data snapshot of the identity context used for planning and assessment.

Recommended fields:

```text
target_candidate_id UUID nullable FK -> catalogue_candidates
target_identity_snapshot JSON NOT NULL
```

The snapshot schema is versioned and may contain only public catalogue identity data:

```json
{
  "schema_version": "catalogue-discovery-target.v1",
  "candidate_id": "...",
  "scholarship_name": "Chinese Government Scholarship",
  "registered_aliases": ["CSC", "CGS"],
  "provider_id": "...",
  "provider_canonical_id": "...",
  "provider_name": "China Scholarship Council",
  "provider_official_domains": ["..."],
  "institution_id": null,
  "institution_name": null,
  "institution_official_domain": null,
  "country_code": "CN",
  "cycle_hint": "2027/28"
}
```

Rules:

- snapshot values are copied from reviewed catalogue/seed context at run creation;
- no student/profile/application/document data is permitted;
- the snapshot is never silently rewritten after provider/alias/domain edits;
- a later run receives a new snapshot;
- the snapshot is audit context, not authority to publish.

### 4. Cycle, degree, funding, route, institution, and programme are scopes/variants, not scholarship identity

These dimensions may constrain discovery or classification, but they do not create a canonical scholarship identity by themselves:

```text
scholarship identity
  ├── cycles
  ├── tracks/routes
  ├── study levels
  ├── participating institutions
  ├── programmes
  ├── funding components
  └── scoped deadlines/requirements
```

Therefore PR5 must not use the current legacy canonical duplicate tuple:

```text
provider + programme_family + cycle + degree + funding
```

as proof that two records are different scholarships.

That tuple remains a legacy creation/collision guard until a later graph-lifecycle migration replaces or narrows it. PR5 does not rewrite the existing opportunity creation path as part of web discovery.

### 5. Provider identity is a strong discriminator, but never sufficient proof of scholarship identity

When a reviewed provider is known, prefer its durable database/provider-canonical identity over raw provider-name comparison.

Provider matching outcomes:

```text
EXACT_CANONICAL_PROVIDER
EXACT_REVIEWED_PROVIDER_ALIAS   (future if provider aliases are added)
UNRESOLVED_PROVIDER
CONFLICTING_PROVIDER
```

Same provider + same/similar scholarship name is not enough to prove `SAME_SCHOLARSHIP`; providers can run many awards.

Different provider names are not automatically proof of independence either; co-funded/delegated schemes can exist.

### 6. Alias lookup is multivalued and must surface ambiguity

`ScholarshipAlias.normalized_alias` is indexed but is not globally unique. This is correct: acronyms such as short initialisms can collide across countries/providers.

A deterministic alias/name resolver returns a **set** of canonical scholarship IDs, then an outcome:

```text
NO_MATCH
UNIQUE_MATCH
AMBIGUOUS
```

Automatic selection is allowed only for `UNIQUE_MATCH` after applicable provider/owner context is checked.

If two canonical scholarships legitimately share the same alias, PR5 must not pick the first database row, highest search rank, or model preference.

Provider context may reduce an ambiguous set only when the provider identity is itself deterministically resolved.

### 7. Registered aliases are lookup evidence; unregistered translations are not silently learned

Reviewed aliases/acronyms/translations can participate in deterministic resolution.

A search-result title or model-generated translation must not be inserted automatically into `scholarship_aliases`.

Unregistered translations remain:

```text
unresolved discovery metadata
```

until official evidence/review establishes the alias relationship.

This preserves the PR3 regression rule that registered translations can resolve while unregistered translations remain unresolved.

### 8. URLs are source identities/signals, not scholarship identities

URL equality can be a strong duplicate/same-source signal after normalization and safe acquisition. URL difference is never proof of a different scholarship.

Examples:

```text
provider.example/award
provider.example/award-2027
provider.example/apply
university.example/provider-award
```

may all concern one scholarship.

A scholarship can also migrate to a new official domain or page path. Source history must preserve that change without creating a new scholarship.

### 9. Discovery never resolves a new independent scholarship from pre-fetch identity signals alone

For an unknown discovered named award, PR5 may record:

- discovered title/name hint;
- URL lead;
- owner/domain assessment;
- query provenance.

It may **not** allocate a new canonical scholarship identity automatically.

The later independent-discovery path remains:

```text
unknown named lead
  -> safe official acquisition
  -> evidence bundle
  -> relationship classification
  -> five-part independence gate
  -> human relationship review
  -> draft graph entity
  -> existing publication review
```

Only after that reviewed creation does the new `Opportunity.id` become canonical scholarship identity.

### 10. Identity resolution is evidence-tiered, not score-only

For existing canonical graph lookups, deterministic signals should be treated as evidence classes rather than blended into an opaque numeric score.

Recommended hierarchy:

#### Tier A — direct canonical reference

- explicit `Opportunity.id`;
- canonical slug resolved uniquely to one scholarship;
- existing reviewed relationship edge explicitly identifies the parent scholarship.

#### Tier B — registered identity evidence

A combination such as:

- registered canonical name/alias;
- deterministically resolved provider identity;
- matching reviewed application/source relationship where applicable.

This may produce `UNIQUE_MATCH` when only one canonical graph entity satisfies all required evidence.

#### Tier C — search/discovery hints

- fuzzy name similarity;
- unregistered translation;
- search-result title;
- same country;
- same degree/funding;
- same institution;
- partial token overlap.

Tier C may rank investigation targets but cannot establish canonical identity.

No weighted score crossing an arbitrary threshold may convert Tier C hints into a canonical scholarship identity.

### 11. PR5 root-source selection must use target identity, not search title identity

When `target_candidate_id` is present, a discovered page is assessed against the target snapshot:

```text
expected scholarship identity
expected provider/owner
expected institution context (if any)
reviewed domains
cycle hint
```

The page's search title is only ranking metadata.

A page can be bound as an official-root attempt only if deterministic source ownership/officiality is appropriate for the target context. The downstream extraction identity check still verifies that fetched content describes the expected target.

### 12. Do not auto-merge existing canonical scholarships in PR5

If identity resolution finds more than one plausible existing canonical scholarship, the outcome is `AMBIGUOUS` or a duplicate-review proposal.

PR5 must not:

- merge opportunities;
- move aliases between scholarships;
- rewrite `parent_scholarship_id`;
- change `independence_status`;
- collapse cycles/degree/funding variants;
- choose a winner based on search ranking.

Those are reviewed graph-governance actions.

## Schema refinement for PR5

Refine `catalogue_discovery_runs` from the initial PR5 specification to include:

```text
target_candidate_id UUID NULL
target_identity_snapshot JSON NOT NULL
```

`objective_ref` may remain as a human-readable/audit label, but it is not a foreign-key substitute and cannot authorize binding.

Recommended indexes:

```text
INDEX(target_candidate_id, created_at)
INDEX(status, created_at)
```

Recommended application invariant:

```text
binding_allowed => target_candidate_id IS NOT NULL
```

If a future phase adds opportunity-enrichment discovery, add an explicit `target_opportunity_id`/enrichment contract rather than overloading `objective_ref`.

## Identity resolver API contract

PR5 may implement a small deterministic read-only resolver for planning/review support:

```python
@dataclass(frozen=True)
class ScholarshipIdentityResolution:
    status: Literal["no_match", "unique_match", "ambiguous"]
    scholarship_ids: tuple[UUID, ...]
    evidence_codes: tuple[str, ...]
```

It never creates rows.

Possible evidence codes:

```text
CANONICAL_ID
CANONICAL_SLUG
CANONICAL_NAME
REGISTERED_ALIAS
CANONICAL_PROVIDER
REVIEWED_APPLICATION_URL
REVIEWED_SOURCE_URL
AMBIGUOUS_ALIAS
PROVIDER_CONFLICT
UNREGISTERED_NAME_HINT
```

Every result must be deterministic for the same reviewed graph state.

## Required tests

PR5 implementation must prove:

1. same scholarship across two cycles does not become two canonical identities;
2. degree-level differences do not prove separate scholarship identity;
3. funding-component/funding-type differences do not prove separate identity;
4. two official URLs for one scholarship do not create two candidates/scholarships;
5. canonical UUID lookup is unique;
6. canonical slug lookup is unique when present;
7. a registered alias resolving to one scholarship returns `UNIQUE_MATCH`;
8. the same normalized alias attached to two scholarships returns `AMBIGUOUS`;
9. provider context disambiguates only when provider identity is deterministic;
10. unregistered translations remain unresolved;
11. fuzzy similarity cannot create a canonical match;
12. same provider alone cannot establish same scholarship;
13. different URL alone cannot establish a new scholarship;
14. route/institution/programme pages cannot create identity;
15. unknown named awards require the independence/review path;
16. a discovery target snapshot is immutable for the life of the run;
17. no applicant/private fields can enter the target snapshot.

## Consequences

### Positive

- Scholarship count is protected from cycle/degree/funding/source inflation.
- PR5 does not inherit legacy duplicate-key assumptions as canonical truth.
- Alias collisions become visible instead of nondeterministic.
- Search ranking remains useful without becoming an identity authority.
- New independent awards still flow through evidence and human governance.
- Discovery runs remain reproducible even after catalogue identity metadata evolves.

### Cost

- PR5 needs explicit target/snapshot fields rather than one loose string reference.
- Some existing graph/legacy fields remain transitional technical debt.
- A later graph-lifecycle migration will still be needed to make all opportunity creation/update paths populate canonical graph identity fields consistently.

That later migration is intentionally **not** hidden inside PR5 web discovery.
