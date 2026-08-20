# ADR 0006: Preserve provider-call history and enforce discovery budgets atomically

- Status: Accepted for PR5 design
- Date: 2026-08-19
- Applies to: PR5 discovery persistence, provider retries, cost accounting, concurrency, and audit durability
- Related: ADR 0002–0005, `docs/pr5-web-discovery-spec.md`, `docs/pr5-implementation-sequence.md`

## Context

The current PR5 design has durable discovery runs and queries, but a mutable query row by itself is not enough to audit external provider behavior.

Example:

```text
attempt 1 -> Azure 429
attempt 2 -> timeout
attempt 3 -> success
```

If `catalogue_discovery_queries` stores only the latest `provider_response_id`, `failure_code`, counters, and status, the first two provider calls disappear from the durable record. That makes it impossible to reconstruct:

- why a query retried;
- how many billable/tool calls occurred;
- how latency changed across attempts;
- whether a provider capability failure was intermittent or systematic;
- whether the configured budget was actually respected.

A second issue is concurrency. A naive sequence:

```text
check remaining budget
 -> call provider
 -> increment counters
```

can overspend if two workers both observe the same remaining budget before either increments it.

A third issue is durability semantics. Discovery observations, officiality assessments, and promotions are provenance records. Cascading or silently mutating them would weaken the audit trail, but copying the security-audit hash chain to every discovery row would add unnecessary write serialization and complexity.

The repository already demonstrates two useful patterns:

- PostgreSQL `FOR UPDATE SKIP LOCKED` leases for catalogue workers;
- database/application immutability for security audit records where tamper resistance is essential.

PR5 needs the first pattern directly and a lighter version of the second: immutable business provenance, without a global cryptographic chain.

## Decision

### 1. Add a provider-call attempt ledger

PR5 adds:

```text
catalogue_discovery_attempts
```

One row represents one outbound Responses/Web Search provider request attempt for one planned discovery query.

Recommended schema:

```text
id UUID PK
query_id UUID NOT NULL
attempt_number int NOT NULL
status varchar(32) NOT NULL
request_fingerprint varchar(64) NOT NULL
provider varchar(100) NOT NULL
model varchar(255) NOT NULL
provider_response_id varchar(255) NULL
http_status int NULL
web_search_executed bool NULL
tool_call_count int NOT NULL default 0
result_url_count int NOT NULL default 0
response_bytes int NOT NULL default 0
input_tokens int NULL
output_tokens int NULL
estimated_model_cost numeric(12,6) NOT NULL default 0
estimated_tool_cost numeric(12,6) NOT NULL default 0
estimated_total_cost numeric(12,6) NOT NULL default 0
latency_ms int NULL
error_code varchar(100) NULL
started_at timestamptz NOT NULL
completed_at timestamptz NULL
```

Constraints:

```text
UNIQUE(query_id, attempt_number)
CHECK(attempt_number > 0)
CHECK(tool_call_count >= 0)
CHECK(result_url_count >= 0)
CHECK(response_bytes >= 0)
CHECK(estimated_model_cost >= 0)
CHECK(estimated_tool_cost >= 0)
CHECK(estimated_total_cost >= 0)
```

Index:

```text
INDEX(query_id, attempt_number)
INDEX(status, started_at)
```

### 2. Attempt rows preserve history but support one bounded in-flight transition

A provider call must be recorded **before** network I/O so a process crash does not make the call invisible.

Attempt lifecycle:

```text
IN_PROGRESS
  -> SUCCEEDED
  -> RATE_LIMITED
  -> TIMEOUT
  -> PROVIDER_FAILED
  -> RESPONSE_INVALID
  -> TOOL_NOT_EXECUTED
  -> CAPABILITY_UNAVAILABLE
  -> BUDGET_REJECTED
  -> ABANDONED
```

`IN_PROGRESS` is the only non-terminal state.

Allowed mutation:

- insert once as `IN_PROGRESS`;
- update exactly once to one terminal state with normalized result/cost metadata;
- never rewrite one terminal outcome into another.

Recovery may mark an expired `IN_PROGRESS` attempt as `ABANDONED` after the owning query lease expires. It must create a **new attempt number** for the retry.

This gives crash visibility without requiring two separate start/end event tables.

### 3. Never persist the full grounded answer or raw provider body by default

Attempt rows store normalized operational metadata only.

Do not persist:

- generated answer prose;
- search snippets as evidence;
- complete raw Responses payloads;
- access tokens;
- authorization headers;
- request headers containing credentials;
- applicant/private context.

The query row already contains the public query text. The attempt stores only a `request_fingerprint` plus bounded provider/model/tool/usage metadata.

When a fixture is needed for CI, keep reviewed synthetic/frozen response fixtures in the repository test suite; do not turn production rows into raw-response archives.

### 4. Query rows are current-state aggregates; attempts are the call history

`catalogue_discovery_queries` remains mutable for efficient worker claiming and administration:

```text
status
attempt_count
next_attempt_at
claimed_by
claimed_until
provider_call_count
response_bytes
latency_ms
estimated_cost
failure_code
completed_at
```

These are current/aggregate values.

For any audit question about a concrete provider call, `catalogue_discovery_attempts` is authoritative.

Query aggregate counters must reconcile with attempt rows in tests.

### 5. Reserve provider-call budget atomically before network I/O

Do not rely on a read-then-write budget check.

Before creating an `IN_PROGRESS` attempt, lock the parent discovery run row or use one atomic conditional update.

The transaction must reserve at least:

```text
1 provider request
1 configured maximum web-search/tool-call allowance for that request
configured worst-case estimated cost reservation for the request
```

Recommended run counters:

```text
provider_calls_reserved int default 0
provider_calls_completed int default 0
estimated_cost_reserved numeric(12,6) default 0
estimated_cost_settled numeric(12,6) default 0
```

A reservation succeeds only if the post-reservation totals remain within the run's hard limits.

No provider request occurs unless reservation commits successfully.

### 6. Settle reservations transactionally after each attempt

When an attempt becomes terminal:

1. record actual normalized tool-call count/usage/cost estimate available from the response;
2. release the unused portion of the reservation;
3. move the reserved provider call into completed accounting;
4. update query aggregate counters/status;
5. update run aggregate counters.

All five changes occur in one database transaction.

If the process crashes after the provider returns but before settlement, recovery treats the attempt conservatively: the reservation remains consumed until the stale attempt is reconciled. This may temporarily under-use budget but must never allow overspend.

### 7. Add an explicit per-request worst-case reservation setting

A hard run cost ceiling cannot be guaranteed if the system has no upper bound for one additional request.

Add configuration conceptually equivalent to:

```text
APP_CATALOGUE_DISCOVERY_MAX_ESTIMATED_COST_PER_PROVIDER_REQUEST=<reviewed positive value>
APP_CATALOGUE_DISCOVERY_MAX_TOOL_CALLS_PER_PROVIDER_REQUEST=1
```

PR5 should target one bounded web-search action per deterministic query request.

The Azure Responses request should use the supported tool-call limiting control when the target runtime proves it is honored. The provider parser must also count actual `web_search_call` actions and fail closed if the response exceeds PR5's configured contract.

Runtime capability proof remains mandatory because Microsoft documentation for Azure Web Search capability is not fully consistent across current pages.

### 8. Provider-call count and web-search/tool-call count are different budgets

Track both:

```text
provider HTTP/Responses requests
web search tool calls/actions
```

One provider request may not be assumed to equal one billable search action unless the runtime response proves it.

Metrics and cost accounting must distinguish them.

### 9. Discovery provenance is immutable business history, not a global cryptographic chain

These rows are insert-only business provenance after creation:

```text
catalogue_discovery_observations
catalogue_discovery_assessments
catalogue_discovery_promotions
```

Rules:

- no normal service method updates/deletes an observation;
- an assessment change creates a new assessment with `supersedes_assessment_id`;
- a promotion is an event and is never edited into another outcome;
- no production admin API for deleting these rows in PR5.

Application-level ORM/service guards should reject mutation of assessments/promotions after insert.

PostgreSQL database triggers may additionally reject UPDATE/DELETE on **assessments and promotions**, because those rows represent trust/promotion decisions and have no legitimate in-place lifecycle. SQLite tests retain application-level guards.

A security-style global integrity hash chain is intentionally not added; discovery writes should not serialize all workers behind one global advisory lock.

### 10. Provider attempts are terminal-immutable, not insert-only

`catalogue_discovery_attempts` cannot use a blanket append-only trigger because it legitimately transitions once from `IN_PROGRESS` to terminal.

Application/domain rules must reject:

- terminal -> terminal rewrite;
- terminal -> `IN_PROGRESS`;
- decrementing attempt number;
- changing query/provider/model/request fingerprint after insert.

A later hardening migration may implement a PostgreSQL trigger that permits only the defined one-way transition if production experience justifies it.

### 11. Foreign-key deletion rules must preserve trust history

Refine the initial PR5 schema as follows.

#### Discovery run target

```text
target_candidate_id
  FK -> catalogue_candidates.id
  ON DELETE SET NULL
```

The immutable `target_identity_snapshot` preserves the public identity context if an unpromoted historical candidate is later removed.

#### Queries

```text
query.run_id -> discovery_runs.id ON DELETE CASCADE
```

A run with no durable downstream provenance may be cleaned up later by an explicit retention policy.

#### Attempts

```text
attempt.query_id -> discovery_queries.id ON DELETE RESTRICT
```

Once a provider request occurred, deleting the query/run must not silently erase billable operational history.

#### Leads

Referenced discovery leads use `ON DELETE RESTRICT` from observations, assessments, and promotions.

#### Observations

```text
observation.query_id -> discovery_queries.id ON DELETE RESTRICT
observation.lead_id  -> discovery_leads.id  ON DELETE RESTRICT
```

#### Assessments

```text
assessment.run_id -> discovery_runs.id ON DELETE RESTRICT
assessment.lead_id -> discovery_leads.id ON DELETE RESTRICT
supersedes_assessment_id -> discovery_assessments.id ON DELETE RESTRICT
```

#### Promotions

```text
promotion.run_id -> discovery_runs.id ON DELETE RESTRICT
promotion.lead_id -> discovery_leads.id ON DELETE RESTRICT
promotion.assessment_id -> discovery_assessments.id ON DELETE RESTRICT
promotion.candidate_id -> catalogue_candidates.id ON DELETE RESTRICT
promotion.candidate_source_id -> catalogue_candidate_sources.id ON DELETE SET NULL
```

Once a discovery lead has been promoted, the candidate/run becomes retention-protected by referential integrity. PR5 adds no production delete operation for promoted discovery history.

This is intentional. Discovery metadata is small public/audit data; correctness is more valuable than prematurely deleting it.

### 12. Do not use cascade deletion as an implicit retention policy

If discovery history eventually requires archival/retention, add an explicit reviewed policy that defines:

- retention horizon;
- which non-promoted runs may be removed;
- which provider-call metadata must remain for cost/audit analysis;
- how promoted-source provenance remains resolvable;
- archival/export strategy if needed.

PR5 does not quietly solve storage growth by cascading away provenance.

### 13. Exact idempotency boundaries

Recommended constraints:

```text
DiscoveryQuery:
  UNIQUE(run_id, ordinal)
  UNIQUE(run_id, query_hash)

DiscoveryAttempt:
  UNIQUE(query_id, attempt_number)

DiscoveryLead:
  UNIQUE(url_fingerprint)
  UNIQUE(normalized_url)

DiscoveryObservation:
  UNIQUE(query_id, lead_id)

DiscoveryAssessment:
  UNIQUE(lead_id, assessment_context_hash, classifier_version)

DiscoveryPromotion:
  UNIQUE(candidate_id, lead_id)
```

An identical assessment context/classifier result is reused. A changed owner/domain/context or classifier version generates a new context hash/assessment.

Two leads that converge through redirects to one final candidate-source URL may both retain their discovery provenance while sharing one effective candidate source after ADR 0003 reconciliation.

### 14. JSON snapshots are bounded typed schemas, never arbitrary ORM dumps

For:

```text
target_identity_snapshot
objective_scope
objective_field_paths
objective_reason_codes
objective_priority_snapshot
public_context
aggregate_summary
```

construct the persisted payload from dedicated Pydantic/dataclass schemas with allowlisted fields and explicit maximum lengths/counts.

Never persist `model_dump()` from broad application/user objects.

This is part of the privacy boundary, not merely input validation.

### 15. Concurrency pattern follows the existing ingestion repository

Query claiming uses the proven pattern:

```text
SELECT ...
FOR UPDATE SKIP LOCKED
LIMIT N
```

with:

```text
claimed_by
claimed_until
attempt_count
next_attempt_at
```

Budget reservation is a separate parent-run lock/atomic conditional step and must occur after claim but before provider call.

A query lease does not itself reserve Azure budget.

### 16. Recovery rules

On worker startup/claim processing:

- expired query leases may be reclaimed;
- an `IN_PROGRESS` attempt whose owning lease is safely expired is marked `ABANDONED` before a new attempt is allocated;
- its reservation remains conservatively consumed until the abandonment/reconciliation transaction settles it according to policy;
- attempt numbers are monotonic per query;
- retries obey both attempt ceiling and `next_attempt_at` backoff;
- terminal non-retryable errors do not return to `PLANNED`.

### 17. Required tests

Implementation must prove:

1. 429 -> retry -> success creates three separate attempt rows;
2. query aggregates reconcile to attempt history;
3. two workers cannot reserve the same final provider-call slot;
4. two workers cannot exceed the run provider-call limit;
5. worst-case cost reservation prevents concurrent overspend;
6. failed reservation produces no outbound provider call;
7. stale `IN_PROGRESS` attempt becomes `ABANDONED` before retry;
8. a terminal attempt cannot be rewritten;
9. no raw grounded prose/search snippet is persisted in attempt rows;
10. no access token/auth header is persisted;
11. observation duplicate is idempotent;
12. identical assessment context is reused;
13. changed classifier/context creates a superseding assessment;
14. assessment/promotion mutation is rejected;
15. promoted history prevents accidental cascade deletion of its run/candidate;
16. candidate-source deletion may null the promotion's source FK without deleting the promotion event;
17. typed JSON snapshot validators reject private/applicant fields and oversize payloads;
18. PostgreSQL `SKIP LOCKED` behavior works under concurrent query claims.

## Consequences

### Positive

- Azure/provider behavior is reconstructable per request.
- Retry history is no longer overwritten.
- Cost limits remain safe under concurrency.
- Search tool calls and provider requests are measured separately.
- Promotion/officiality history cannot be silently rewritten.
- The design remains PostgreSQL-first without adding Redis/Kafka for discovery coordination.

### Cost

- PR5 gains one additional table and reservation counters.
- Provider call finalization needs a transactionally careful settlement path.
- Promoted discovery history is deliberately harder to delete.

These costs are accepted because invisible retries, budget races, and erasable provenance are unacceptable foundations for autonomous acquisition.
