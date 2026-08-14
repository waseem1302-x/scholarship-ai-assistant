# Fresh final audit after Weakness 145

Audit date: 14 August 2026. Audited release tree: `b3e09e5667312171492abd25428d7f9d22f1d059`.

This audit restarted from the final merged tree rather than assuming that the 145-item remediation
plan was complete. It checked live GitHub state, exact post-merge workflow runs, application and
release trust boundaries, dependency/build reproducibility, data rights, tenant isolation,
concurrency patterns, frontend request/navigation behavior, and scaling-sensitive query surfaces.

## FRESH-001 — migration workflow could accept an older successful execution

1. **Problem:** The staged workflow started a Container Apps job and then polled the latest listed
   execution. Before the new execution became visible, a prior successful execution could be
   selected.
2. **Current implementation:** Both preflight and Alembic stages used an unbound `execution list`
   query.
3. **Validity:** Valid and release-blocking.
4. **Root cause:** Job start and job observation were correlated by recency instead of identity.
5. **Security/reliability/performance impact:** A release could continue without proving that its
   candidate binary or migration actually succeeded. Runtime performance is unaffected.
6. **Scaling impact:** More releases and retained executions make the race more likely.
7. **Mobile impact:** A bad schema promotion can break older mobile API clients and rollback.
8. **Options:** Delete old executions; add sleeps; compare timestamps; capture the execution name
   returned by Azure and poll that exact identity.
9. **Recommendation:** Capture `az containerapp job start --query name` and use
   `job execution show --job-execution-name` until terminal state.
10. **Why simplest scalable:** It uses Azure's native execution identity and requires no new
    service, database, or lock.
11. **Files:** Azure application deployment workflow and delivery-policy regression test.
12. **Migration implications:** None; this corrects observation of the existing migration job.
13. **Backward compatibility:** No API or schema change.
14. **Regression risk:** Azure CLI syntax drift; the command is covered by the pinned CLI version,
    workflow policy test, and staging execution proof.
15. **Tests:** Assert both job stages bind the returned execution name and ban latest-run polling.
16. **CI:** YAML/policy tests and Bicep validation; actual Azure staging remains required.
17. **Decision:** **FIX** before staging.

## Residual external and product-data conditions

- **Weakness 124:** `main` remains unprotected. Private-repository protection requires an account
  plan that supports it. Keep the repository private and enable required PR checks after upgrade.
- **Weakness 127:** GitHub reports zero Environments. Create `azure-staging` and `azure-beta` with
  environment-scoped OIDC and required beta approval.
- **Weakness 131:** The Azure application-deployment workflow has zero executions. Workflow and
  Bicep validation are not deployment evidence.
- **Weakness 142:** Incomplete catalogue records remain informational/draft. Official-source rule
  curation is required before those records can become decision-ready; the software must not invent
  missing facts.

The repository also retains obsolete audit branches and PR #4. They are housekeeping rather than a
runtime defect; close/delete them only after confirming that no independent history must be kept.

## Non-blocking scale follow-up

Account export intentionally has no fixed row truncation for data-rights completeness and currently
builds the response synchronously. This is acceptable for closed-beta data volumes, but should move
to a rate-limited background export with encrypted expiring object storage before individual account
histories become large enough to exceed normal request memory or timeout budgets.

## Launch disposition

**NO-GO for Azure staging execution** until FRESH-001 is merged and exact post-merge CI passes.
After that code gate, staging still requires the repository Environments/OIDC configuration above.
Closed-beta release approval additionally requires a successful staging deployment, tenant smoke,
rollback drill, PITR restore, and the planned load/stress/spike/soak evidence.
