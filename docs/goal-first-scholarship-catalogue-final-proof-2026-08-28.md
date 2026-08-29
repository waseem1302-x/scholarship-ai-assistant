# Goal-first scholarship catalogue proof

Date: 2026-08-28 (Asia/Singapore)

## Outcome

The catalogue pipeline successfully completed a bounded, multi-page ingestion of the
Chinese Government Scholarship Program from the official HEC source bundle.

- Run: `0abb9fa2-6e32-403a-84f5-c6873ede1dad`
- Candidate: `edfb2233-3a91-43df-bbd7-1d8868573c53`
- Run status: `completed`
- Candidate status: `ready_for_review`
- Official sources fetched: 13 pages/PDFs/image resources
- Official sources contributing accepted evidence: 10
- Objective coverage: 12/12 complete
- Accepted facts: 453
- Exact citation spans: 453/453
- Validation errors: 0
- Conflicts: 0
- Completeness errors: 0
- Additional model calls for the definitive rerun: 0 (verified cached output was reused)

## Student-facing result

The result contains scholarship identity and cycle; five correctly separated programme
categories; application tracks and steps; eligibility; required documents and their
conditions; funding components; deadlines/events; and official resources.

Programme categories:

- Undergraduate / Bachelor's: 4-5 years
- Master's: 2-3 years
- Doctoral / PhD: 3-4 years
- General Scholar: non-degree
- Senior Scholar: non-degree

Funding includes tuition/fees, accommodation, monthly stipend, travel responsibility,
and the HEC financial-liability disclaimer. The application data includes both the HEC
and CSC portal routes. A final exact-evidence rule also retains plain-text official URLs
from government pages and PDFs, including the HEC portal, CampusChina portal, university
index, and CSCA site; invented URLs remain quarantined.

## Corrections implemented

- Decode HTML entities before source-text normalization so programme tables retain word
  boundaries.
- Normalize scalar programme fields to their list schema.
- Prevent prerequisite degrees from being mistaken for the degree being offered.
- Infer explicit General/Senior Scholar categories as non-degree.
- Preserve duration units supplied by table headers.
- Remove unsupported programme scope from general funding statements.
- Merge same-degree programme aliases using official-source authority.
- Quarantine scholarship-title-as-programme, placeholder, non-discipline, invalid-route,
  invalid deadline/event, and unsupported resource claims.
- Reapply current canonicalization at the resolver boundary so historical cached model
  results and fresh model results produce the same graph.
- Accept a resource URL only when it is a fetched link, the source itself, or occurs
  verbatim in the claim's exact cited evidence.

## Verification

- 173 relevant backend tests passed across ingestion, routing, browser acquisition,
  bounded crawling, and source normalization.
- Ruff passed for every tracked Python file.
- All 281 tracked Python files compiled successfully.
- `git diff --check` passed (line-ending notices only).
- Focused resource and programme regression tests passed in the project virtualenv.
- The final catalogue-worker Docker image was rebuilt successfully.
- The local catalogue kill switch is armed.
- The stopped temporary capability-probe container was removed.
- No commit or push was performed.

## Scope

This is strong end-to-end evidence for a complex official multi-page/PDF source family,
alongside the earlier MEXT PDF and Commonwealth HTML proofs. It does not mean that all
500 future scholarship websites have already been individually validated. Bulk launch
still requires a curated seed set, batch execution, and review of site-specific failures.
