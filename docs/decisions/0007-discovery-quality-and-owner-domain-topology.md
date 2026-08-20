# ADR 0007: Make discovery quality owner-aware, staged, and measurable

- Status: Accepted for PR5 design
- Date: 2026-08-19
- Applies to: PR5 query planning, official-domain resolution, multilingual discovery, lead ranking, and discovery Gold evaluation
- Related: ADR 0002–0006, `docs/pr5-web-discovery-spec.md`, `docs/scholarship-information-contract.md`

## Context

PR5 is not valuable merely because it can call a web-search tool. It is valuable only if it can repeatedly find the correct official source for a known scholarship objective with low false-positive risk, bounded cost, and enough provenance for later evidence collection.

The live repository currently has a deliberately conservative `OfficialSourceClassifier`:

- reject known third-party scholarship directories;
- trust a reviewed domain allowlist;
- trust the canonical provider website family;
- recognize a small set of government suffixes;
- trust a resolved university website family;
- reject education-looking domains when institution identity is not resolved.

That is a strong fail-closed boundary for PR3/PR4, but it is not a complete global ownership model. Real scholarships commonly span more than one legitimate official domain:

```text
scholarship provider / ministry
    ├── canonical programme website
    ├── government ministry site
    ├── application portal
    ├── embassy / country mission page
    ├── delegated implementation body
    └── participating university pages
```

Those pages are not equally authoritative for every fact. An embassy page can be official for local nomination instructions while a provider/ministry remains authoritative for global funding rules. A university page can be official for its local deadline without becoming the umbrella award owner.

Search quality therefore cannot be solved by prompt cleverness alone. It needs:

1. verified owner-domain topology;
2. staged deterministic queries;
3. contextual source authority;
4. multilingual identity inputs that are reviewed rather than invented;
5. deterministic lead ranking;
6. early stopping once an information objective is safely satisfied;
7. evaluation against hard scholarship discovery cases.

Microsoft's current Web Search guide exposes domain allowlisting and can return source URLs consulted by the web-search action. This allows PR5 to search inside already-reviewed owner domains before falling back to broad discovery. Runtime capability remains gated separately because current Microsoft documentation is not fully consistent about stable Azure `web_search` availability.

## Decision

### 1. Separate owner resolution from page resolution

PR5 must distinguish two questions:

```text
Who/which domain is an official owner or delegated official source?
```

and:

```text
Which page on that trusted domain best satisfies this scholarship objective?
```

When an owner domain is already reviewed, PR5 performs **page resolution** first using domain-constrained search.

When no trusted owner domain exists, PR5 may perform **owner resolution discovery**, but a newly discovered domain remains unresolved until deterministic/reviewed ownership rules establish it. A domain discovered by Web Search does not become an allowlisted domain recursively inside the same run.

### 2. Add a reviewed owner-domain registration model

The existing single provider/university website fields remain useful canonical hints, but PR5 should support multiple reviewed domains and explicit authority relationships.

Recommended table:

```text
catalogue_source_owner_domains
```

Fields:

```text
id UUID PK
domain varchar(255) NOT NULL
owner_kind varchar(32) NOT NULL
provider_id UUID NULL
institution_id UUID NULL
owner_name_snapshot varchar(255) NOT NULL
relationship_kind varchar(32) NOT NULL
scope_country_code varchar(2) NULL
scope_notes varchar(500) NULL
status varchar(32) NOT NULL
valid_from timestamptz NULL
valid_to timestamptz NULL
review_reason varchar(500) NOT NULL
reviewed_by UUID NULL
reviewed_at timestamptz NULL
created_at timestamptz NOT NULL
```

Initial `owner_kind`:

```text
provider
institution
government_or_mission
delegated_portal
```

Initial `relationship_kind`:

```text
canonical_owner
co_owner
delegated_official
application_portal
country_mission
supporting_institution
```

Initial `status`:

```text
reviewed_active
reviewed_inactive
proposed
rejected
```

Constraints/invariants:

- normalized lowercase host only; no scheme/path/userinfo;
- exactly one of `provider_id` / `institution_id` may be required for the applicable owner kind; government/mission/delegated rows may anchor to the scholarship provider through `provider_id` when appropriate;
- `reviewed_active` requires `reviewed_at` and review reason;
- a `proposed` domain never participates in an Azure `allowed_domains` filter or automatic officiality decision;
- domain identity is contextual; the same registrable family may have more than one reviewed relationship where scope legitimately differs;
- no wildcard like `*.gov` is a substitute for reviewed ownership.

PR5 does not need to create a new global Organization microservice. It extends the catalogue's existing provider/institution identities with a narrow reviewed domain registry.

### 3. Canonical website fields seed the registry; the registry becomes the scalable lookup surface

For existing reviewed entities:

```text
Provider.website_url
Institution.official_domain / official_website
University.website_url
```

may be represented as `canonical_owner` / `supporting_institution` registrations during migration/backfill when they already satisfy current deterministic identity assumptions.

Do not automatically backfill arbitrary education-looking/government-looking domains merely from syntax.

The live classifier can remain backward compatible while PR5 progressively consults the reviewed registry first.

### 4. Authority classes control search and later fact scope

A reviewed domain registration does not mean "official for everything."

Interpretation:

#### `canonical_owner`

Appropriate candidate for scholarship-wide identity, global funding, global eligibility, and provider-level cycle/application facts when the fetched page supports them.

#### `co_owner`

Can support global/provider facts where the reviewed relationship establishes shared authority; conflicts still require review.

#### `delegated_official`

Official for the delegated function/scope, not automatically the scholarship's global truth source.

#### `application_portal`

Useful for application URLs/workflow and possibly current application-window evidence; not automatically authoritative for funding/eligibility prose.

#### `country_mission`

Official for country/embassy/local nomination instructions and scoped deadlines; not automatically a global provider source.

#### `supporting_institution`

Official for institution/programme/local deadline/requirement scope. Supporting-official for an umbrella scholarship unless the institution owns the award.

This authority class flows into `DiscoveryAssessment`, objective fulfilment, and later PR6 field-evidence scope.

### 5. Use a staged query ladder, strongest evidence first

The planner produces all allowed query strings deterministically up front, but execution may stop early when the objective is fulfilled.

Recommended query ladder:

#### Tier 0 — no Web Search required

If the exact reviewed official source URL is already current and satisfies the objective, suppress discovery entirely.

#### Tier 1 — reviewed-domain page resolution

When one or more reviewed owner domains are known:

```text
exact canonical scholarship name + objective terms
registered alias + objective terms
provider name + canonical scholarship name
```

with Azure `allowed_domains` restricted to reviewed active domains that are authoritative for the objective scope.

This is the default high-precision path.

#### Tier 2 — reviewed-owner identity refinement

When the owner is known but no usable domain-constrained result appears:

```text
"canonical scholarship name" "canonical provider name"
"registered alias" "canonical provider name"
```

Broad search is allowed, but all returned domains remain leads and must pass ownership assessment.

#### Tier 3 — canonical scholarship identity broad resolution

Used only when provider/domain context is incomplete:

```text
"canonical scholarship name" official
"canonical scholarship name" country/provider hint
```

This tier has a stricter call/lead budget and cannot auto-register a new owner domain.

#### Tier 4 — scope-specific refinement

Only after the umbrella/root identity is resolved, and only for an objective that genuinely needs local scope:

```text
"scholarship name" "institution name" deadline
"scholarship name" "institution name" requirements
"scholarship name" embassy/mission country
```

Prefer reviewed institution/mission domains where available.

Do not run Tier 4 merely to increase page count.

### 6. Do not rely on search query operators as a core contract

The planner should not depend on undocumented engine-specific syntax such as complex `site:`, exclusion, or ranking operators.

Use structured Web Search controls such as reviewed-domain filters when the runtime capability supports them.

The query text itself should remain simple, readable, reproducible, and provider-portable.

### 7. Use reviewed aliases/translations; never silently machine-translate identity

Multilingual discovery is important, but an AI-generated translation can accidentally create a false identity.

Allowed query identity inputs:

- canonical scholarship name;
- reviewed `ScholarshipAlias` values, including official translations/transliterations;
- canonical provider name;
- reviewed institution aliases;
- reviewed local/translated owner names when a later provider-owner alias registry exists;
- official cycle/route names already present in the reviewed graph.

Not allowed as automatic identity proof:

- model-generated translation;
- search-result translation;
- unreviewed transliteration;
- translation inferred from a third-party directory.

A model-generated language variant may be retained only as unresolved discovery metadata for later review, not inserted into canonical alias tables.

### 8. Do not use applicant location to bias scholarship discovery

The Web Search API can support approximate user location, but catalogue discovery is an objective about the scholarship/provider—not the current operator/student location.

PR5 therefore leaves provider `user_location` unset by default.

Country-specific scholarship/embassy discovery is expressed explicitly in the deterministic query/objective scope.

This avoids a worker running in Malaysia, Southeast Asia, or another Azure region accidentally biasing results for a scholarship whose authoritative source is in Japan, the UK, Germany, or elsewhere.

A future evaluated localisation strategy may set objective-specific search location only if it proves measurable recall gains without source-authority regressions.

### 9. Prefer low search context and source metadata, not generated answer prose

PR5 needs URLs, not a synthesized scholarship answer.

When the runtime supports it, prefer the lowest search-context setting that still passes the discovery Gold set, and request the source/action metadata required to extract consulted URLs.

The provider output parser ignores grounded narrative text for catalogue truth.

Any change from low to medium/high context must be justified by measured recall/precision improvement versus additional token/cost usage.

### 10. Search tool execution is required and verified

The request must clearly instruct the model to perform the web search. If supported reliably by the exact target runtime, a tool-choice mode that requires tool use may be evaluated.

Regardless of request settings, success is determined only by the response containing the expected web-search action item.

No `web_search_call` => `TOOL_NOT_EXECUTED`.

Never parse URLs from free-form assistant text as a fallback.

### 11. Lead ranking is deterministic and trust-first

Search provider rank is useful but weak. It is never the first ranking dimension for auto-binding.

Recommended lexicographic lead ranking tuple:

```text
(
  url_policy_rank,
  owner_authority_rank,
  contextual_officiality_rank,
  objective_scope_match_rank,
  query_tier_rank,
  query_intent_rank,
  reviewed_alias_match_rank,
  cycle_hint_rank,
  provider_result_rank,
  normalized_url_tiebreak
)
```

Key principle:

```text
reviewed owner + correct scope
    beats
high search rank on an unresolved/third-party domain
```

The ranking may use bounded title/path tokens for navigation relevance, but not as evidence that a fact is true.

### 12. Root selection and supporting-source selection are different

For a known umbrella scholarship:

- one strongest canonical/provider-authority root is selected for PR5 binding;
- additional high-quality institution/embassy/application-portal leads remain in the discovery ledger;
- supporting leads become useful in PR6 multi-source evidence acquisition, where field scope/provenance can be preserved.

This prevents PR5 from treating every official result as another extraction root.

For an institution-owned independent scholarship, a reviewed institution `canonical_owner` domain may legitimately be the root.

### 13. Execute planned queries adaptively, but never generate queries recursively from search prose

All candidate queries are deterministic outputs of the planner before external calls.

Execution policy:

```text
run highest-precision query
  -> evaluate persisted leads/assessment/binding
  -> if objective satisfied, stop
  -> otherwise run next preplanned query
```

Allowed feedback:

- objective satisfied/not satisfied;
- no acceptable lead;
- budget remaining;
- capability/failure state.

Not allowed feedback into new query generation:

- search snippet text;
- generated answer prose;
- model suggestions such as "try searching X";
- an unreviewed discovered alias/domain.

This provides adaptive cost efficiency without turning PR5 into an agentic recursive search loop.

### 14. Apply per-owner and per-domain lead diversity before fetch

Web Search may return many near-duplicate URLs from one site.

Before expensive safe fetching:

- normalize/deduplicate URLs;
- group by reviewed owner/domain;
- suppress obvious duplicate path/query variants;
- prefer one strongest root candidate per owner/authority class initially;
- retain observations for suppressed duplicates in the ledger;
- expand to additional pages only if the objective remains unsatisfied or PR4 crawler/PR6 needs them.

Do not fetch five search URLs from the same owner when one reviewed root plus bounded site crawl can resolve the objective more safely and cheaply.

### 15. Third-party domains can inform discovery only as rejected observations

Known scholarship directories are explicitly rejected by the live classifier.

PR5 may optionally configure `blocked_domains` for known high-volume directories when the runtime capability is proven, to reduce search noise/cost. This is an optimization only.

The trust boundary remains deterministic classification after results return.

Unknown third-party domains are persisted/rejected/unresolved according to policy; they cannot contribute scholarship facts.

### 16. Government-domain syntax is a hint, not a global registry

The live classifier contains a small government suffix list. PR5 must not expand this into a guessed universal list and call every matching host official.

Government/ministry/embassy trust at scale should come from reviewed owner-domain registrations and explicit country/authority context.

Suffix syntax can remain a bounded legacy signal, but reviewed ownership outranks it.

### 17. Discovery quality is evaluated by official-source retrieval, not URL volume

PR5 gets a dedicated frozen **Discovery Gold Set** separate from extraction Gold evaluation.

Recommended initial composition: 60 public scholarship objectives.

```text
12 government / national flagship schemes
10 independent university awards
8 foundation / international-organization awards
8 embassy / country-route objectives
8 multilingual / official-translation cases
6 acronym/name-collision or ambiguous cases
4 moved/redirected official source cases
4 third-party/SEO-dominated negative cases
```

Each fixture records:

- canonical scholarship identity;
- reviewed provider/owner;
- expected acceptable official domain family/families;
- authority class;
- expected objective scope;
- registered aliases/translations permitted for queries;
- known unacceptable third-party domains;
- whether unresolved is the correct safe outcome;
- expected maximum query tier needed.

Do not encode one brittle exact URL when multiple official pages are valid; encode acceptable owner/domain/authority outcomes and target-binding expectations.

### 18. Proposed discovery release metrics

These are engineering gates to validate empirically, not vendor guarantees.

#### Hard safety gates

```text
third_party_auto_bind_rate = 0
unresolved_domain_auto_bind_rate = 0
search_snippet_as_evidence_count = 0
model_generated_alias_auto_registration_count = 0
applicant_private_field_in_query_count = 0
automatic_publication_count = 0
```

#### Quality targets for Gold evaluation

```text
official_root_recall_at_5 >= 95%
auto_bound_root_precision = 100%
reviewed_domain_constrained_success_rate measured separately
multilingual_official_root_recall >= 90% for reviewed-alias fixtures
ambiguous_case_false_resolution_rate = 0
```

#### Efficiency targets to measure

```text
median provider requests before acceptable root <= 2
p95 provider requests before terminal outcome <= 4
median unique leads per successful objective
cost per acceptable official root
cost per COMPLETE_CORE scholarship later
percentage of objectives satisfied by reviewed-domain Tier 1 search
```

If precision/identity safety and recall conflict, prefer unresolved/exception over false official binding.

### 19. Run-level diagnostics preserve query-tier attribution

Every query row records:

```text
query_kind
query_tier
query_intent
allowed_domains
planner_version
```

Discovery evaluation can therefore answer:

- Which query tier actually finds official roots?
- Which templates waste calls?
- Which scholarship types need local-language aliases?
- Which reviewed domains produce no usable pages?
- How often broad Tier 3 search is required?
- Where third-party SEO pressure is highest?

Planner changes are versioned and evaluated A/B offline against the same frozen Gold set before replacing the production planner version.

### 20. Discovery planner evolution is evidence-based

Do not continuously mutate production query templates based on anecdotal misses.

Workflow:

```text
miss / exception
  -> add reviewed regression fixture
  -> propose planner/owner-registry change
  -> run frozen Gold set
  -> compare precision, recall, cost, query count
  -> adopt new planner version only if gates remain satisfied
```

This prevents search prompt drift from silently changing acquisition behavior.

## Implementation impact

PR5 implementation should incorporate:

1. `catalogue_source_owner_domains` (or an equivalent narrowly scoped reviewed-domain table);
2. query-tier / query-intent fields in discovery query records;
3. reviewed-domain-aware query planning;
4. owner-authority-aware contextual assessments;
5. deterministic lead ranking;
6. early-stop execution over preplanned queries;
7. Discovery Gold Set fixtures/evaluator;
8. metrics broken down by query tier and terminal outcome, without domain/URL labels in telemetry.

The public-domain registry contains catalogue governance metadata only and must not become a general-purpose tenant/admin URL allowlist.

## Required tests

PR5 implementation must prove at least:

1. a reviewed provider domain is searched before broad web discovery;
2. a `proposed` domain never enters `allowed_domains`;
3. a country-mission domain cannot satisfy umbrella global-funding authority automatically;
4. an institution supporting domain cannot become umbrella root without correct authority context;
5. an institution-owned award may use its institution canonical-owner domain;
6. registered official translation can generate a query;
7. unregistered/model-generated translation cannot establish identity or auto-register an alias;
8. applicant/user physical location is not included by default;
9. one successful high-precision query suppresses lower-priority provider calls;
10. search-result prose cannot create additional recursive queries;
11. provider rank cannot outrank a reviewed owner/authority match;
12. known third-party domains never auto-bind;
13. repeated URLs/path variants deduplicate before fetch;
14. broad search results cannot become reviewed domains within the same run;
15. ambiguous identity fixtures remain unresolved;
16. every Gold case records query tier/call count/outcome for cost/quality analysis.

## Consequences

### Positive

- Most known-provider scholarships can use precise domain-constrained discovery instead of noisy global search.
- Multiple legitimate official domains are represented without pretending they have equal authority.
- Embassy, portal, and institution pages can contribute later without corrupting global scholarship facts.
- Multilingual discovery improves through reviewed aliases rather than translation guesses.
- Search costs fall through early stopping and owner-aware deduplication.
- Planner improvements become measurable engineering changes instead of prompt experimentation.

### Cost

- PR5 gains a small reviewed owner-domain registry and additional query metadata.
- Initial owner/domain governance requires a reviewed bootstrap for flagship providers/institutions.
- Some unknown-owner scholarships will correctly remain unresolved until the owner identity is established.

These costs are accepted because source ownership is the foundation of both discovery precision and downstream evidence trust.
