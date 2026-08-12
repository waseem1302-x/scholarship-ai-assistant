# Phase 4 milestone 1: matching evaluation records

Every match request creates an immutable evaluation record with a matcher version,
evaluation time, and a canonical snapshot of the matching inputs. The snapshot hash
allows identical inputs to be identified without exposing them in logs or analytics.

Each result stores the evaluated opportunity, effective cycle, official-source/excerpt
reference, score, eligibility state, confidence, stable rank, and a frozen public
opportunity/source snapshot. Each rule considered is stored with a machine-readable
outcome and reason code. Later Phase 4 milestones will enrich these outcome records
with rule-specific comparisons and source excerpts.

## Retention and privacy

- Evaluation records are user-owned and are deleted with the user account.
- Snapshots contain matching inputs only; passwords, email address, sessions, and
  account-security data are never copied.
- Records have a 365-day expiry and `MatchEvaluationRepository.purge_expired` is the
  retention boundary for the scheduled cleanup introduced in the safeguards milestone.
- Snapshot values must not be included in audit logs, analytics, or error messages.
- Historical records preserve their snapshots if a mutable profile, opportunity, or
  source record is later changed or removed.
