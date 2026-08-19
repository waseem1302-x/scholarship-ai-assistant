# ADR 0011: Monitor scholarship sources around lifecycle events, not on a fixed daily/weekly polling interval

- Status: Accepted for architecture; implementation belongs to the PR6/PR8 maintenance bridge
- Date: 2026-08-19
- Applies to: source monitoring cadence, cycle rollover, deadline extension detection, freshness scheduling, and maintenance cost control
- Related: ADR 0008, ADR 0010, `app/modules/opportunities/source_monitor.py`, `infra/azure/scheduled-jobs.bicep`

## Context

The live repository currently has a source-monitor dispatcher scheduled once per day and a source-level default monitoring interval of seven days.

That was a reasonable initial safety mechanism, but it is not the desired steady-state policy for a catalogue containing hundreds of scholarships and potentially thousands of official sources.

A scholarship source whose current verified deadline is 20 May does not need to be fetched every seven days from January through May merely to discover that the page remains unchanged.

Likewise, after the deadline is confirmed closed and the next cycle is not expected for many months, continued weekly polling wastes network traffic and operational capacity.

The system already has the correct primitive for sparse monitoring:

```text
Source.monitor_next_check_at
```

The scheduler can wake regularly, select only sources whose `monitor_next_check_at <= now`, and perform zero network requests for every other source.

Therefore the distinction is:

```text
scheduler wake frequency != source fetch frequency
```

A lightweight dispatcher may wake daily so one shared job can service every scholarship without provisioning hundreds of independent Azure jobs. The actual source fetch cadence should be event-relative and scholarship-specific.

## Decision

### 1. Replace the fixed successful-check interval with `MonitoringSchedulePolicy`

After each successful observation, do not simply set:

```text
next_check_at = observed_at + 7 days
```

Instead calculate the next meaningful lifecycle checkpoint.

Conceptual interface:

```python
@dataclass(frozen=True)
class MonitoringDecision:
    next_check_at: datetime | None
    reason_code: str
    priority: int
    policy_version: str

class MonitoringSchedulePolicy(Protocol):
    def next_check(
        self,
        *,
        source: Source,
        scholarship: Opportunity,
        current_cycle: OpportunityCycle | None,
        source_scope: GraphScope,
        now: datetime,
    ) -> MonitoringDecision: ...
```

Initial policy version:

```text
scholarship-monitoring.v1
```

The decision is deterministic from reviewed catalogue state; an LLM does not choose monitoring dates.

### 2. Keep one low-cost dispatcher, but fetch only due sources

The Azure job may continue to wake once daily as a dispatcher.

Its work is:

```text
wake
 -> query due source rows
 -> if none due: exit
 -> safely fetch only due rows
 -> calculate each source's next event-relative checkpoint
```

A daily dispatcher is operationally simple and does **not** mean daily monitoring of every scholarship.

At steady state most scholarships should produce no network activity on most days.

### 3. Baseline observation occurs when a cycle/source is first verified

When the platform first accepts a current-cycle source, that acquisition/verification already acts as the baseline snapshot.

Do not immediately schedule another routine fetch merely because the source was newly added.

Calculate the next relevant event from its known opening/deadline/cycle state.

### 4. Deadline-critical sources use event checkpoints

For a verified fixed deadline `D`, the default v1 deadline checkpoints are:

```text
D - 30 days   EARLY_DEADLINE_RECHECK
D - 7 days    PRE_DEADLINE_RECHECK
D - 1 day     FINAL_DEADLINE_RECHECK
D             DEADLINE_DAY_RECHECK
D + 1 day     POST_DEADLINE_EXTENSION_RECHECK
```

A sixth checkpoint:

```text
D + 7 days    EXTENSION_FOLLOWUP
```

is created **only if** the `D`/`D+1` observation leaves closure/extension state unresolved, the official source remains open/ambiguous, or a material change was detected.

Why include `D-30` and `D-1` in addition to the user's proposed `D-7 / D / D+1`:

- `D-30` catches a material deadline change before the final week;
- `D-1` protects against last-minute changes/extension announcements;
- these are still sparse event checks, not routine polling.

The exact checkpoint list is policy-versioned and can be tuned from production evidence.

### 5. Collapse redundant deadline checkpoints

Do not fetch the same source twice merely because two policy checkpoints fall near each other.

Rules:

- if the baseline acquisition occurred after `D-30`, treat the baseline as satisfying the early checkpoint;
- if the application window is shorter than 30 days, omit checkpoints already in the past;
- if multiple due reasons fall on the same calendar day for the same source, one fetch satisfies them all;
- enforce one successful routine observation per source per policy-defined minimum interval unless an explicit failure/change follow-up requires otherwise.

### 6. Opening/cycle checks are also event-relative

For a confirmed opening date `O`, default checkpoints are:

```text
O - 30 days   PRE_OPENING_CYCLE_CHECK
O - 7 days    PRE_OPENING_RECHECK
O             OPENING_DAY_RECHECK
O + 1 day     POST_OPENING_CONFIRMATION
```

These checks focus on sources authoritative for:

- current/new cycle announcement;
- application opening status;
- current application guidance;
- deadline/route changes that accompany a newly opened cycle.

If current-cycle evidence is already freshly established by an acquisition/refresh inside one of these windows, the equivalent scheduled checkpoint can be suppressed.

### 7. Historical cadence schedules the *search for* a new cycle; it never invents one

After the current cycle closes and no next cycle is confirmed:

1. preserve the closed cycle;
2. estimate an expected next-opening window from reviewed historical cadence only when there is enough history;
3. schedule the first cycle-rollover check approximately 30 days before that expected opening;
4. use PR5 domain-constrained discovery/known official sources to look for current evidence;
5. create no new cycle unless official evidence supports it.

Example:

```text
2026 opening: 1 March
2027 not yet published

scheduler may check around 1 February 2027
```

but it may not create `2027 opening = 1 March` from historical repetition.

### 8. If a next cycle is still unconfirmed, increase checks only near the expected window

When `PRE_OPENING_CYCLE_CHECK` finds no current cycle evidence:

```text
expected opening - 30d
 -> expected opening - 14d
 -> expected opening - 7d
 -> expected opening day
 -> +1d
 -> then bounded fallback cadence
```

The fallback cadence should be modest (for example weekly only during the narrow unresolved opening window), not year-round polling.

Once the new cycle is confirmed, replace the unresolved schedule with the actual new cycle's checkpoints.

### 9. After a deadline is conclusively closed, stop routine deadline polling

If the official source at `D` or `D+1` confirms the cycle is closed and no extension is indicated:

```text
no more deadline checks for that cycle
```

Next monitoring is driven by:

- expected next-cycle opening;
- a separate stable-source governance check if policy requires it;
- explicit source failure/relocation;
- a manual/review objective;
- another scoped event (institution/programme deadline, for example).

This is the main steady-state cost reduction.

### 10. Deadline extension changes the schedule immediately

Suppose current deadline is:

```text
20 May
```

and the `20 May` or `21 May` observation finds an official extension to:

```text
31 May
```

Then:

1. create a new immutable snapshot;
2. run the PR6 field-resolution path;
3. keep the old 20 May fact historically auditable;
4. after approval/materialization, recompute monitoring checkpoints around 31 May;
5. do not continue using the old 20 May schedule.

The scheduler always derives future checks from the current resolved effective fact.

### 11. A deadline may move earlier; this is why one earlier checkpoint exists

Only checking at `D-7` can be unsafe.

Example:

```text
published deadline = 20 May
provider changes it on 1 May to 10 May
```

A first recheck on 13 May would discover the change too late.

The `D-30` checkpoint provides an early guard without falling back to daily/weekly monitoring throughout the cycle.

For especially volatile/high-risk providers, a future reviewed source policy may add one mid-window checkpoint. This must be explicit and measured, not globally applied.

### 12. Application-open periods do not automatically imply periodic weekly checks

Once an opening-day observation establishes the current application window, do not poll every seven days simply because the scholarship is open.

The next check should normally be the next deadline-relative checkpoint.

Example:

```text
opens 1 February
closes 20 May

baseline/opening confirmed 1 February
next relevant routine check ~= 20 April (D-30)
```

unless:

- a source is known to be volatile;
- a prior observation changed;
- a conflict/completeness gap exists;
- another scoped event occurs sooner.

### 13. Monitoring is per source and per scope, not one schedule per scholarship card

A scholarship can have:

```text
provider global deadline
embassy route deadline
institution deadline
programme deadline
```

Each authoritative source/scope has its own event dates.

Example:

```text
MEXT global/provider source
  -> cycle/opening checkpoints

Malaysia embassy source
  -> Malaysia route deadline checkpoints

University source
  -> university recommendation/local deadline checkpoints
```

One local deadline does not force all MEXT sources to be fetched.

### 14. One source supporting multiple facts gets one consolidated next check

A provider page may support both opening and deadline facts.

The scheduler calculates all relevant future checkpoints and stores the earliest meaningful one:

```text
next_check_at = min(relevant future checkpoints)
```

At that observation, one safe fetch can satisfy every objective due for that source.

After processing, recompute the next earliest checkpoint.

### 15. Changed sources temporarily enter a tighter exception schedule

Event-relative routine monitoring is for stable sources.

If a source changes materially:

```text
CHANGED
 -> immediate RefreshTask
```

After PR6 resolution:

- if change is fully resolved and source stabilizes, return to event-relative schedule;
- if conflict/ambiguity remains, schedule bounded follow-up appropriate to the issue;
- do not permanently switch the entire scholarship to daily monitoring.

### 16. Failed sources use operational backoff independently of lifecycle checkpoints

Network failures, 429, 5xx, blocked sources, and temporary outages follow bounded retry/backoff.

This is separate from scholarship-event cadence.

After recovery, recompute the lifecycle next-check date rather than blindly adding seven days.

Persistent failure can trigger ADR 0010 `SOURCE_UNAVAILABLE` / targeted PR5 rediscovery.

### 17. Rolling scholarships use a separate policy

A genuinely rolling scholarship has no fixed closing deadline.

Do not invent deadline checkpoints.

Initial rolling policy should be conservative, for example:

```text
current rolling status confirmed
 -> periodic verification every ~30 days while active
```

plus immediate checks triggered by source change/failure or explicit completeness gaps.

The exact interval is configurable and must be evaluated. Rolling awards are the exception where a periodic interval remains appropriate.

### 18. Unknown-cycle/unknown-deadline scholarships use bounded fallback monitoring

If no reliable event date exists, the scheduler cannot be event-relative yet.

Use a bounded fallback such as:

```text
UNKNOWN_CYCLE -> targeted check approximately every 30 days
```

or more targeted PR5 discovery based on provider/cadence context.

Once event dates become verified, switch to event-relative scheduling.

Do not let `unknown` cause daily fetching.

### 19. Stable identity/owner sources need infrequent governance checks, not deadline cadence

A provider ownership/identity page may remain stable for years.

Its policy can be much slower than deadline sources, for example quarterly/semiannual or tied to next-cycle discovery, depending on the authority/freshness class.

The exact governance interval is policy configuration, not a universal hardcoded number.

### 20. Scheduler decisions should be stored with reason codes

Add/materialize on `Source` or the source-observation/scheduling ledger:

```text
monitor_next_check_at
monitor_next_check_reason
monitor_policy_version
monitor_priority
```

Example reason codes:

```text
PRE_OPENING_CYCLE_CHECK
PRE_OPENING_RECHECK
OPENING_DAY_RECHECK
POST_OPENING_CONFIRMATION
EARLY_DEADLINE_RECHECK
PRE_DEADLINE_RECHECK
FINAL_DEADLINE_RECHECK
DEADLINE_DAY_RECHECK
POST_DEADLINE_EXTENSION_RECHECK
EXTENSION_FOLLOWUP
ROLLING_PERIODIC
UNKNOWN_CYCLE_PROBE
CHANGE_FOLLOWUP
FAILURE_RETRY
SOURCE_GOVERNANCE_CHECK
```

This makes every fetch explainable:

> Why did the system hit this official website today?

### 21. Missed scheduler runs remain safe

If Azure/job execution is unavailable on an exact checkpoint date, the next dispatcher run selects overdue sources:

```text
monitor_next_check_at <= now
```

It executes the overdue check once, records lateness/queue lag, then recalculates future checkpoints.

Do not create multiple catch-up fetches for every missed day.

### 22. Event-relative monitoring drastically reduces steady-state volume

Illustrative comparison for 500 scholarships with one deadline source each:

Fixed daily fetching:

```text
500 * 365 = 182,500 fetches/year
```

Fixed weekly fetching:

```text
500 * 52 = 26,000 fetches/year
```

A six-check event policy around one opening/deadline cycle would be on the order of only a few thousand routine fetches/year before accounting for shared-source consolidation, unknown/rolling exceptions, source failures, or extra scoped deadlines.

These numbers are illustrations, not production forecasts; real load must be measured from actual source topology.

### 23. Cost/quality evaluation decides whether checkpoints are removed or added

Monitor:

```text
material_changes_detected_by_reason
changes_detected_at_D_minus_30
changes_detected_at_D_minus_7
changes_detected_at_D_minus_1
extensions_detected_D/D_plus_1
checks_with_no_change_by_reason
late_change_detection_incidents
network/cost per maintained scholarship
```

After enough production evidence:

- remove checkpoints that provide negligible value;
- add a checkpoint for a specific source/provider class if misses occur;
- never globally increase cadence merely because one provider is volatile.

### 24. Required tests

Implementation must prove:

1. a deadline months away is not fetched weekly;
2. a 20 May deadline schedules an early and near-deadline checkpoint;
3. baseline inside the `D-30` window suppresses redundant early check;
4. multiple same-day reasons produce one fetch;
5. deadline extension to 31 May replaces future schedule with 31 May-relative checkpoints;
6. conclusively closed cycle stops routine deadline polling after post-deadline verification;
7. no new cycle evidence means no invented next cycle;
8. expected-opening cadence creates a future check, not a scholarship fact;
9. confirmed opening switches from expected to actual cycle dates;
10. rolling scholarship uses rolling policy rather than fake deadline events;
11. unknown-cycle scholarship uses bounded fallback, not daily polling;
12. local institution deadline schedules only its relevant source/scope;
13. changed source gets an exception follow-up but other scholarship sources keep normal cadence;
14. failed fetch uses backoff and then returns to lifecycle scheduling;
15. missed dispatcher day performs one overdue check rather than replaying every missed checkpoint;
16. dispatcher can run daily with zero HTTP fetches when no sources are due;
17. every scheduled check has a reason code and policy version.

## Implementation impact

### Existing daily Azure job

The existing daily `source-monitor` Container Apps job can remain as a dispatcher initially. The important change is **not** the cron expression; it is how `monitor_next_check_at` is computed.

This avoids creating hundreds/thousands of Azure schedules while still producing sparse network activity.

### Existing `SourceMonitor`

Replace the successful-path fixed:

```text
observed_at + check_interval_days
```

with a call to `MonitoringSchedulePolicy`.

Retain failure backoff as a separate operational mechanism.

### ADR 0010

ADR 0010 remains the lifecycle/refresh architecture. This ADR refines its cadence rule: steady-state known-source maintenance is event-relative rather than fixed periodic polling.

### PR6/PR8

PR6 provides the field-level change/evidence consequences of a changed checkpoint.

PR8 provides the autonomous scheduler/orchestrator and cycle-rollover behaviour.

## Consequences

### Positive

- stable scholarships are not needlessly fetched every day/week;
- monitoring effort concentrates around the dates where student harm from stale information is highest;
- deadline extensions are explicitly checked;
- next-cycle discovery begins before expected opening without inventing future facts;
- one lightweight dispatcher can manage thousands of independently scheduled sources;
- monitoring volume/cost scales with lifecycle events and actual changes rather than catalogue size * calendar days.

### Cost

- monitoring policy becomes a real deterministic subsystem rather than one interval setting;
- irregular/rolling scholarships need explicit fallback policies;
- an event-relative model can miss unexpected mid-cycle changes, so the early deadline checkpoint and exception/provider-specific policies are important;
- production metrics are required to tune checkpoint spacing safely.

These costs are accepted because lifecycle-relative monitoring is substantially more efficient and more meaningful than fixed polling for a mature scholarship catalogue.
