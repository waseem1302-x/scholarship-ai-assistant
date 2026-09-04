# Catalogue Completeness Design

## Goal

Add an opt-in catalogue completeness mode that exhausts the relevant, authorized official-source
frontier and extracts every supported fact with exact persisted evidence. Fixed page and per-job
token ceilings must not silently turn into incomplete results. A run may stop only when coverage is
resolved, an explicit access limitation is recorded, or the approved emergency budget is reached.

## Completeness contract

A candidate is 100% complete only when:

1. Every reachable and authorized official link judged relevant to the scholarship has been fetched,
   deduplicated, or recorded with a specific rejection/failure reason.
2. Every supported extraction objective is `complete`, `not_stated`, or `not_applicable` for the
   acquired corpus. `partial` coverage and unknown objectives remain visible and prevent a 100%
   result.
3. Every accepted claim cites an exact span in an immutable source artifact.
4. Every resumable extraction job is terminal; no candidate may finish with a `running` job.
5. A non-empty proposal and its coverage report are staged for human review. Completeness mode never
   auto-publishes.

This contract covers public material reachable within configured official-domain authority. It does
not claim completeness for login-only pages, CAPTCHA-protected pages, robots-disallowed material, or
unapproved external domains. Those boundaries are explicit unresolved reasons rather than inferred
facts.

## Runtime mode and safety

Completeness mode is opt-in through catalogue settings so existing bounded production behavior remains
unchanged. In completeness mode:

- accepted-page count is not a normal stopping condition;
- the crawler continues until its relevant frontier is empty;
- provider input is divided into deterministic evidence spans instead of dropping evidence;
- truncated or deterministically invalid bundle output is retried through smaller evidence spans;
- the approved emergency ceilings are 500 physical model calls and USD 5 per scholarship;
- provider context/output limits, URL safety, domain authority, byte limits, and evidence validation
  remain enforced.

An emergency frontier ceiling remains configurable to prevent malformed sites from generating an
infinite URL space. Reaching it produces `budget_exhausted` and cannot be reported as complete.

## Acquisition changes

The crawler will reject known non-content static resources before they enter the fetch frontier and
deprioritize unlabeled links. This prevents JavaScript, CSS, calendar-feed, and blank application
resource links from outranking labelled scholarship, eligibility, funding, rules, programme, and
document links. The rule is generic and must not contain Open Doors host-specific logic.

Completeness mode uses a high emergency frontier limit while removing accepted-artifact count as the
normal stop. Existing URL deduplication, content deduplication, depth, authority, MIME, byte, and
per-host controls stay active. Persisted fetched artifacts and acquisition snapshots are reused on
resume, so provider deferral cannot trigger a second crawl or repeat PDF OCR.

## Extraction changes

The existing strict validator remains authoritative. It will not be weakened to manufacture a
proposal. When a paid bundle result fails deterministic evidence validation:

1. Persist the validated raw structured output, exact validation warnings, provider-attempt identity,
   evidence spans, and objective bundle in the existing quarantine event JSON.
2. Mark the current resumable job terminal.
3. If the evidence span can be split further, complete the parent with a deterministic split outcome
   and enqueue its children.
4. If it cannot be split, mark it failed with the exact safe validation detail and continue independent
   jobs so valid evidence is not discarded.

At finalization, terminal failures and partial objective coverage remain explicit. A candidate cannot
receive a 100% completeness result while either exists, but valid extracted claims can still produce a
reviewable partial proposal.

## State and diagnostics

Add one repository transition for owned jobs to `failed`, recording `error_code`, bounded safe detail,
checkpoint, and `completed_at`. Schema/provider failures that currently leave jobs running use this
transition. Deferred work remains resumable and therefore may stay running only while its candidate is
scheduled for retry.

Quarantine diagnostics use the existing JSON event column, so no database migration or new subsystem
is required.

## Testing

Development follows red-green TDD for:

- artifact reuse on direct-run resume;
- failed-job terminal state and diagnostic persistence;
- deterministic validation split/retry and terminal fallback;
- quarantine output/error retention;
- generic non-content link filtering and unlabeled-link ranking;
- completeness-mode acquisition budget behavior;
- completeness reporting refusing 100% when any frontier/objective/job remains unresolved.

Run focused tests after each change. Run the full backend suite, frontend tests, frontend production
build, and Ruff before the implementation commit. No additional paid live call is part of this change;
the next Open Doors call requires a separate explicit run after local verification.

## Out of scope

Cost optimization, infrastructure redesign, framework/library replacement, broad code-quality
refactoring, and automatic external-domain expansion belong to the later optimization phase requested
by the user. They are not mixed into this completeness implementation.
