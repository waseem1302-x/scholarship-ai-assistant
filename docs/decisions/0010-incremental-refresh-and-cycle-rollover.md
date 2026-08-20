# ADR 0010: Maintain the catalogue incrementally across source changes and scholarship cycles

- Status: Accepted for architecture; implementation spans PR6/PR8
- Date: 2026-08-19
- Applies to: source monitoring, cycle rollover, freshness, re-extraction, source relocation, catalogue maintenance, and autonomous acquisition
- Related: ADR 0002–0009, `docs/scholarship-information-contract.md`, `docs/pr5-web-discovery-spec.md`

## Context

A catalogue of 500 trusted scholarships must not be rebuilt from zero every year.

The canonical scholarship identity is intended to survive:

- annual application cycles;
- deadline changes;
- funding/eligibility changes;
- source-page edits;
- official URL relocation;
- provider website redesigns;
- new/removed participating institutions and programmes;
- temporary source failures.

The live repository already contains important foundations:

1. `OpportunityCycle` explicitly represents historical/recurring application windows and documents that prior cycles must never be overwritten.
2. Only one `OpportunityCycle.is_current` row is permitted per opportunity.
3. `Opportunity` contains `current_cycle_id`, `last_verified_at`, and `next_review_at` compatibility/summary fields.
4. The public application window is materialized from cycle history rather than deleting old cycles.
5. `Source` has monitoring leases, next-check timestamps, failure counters, content hash, last-updated/verified state, officiality, owner metadata, and active state.
6. A scheduled Azure Container Apps source-monitor job already runs daily and performs bounded safe fetching with per-host throttling/backoff.
7. The source monitor distinguishes changed/unchanged/initial hash outcomes.
8. `SourceSnapshot` is immutable and deduplicated by `(source_id, content_hash)`.
9. `FieldEvidence` preserves exact evidence spans against immutable snapshots.

These are strong primitives, but they do not yet form a complete incremental-maintenance engine.

Important current limitations:

- the legacy source monitor's `Source.content_hash` intentionally hashes a selected relevant section to avoid noisy change storms; its fetcher also computes a full normalized-content hash, but that full hash is not currently the durable refresh identity;
- an unchanged monitor check records observation activity but does not by itself advance the human `Source.last_verified_at`;
- source change currently demotes the source to `NEEDS_REVIEW` broadly rather than generating a field/scope-aware refresh plan;
- a changed published scholarship has no explicit non-candidate refresh/enrichment lifecycle;
- cycle detection/idempotency is not yet a first-class resolver;
- `Opportunity.current_cycle_id` and `OpportunityCycle.source_id` are currently compatibility columns without enforced graph foreign-key semantics in the ORM model;
- the source monitor detects page changes but does not yet create/reuse `SourceSnapshot` plus PR6 evidence bundles for precise change resolution.

The target is therefore **incremental truth maintenance**, not periodic re-ingestion.

## Decision

### 1. Canonical scholarship identity survives cycles and source changes

A reviewed scholarship remains the same canonical entity:

```text
Opportunity.id
```

across:

```text
2026 cycle
2027 cycle
2028 cycle
new official URL
provider website redesign
new institution list
changed stipend
```

Do not create a new scholarship because:

- the year changed;
- the deadline changed;
- the official page moved;
- a new PDF was published;
- a cycle-specific route page appeared.

A new independent scholarship identity still requires ADR 0004/PR3 independence evidence.

### 2. Preserve four separate concepts: identity, cycle, source, observation

The maintenance model is:

```text
Scholarship identity
  -> Cycle history
  -> Official Source identities
  -> Immutable Source content snapshots
  -> Repeated source observations
  -> Field claims/evidence
```

These must not be collapsed.

A source URL is not a scholarship.
A snapshot is not a source identity.
A new snapshot is not automatically a new cycle.
A new cycle is not a new scholarship.

### 3. Add durable source-observation history

`SourceSnapshot` stores unique content, but repeated unchanged checks need their own lightweight history.

Introduce:

```text
source_observations
```

Recommended fields:

```text
id UUID PK
source_id UUID NOT NULL
observed_at timestamptz NOT NULL
outcome varchar(32) NOT NULL
requested_url varchar(2048) NOT NULL
final_url varchar(2048) NULL
http_status int NULL
content_type varchar(255) NULL
byte_count int NOT NULL default 0
monitor_section_hash varchar(128) NULL
normalized_content_hash varchar(128) NULL
source_snapshot_id UUID NULL
previous_source_snapshot_id UUID NULL
redirect_count int NOT NULL default 0
failure_code varchar(100) NULL
next_check_at timestamptz NULL
created_at timestamptz NOT NULL
```

Initial outcomes:

```text
UNCHANGED
CHANGED
INITIALIZED
RELOCATED_UNCHANGED
RELOCATED_CHANGED
UNREACHABLE
ACCESS_BLOCKED
ROBOTS_BLOCKED
UNSUPPORTED_CONTENT
LOW_INFORMATION
```

Rules:

- one row per monitoring attempt;
- no raw response body stored in the observation;
- successful usable content links to a `SourceSnapshot`;
- repeated identical normalized content reuses the existing snapshot;
- the observation records that the same immutable snapshot was seen again at a later time;
- failures preserve operational history without creating fake snapshots.

### 4. Full normalized content hash is the evidence-reuse identity

The legacy monitor-section hash remains useful as a cheap/noise-resistant operational signal, but it cannot prove all evidence is unchanged.

For evidence reuse and refresh planning use:

```text
normalized_content_hash
```

computed using the same reviewed normalization semantics as the authoritative safe-fetch/snapshot pipeline.

Required behavior:

```text
same normalized content hash
  -> reuse existing SourceSnapshot
  -> no re-extraction
  -> evidence can remain attached to the same immutable content

new normalized content hash
  -> create new SourceSnapshot
  -> enqueue bounded refresh task
```

Do not create duplicate snapshots merely because a source was checked again.

### 5. Separate human verification from machine-observed unchanged freshness

Keep:

```text
Source.last_verified_at
```

as the timestamp of the governing human/review policy verification event.

Do **not** rewrite it on every machine monitor check.

Add or derive a separate concept:

```text
last_observed_unchanged_at
```

which may be materialized on `Source` for efficient reads but is backed by `source_observations`.

The effective evidence-freshness policy can then reason about:

```text
human/policy verification age
+ exact snapshot last observed unchanged
+ field freshness class
+ cycle applicability
```

This avoids both bad extremes:

- forcing a human to reverify identical bytes every 90 days;
- pretending a machine fetch is equivalent to a human policy review.

### 6. Exact unchanged content can extend evidence usability under policy

If:

1. a source was previously accepted/verified;
2. the safe monitor observes the exact same normalized snapshot hash;
3. source ownership/officiality has not been invalidated;
4. the field's freshness policy permits unchanged-content carry-forward;
5. cycle applicability is still valid;

then existing `FieldEvidence` against that snapshot may remain `VERIFIED_CURRENT` without re-running AI extraction.

This is the core cost-saving path.

However, unchanged bytes cannot make an old-cycle deadline current for a new cycle. **Content freshness and cycle applicability are separate.**

### 7. A changed source triggers source-local re-extraction, not catalogue-wide rebuilding

When normalized content changes:

```text
Source A old snapshot
  -> Source A new snapshot
  -> PR6 evidence bundle/change analysis for Source A
```

Do not automatically re-extract:

- unrelated Source B/C/D pages;
- unrelated scholarships;
- stable provider identity;
- unchanged graph branches.

PR6 compares old and new normalized claims and determines which semantic claim keys changed.

Example:

```text
Deadline changed
Funding unchanged
Eligibility unchanged
```

Only deadline-dependent materialized facts/completeness dimensions are invalidated/reconsidered.

### 8. A changed page may be re-extracted broadly once; graph mutation remains field-local

Before PR6 knows which facts changed, it is acceptable to run one bounded extraction over the **changed source snapshot**.

This is still incremental: one changed page is reprocessed, not the whole scholarship or catalogue.

The resolver then computes claim differences:

```text
ADDED
REMOVED
CHANGED
UNCHANGED
SCOPE_CHANGED
```

and materializes only affected effective facts after validation/review policy.

Do not attempt unsafe optimization that skips re-extraction merely because old evidence excerpts still appear: a page may add a new cycle or new eligibility restriction while keeping old text intact.

### 9. Published opportunities use explicit refresh tasks, not new catalogue candidates

Do not create a fresh `CatalogueCandidate` merely because a published scholarship source changed.

Introduce an explicit maintenance work item, conceptually:

```text
CatalogueRefreshTask
```

Recommended fields:

```text
id UUID PK
opportunity_id UUID NOT NULL
source_id UUID NULL
source_snapshot_id UUID NULL
trigger_kind varchar(64) NOT NULL
objective_kind varchar(64) NOT NULL
scope_snapshot JSON NOT NULL
status varchar(32) NOT NULL
priority int NOT NULL
input_fingerprint varchar(64) NOT NULL
attempt_count int NOT NULL default 0
next_attempt_at timestamptz NULL
claimed_by varchar(255) NULL
claimed_until timestamptz NULL
failure_code varchar(100) NULL
created_at timestamptz NOT NULL
completed_at timestamptz NULL
```

Trigger kinds initially:

```text
SOURCE_CHANGED
SOURCE_RELOCATED
SOURCE_UNAVAILABLE
FRESHNESS_DUE
CYCLE_ROLLOVER_EXPECTED
NEW_CYCLE_DETECTED
COMPLETENESS_GAP
CONFLICT_RECHECK
```

Idempotency:

```text
UNIQUE(opportunity_id, objective_kind, scope/input_fingerprint)
```

or an equivalent explicit partial/open-task uniqueness rule.

Workers use the existing PostgreSQL lease/`SKIP LOCKED` pattern.

### 10. Refresh tasks reuse PR5 discovery and PR6 evidence; they do not duplicate those subsystems

Refresh orchestration is composition:

```text
Source monitor / lifecycle scheduler
  -> RefreshTask
      -> known source fetch if source known
      -> PR5 targeted rediscovery if source missing/moved
      -> PR6 evidence bundle + resolver if content changed
      -> ADR 0008 completeness reassessment
      -> next task only if an actual gap remains
```

Do not create a separate refresh crawler, refresh AI extractor, or refresh truth database.

### 11. Cycle rollover is append-only

For the same scholarship:

```text
Opportunity
  ├── OpportunityCycle 2026
  ├── OpportunityCycle 2027
  └── OpportunityCycle 2028
```

Never update `2026` into `2027`.

Previous cycles retain:

- dates;
- cycle-scoped eligibility;
- cycle-scoped funding;
- route/institution/programme facts;
- evidence snapshots/claims;
- review history.

### 12. New-cycle detection is a proposal/resolution problem, not string incrementing

Never generate the next cycle by doing:

```text
2026 -> 2027
```

and assuming the scholarship is available.

Historical cadence may schedule a **check**, but cannot create truth.

A new cycle is established only from current official evidence that can identify a new application/intake period.

Potential signals:

- explicit official cycle/year label;
- current application opening/deadline tied to a new period;
- new official application guidance/PDF;
- provider explicitly announces a new intake/call.

AI may extract/propose cycle identity; deterministic validation/evidence governs acceptance.

### 13. Add a cycle-resolution key separate from mutable dates

Dates can move; therefore deadline/opening date must not be the sole cycle identity.

PR6/PR8 should introduce a versioned `CycleIdentityResolver`.

Conceptual normalized inputs:

```text
official cycle label when available
intake year/academic period when explicitly supported
provider cycle/call identifier when available
scholarship identity
```

Outcome:

```text
EXISTING_CYCLE
NEW_CYCLE_PROPOSAL
AMBIGUOUS_CYCLE
INSUFFICIENT_EVIDENCE
```

A versioned cycle identity fingerprint supports idempotency of repeated detection, but the UUID of an accepted `OpportunityCycle` remains the canonical cycle identity.

Do not include deadline as a required identity component because deadlines legitimately change within one cycle.

### 14. Harden cycle linkage before autonomous rollover

The current model has compatibility identifiers that should be strengthened before autonomous cycle switching.

Target schema direction:

```text
Opportunity.current_cycle_id
  -> FK opportunity_cycles.id
  -> referenced cycle must belong to the same Opportunity

OpportunityCycle.source_id
  -> either a real FK to Source where kept
  -> or superseded by PR6 field evidence/claim provenance
```

Because a simple FK cannot enforce "cycle belongs to this opportunity" by itself across all engines, the service transition must also verify ownership under row lock.

`Opportunity.current_cycle_id` and `OpportunityCycle.is_current` must never disagree after a committed lifecycle transition.

### 15. Current-cycle switch is one atomic reviewed/materialization transition

When a validated new cycle is accepted:

within one transaction:

1. lock the scholarship/current-cycle rows;
2. verify the proposed cycle belongs to this scholarship;
3. mark previous cycle `is_current = false`;
4. mark new cycle `is_current = true`;
5. set `Opportunity.current_cycle_id`;
6. materialize current catalogue window compatibility fields;
7. reassess current-cycle completeness;
8. preserve previous cycle as historical/archived according to lifecycle policy.

There must never be an observable state with two current cycles or a current-cycle pointer to another scholarship.

### 16. Closing an old cycle is not the same as announcing a new cycle

If the 2026 deadline passes and no 2027 official evidence exists:

public state should be conceptually:

```text
2026 cycle: closed/historical
next cycle: not yet confirmed
```

not:

```text
2027: open/upcoming (guessed)
```

The catalogue may retain the canonical scholarship page and show "next cycle not yet verified" rather than disappearing or fabricating a deadline.

### 17. Use historical cadence only to schedule proactive checks

Historical cycles can tell the system **when to look**, not **what the next facts are**.

Example:

If a scholarship historically opens annually around a similar month, scheduler policy may create:

```text
CYCLE_ROLLOVER_EXPECTED
```

before/around that renewal window.

The check runs PR5 domain-constrained discovery/current-source monitoring.

No new cycle is created if no official evidence is found.

Cadence inference must be conservative, versioned, and bounded.

### 18. Freshness scheduling is risk-based, not one interval forever

The existing 7-day source-monitor interval and 90-day source freshness are useful baseline behavior, but the target model uses freshness classes from ADR 0008.

Examples:

```text
IDENTITY_STABLE
CYCLE_CRITICAL
DEADLINE_CRITICAL
FUNDING_CRITICAL
ELIGIBILITY_CRITICAL
STRUCTURAL_LIST
WORKFLOW_GUIDANCE
```

Scheduler priority can tighten near relevant periods:

```text
closed / far from expected cycle
  -> lower-frequency checks

approaching historical opening window
  -> higher-priority cycle check

application open
  -> deadline/route sources checked more frequently

just before deadline
  -> highest priority for deadline-critical sources

after deadline
  -> confirm closure and reduce cadence
```

Exact intervals remain configuration/policy and should be tuned from real monitoring data rather than permanently embedded in this ADR.

### 19. Source relocation does not create a new scholarship or erase source history

If:

```text
old URL -> redirect -> new URL
```

then safe-fetch and owner-domain policy determine whether this is a legitimate relocation.

If owner/authority remains valid and normalized content is unchanged:

```text
RELOCATED_UNCHANGED
```

- preserve old requested URL/history;
- update/reconcile canonical source URL through the existing safe URL rules;
- reuse the snapshot/evidence;
- no AI extraction required.

If content changed:

```text
RELOCATED_CHANGED
```

- create/reuse new snapshot;
- run normal bounded refresh resolution.

If redirect leaves accepted ownership/authority scope, fail closed and run targeted rediscovery/review.

### 20. 404/unavailable sources never delete scholarship truth immediately

A temporarily unavailable source produces operational failure/backoff.

After configurable repeated/terminal failure:

```text
SOURCE_UNAVAILABLE
  -> targeted PR5 rediscovery using known scholarship/provider identity
```

Existing reviewed facts become stale/update-pending according to field policy; they are not deleted merely because one URL disappeared.

If a replacement official page is found, attach it to the same scholarship/source lineage and continue.

### 21. Unchanged snapshots do not trigger AI or PR6 resolution

Cheap path:

```text
scheduled safe fetch
  -> normalized hash matches existing snapshot
  -> SourceObservation(UNCHANGED)
  -> refresh effective observation freshness
  -> no new snapshot
  -> no AI extraction
  -> no claim resolver
  -> no graph write
```

This must be the dominant steady-state behavior at 500 scholarships.

### 22. Changed snapshots trigger one bounded work unit

Expensive path:

```text
scheduled safe fetch
  -> new normalized hash
  -> immutable SourceSnapshot
  -> one idempotent RefreshTask
  -> PR6 source-local extraction
  -> normalized claim diff/resolution
  -> affected graph materialization only
```

If another monitor worker sees the same hash, uniqueness/idempotency prevents duplicate extraction.

### 23. Cycle-sensitive facts are not blindly inherited

For a new cycle, do not copy old values and call them current.

Tier 1 volatile facts require current-cycle evidence/policy:

```text
application timing
funding
eligibility
application route
```

Old-cycle values can be used as:

- historical context;
- comparison inputs;
- expected-field templates for completeness checking;
- targeted acquisition hints.

They cannot silently become confirmed new-cycle facts.

### 24. Stable scholarship-level facts may persist across cycles

Facts whose scope is genuinely scholarship/provider-level and whose evidence/freshness policy remains valid do not need duplication into every cycle.

Examples can include:

```text
canonical scholarship identity
provider identity
reviewed owner domains
registered aliases
long-lived relationship structure where still current
```

The graph resolver uses inheritance/effective-scope rules rather than copying rows.

This is another major reason scope must be explicit.

### 25. New-cycle acquisition starts from known structure, not zero

When a new cycle is detected, the completeness engine evaluates the new cycle against the existing scholarship graph.

It knows which dimensions need new-cycle proof and which stable dimensions are inherited.

Example:

```text
Scholarship identity       inherited/current
Provider                   inherited/current
Owner domains              inherited/current

2027 timing                missing -> acquire
2027 funding               needs current-cycle proof
2027 eligibility           needs current-cycle proof
2027 route                 needs current-cycle proof
Institution structure      reuse as hypothesis; verify if policy/cycle requires
Documents                  verify if current-cycle policy requires
```

This makes rollover a focused evidence refresh rather than discovery from scratch.

### 26. Material changes do not silently overwrite published truth

`APP_CATALOGUE_AUTO_PUBLISH_ENABLED=false` remains the publication boundary.

A changed/new-cycle extraction may automatically:

- acquire official sources;
- create snapshots;
- extract claims;
- validate deterministic rules;
- resolve scope/authority where safe;
- compute completeness;
- reach `READY_FOR_REVIEW`/equivalent maintenance state.

It may not silently publish a material changed Tier 0/Tier 1 fact merely because AI extracted it.

Routine **acquisition** is automated; human governance remains focused on material exceptions/approval according to the existing publication contract.

Unchanged-content freshness carry-forward is not publication of a new fact; it is reuse of the same previously reviewed evidence bytes under policy.

### 27. Review should be change-focused, not full-record-focused

For a material refresh, the reviewer/admin surface should eventually show:

```text
previous effective value
proposed new value
field + graph scope
old/new source snapshot
exact excerpts
resolver reason
cycle/version context
completeness impact
```

Example:

```text
APPLICATION_DEADLINE
2026 cycle: 15 May 2026 [historical]
2027 proposed: 12 May 2027 [official current source]
```

Do not ask a reviewer to reread the entire scholarship record when only one field changed.

### 28. Refresh history is append-only enough to explain every public change

For any public fact, operations should eventually be able to answer:

```text
What source/snapshot originally established this?
When was that exact snapshot last observed unchanged?
What source change triggered re-extraction?
Which normalized claim changed?
How was scope/authority resolved?
Who/what approved materialization?
Which cycle was affected?
```

This comes from SourceObservation + SourceSnapshot + PR6 claims/conflicts + review/audit events, not one mutable `updated_at` timestamp.

### 29. Do not create 500 recurring discovery runs when monitoring known sources is sufficient

At steady state, known official sources are the first maintenance frontier.

PR5 web discovery is invoked only when needed, for example:

- source moved/disappeared;
- new cycle expected but known source remains old;
- completeness gap has no adequate known source;
- new institution/programme coverage must be expanded;
- owner/domain relationship changed.

This preserves both cost and precision.

### 30. Monitoring order at scale is priority-driven

A maintenance scheduler should prioritize approximately by:

```text
critical current-cycle deadline risk
> active/open scholarship Tier 1 freshness
> detected source change awaiting resolution
> expected cycle rollover
> conflict recheck
> completeness gaps
> structural list freshness
> stable identity maintenance
```

Tie-breakers remain deterministic and fairness/age-aware so low-priority scholarships are not starved indefinitely.

### 31. Failure isolation is per source/task

One broken government site must not fail the entire 500-scholarship maintenance run.

Each source/task has:

- independent lease;
- bounded retry/backoff;
- terminal reason codes;
- next check time;
- metrics.

Global runs aggregate outcomes but do not use one giant transaction.

### 32. Metrics measure maintenance efficiency, not activity volume

Key counters:

```text
source_observations_total
source_unchanged_total
source_changed_total
source_relocated_total
source_unavailable_total
snapshots_reused_total
snapshots_created_total
refresh_tasks_created_total
refresh_tasks_completed_total
refresh_tasks_failed_total
cycle_rollover_checks_total
new_cycle_proposals_total
new_cycles_confirmed_total
material_fact_changes_total
no_material_change_after_reextract_total
targeted_rediscovery_total
```

Key ratios/histograms:

```text
unchanged_source_ratio
AI/extraction calls per monitored source
cost per material catalogue change
refresh task latency
change-to-review latency
cycle detection lead time
percentage of new-cycle facts reused vs newly verified (reported by dimension, not as truth confidence)
```

Do not put URL/domain/scholarship IDs in low-cardinality telemetry labels.

### 33. Gold/regression cases for lifecycle maintenance

Before autonomous maintenance, prove at least:

1. unchanged exact snapshot for months -> zero AI re-extraction;
2. changed footer/noise normalization -> no false material graph change;
3. changed deadline only -> only deadline claim/materialization changes;
4. changed funding only -> previous deadline remains untouched;
5. old cycle 2026 remains after 2027 creation;
6. 2027 deadline does not overwrite 2026 deadline;
7. past cycle close with no new evidence -> "next cycle unconfirmed", not invented 2027;
8. same new cycle detected twice -> one cycle proposal/accepted cycle;
9. deadline correction within same cycle -> same cycle, new fact version;
10. source redirect same owner + same content -> relocation without AI;
11. source redirect different/unresolved owner -> fail closed + rediscovery;
12. 404 temporary -> backoff, no scholarship deletion;
13. persistent source loss -> targeted rediscovery, same scholarship identity;
14. new PDF URL -> same scholarship, source added/replaced, not new candidate;
15. old-cycle eligibility cannot satisfy current-cycle eligibility when policy requires current proof;
16. stable provider identity is not duplicated into every cycle;
17. institution local deadline refresh does not invalidate global deadline;
18. changed one source does not re-extract other unchanged sources;
19. duplicate monitor workers seeing same new hash create one snapshot/refresh task;
20. human `last_verified_at` does not pretend to be machine observation time;
21. effective freshness can carry forward identical reviewed bytes when policy allows;
22. one failed source does not abort other maintenance tasks.

## Implementation sequence impact

### PR5

Remain focused on discovery of missing/moved official sources. No full refresh engine implementation is required in PR5.

Ensure PR5 objectives support:

```text
FRESHNESS_REFRESH
SOURCE_RELOCATION
CYCLE_ROLLOVER / CURRENT_CYCLE_SOURCE
```

as public catalogue objectives without applicant data.

### PR6

Implement evidence bundles/claims/conflict resolution **with incremental comparison in mind**:

- per-source snapshot membership;
- claim fingerprints;
- old/new claim comparison;
- affected semantic claim keys;
- field/scope-local graph materialization;
- no multi-page synthetic concatenation.

PR6 should not require re-extracting unchanged snapshots.

### PR6/PR8 bridge

Add/harden:

```text
SourceObservation
full normalized snapshot monitoring
CycleIdentityResolver
current-cycle transition service
refresh task model/repository
```

Exact migration grouping can be adjusted to keep PR sizes reviewable.

### PR8

Implement autonomous maintenance orchestration:

```text
monitor
 -> refresh task
 -> changed-source re-extract
 -> completeness
 -> targeted discovery if needed
 -> cycle rollover checks
```

with catalogue-only permissions, leases, budgets, retry/backoff, and exception queues.

### PR9

Scale proof must include steady-state maintenance economics, not only initial acquisition:

```text
flagship
 -> 30
 -> 100
 -> 500
```

Measure:

- percentage unchanged;
- changed source rate;
- AI calls avoided by snapshot reuse;
- cost per maintained scholarship/month;
- source failures;
- cycle-rollover accuracy;
- review workload per material change.

## Consequences

### Positive

- 500 scholarships do not become 500 annual re-ingestion projects.
- Historical cycles are never destroyed by current-year updates.
- The common unchanged path is cheap and AI-free.
- Changed pages are processed locally and idempotently.
- New cycles start from trusted structure while requiring fresh proof for volatile facts.
- URL changes do not inflate scholarship count.
- Review workload becomes delta-focused instead of full-record-focused.
- PR6 evidence architecture is designed correctly for future maintenance from day one.

### Cost

- We need a lightweight source-observation ledger and explicit published-record refresh lifecycle.
- Cycle resolution/current-cycle transitions require stronger invariants than the legacy model currently enforces.
- Some unchanged content may still require periodic human/policy reverification depending on field class; identical bytes are not a universal exemption from governance.
- Changed sources require re-extraction even when most fields ultimately remain unchanged, because skipping changed content could miss newly introduced restrictions/cycles.

These costs are accepted because incremental, historically correct maintenance is mandatory for a durable scholarship intelligence catalogue.
