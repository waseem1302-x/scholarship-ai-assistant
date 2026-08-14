# Concurrency-control standard

Concurrency is selected per invariant; there is no universal application lock.

| Invariant | Required primitive | Client outcome |
|---|---|---|
| one refresh rotation | conditional SQL update in one transaction | one success; reuse/race rejected |
| one Application version | optimistic `UPDATE ... WHERE version = expected` | `409` with stable code |
| one worker claim | atomic PostgreSQL `UPDATE ... RETURNING`/skip-locked pattern | one claimant |
| one audit-chain append | transaction-scoped PostgreSQL advisory lock | ordered immutable append |
| one idempotent reminder/action | unique idempotency key plus transaction | existing result/no duplicate |
| shared abuse/cost quota | atomic Redis script | `429` with `Retry-After` |
| tenant access | transaction-scoped tenant context plus PostgreSQL RLS | no row visibility/mutation |

Rules:

1. never implement read-check-write for a uniqueness or capacity invariant;
2. never rely on process memory when more than one replica can run;
3. keep transactions bounded and do not call remote providers while holding database locks;
4. return stable conflict/idempotency codes so web and mobile clients can retry safely;
5. test the real primitive with simultaneous PostgreSQL/Redis clients; SQLite tests are unit evidence
   only and cannot close a concurrency or RLS regression;
6. make retry, timeout, and failure behavior explicit before introducing a distributed lock.
