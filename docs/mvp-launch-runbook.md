# Truth-first MVP launch runbook

This runbook publishes the 12 reviewed roots in `data/launch-scholarships.json` to staging and
promotes only a candidate whose catalogue audit and two staging smoke gates pass. Never paste
access tokens, passwords, source excerpts, or database URLs into tickets or release artifacts.

## Before ingestion

1. Confirm the operator is using the staging resource group and immutable candidate image.
2. Confirm the admin account has a current step-up token. Set `STAGING_ORIGIN`, `ACCESS_TOKEN`,
   and `ADMIN_STEP_UP` only in the protected operator shell.
3. For each manifest row, open the official root in a browser and confirm the hostname and
   scholarship identity. Add supporting URLs only when they are official and needed for a scoped
   claim. The manifest is a source list, not permission to invent or copy claims.

The examples below use PowerShell and the authenticated admin API:

```powershell
$headers = @{
  Authorization = "Bearer $env:ACCESS_TOKEN"
  'X-Admin-Step-Up' = $env:ADMIN_STEP_UP
  'Content-Type' = 'application/json'
}
$api = "$env:STAGING_ORIGIN/api/v1/admin/catalogue-ingestion"
```

## Ingest and review every flagship

Perform these steps separately for every manifest entry. Retain the run ID, candidate ID, current
proposal hash, opportunity ID, and operator identity in the protected release record.

1. **Create a non-dry-run ingestion run without processing it.** This keeps plan inspection ahead
   of paid extraction.

   ```powershell
   $body = @{
     url = 'OFFICIAL_ROOT_URL'
     supporting_urls = @()
     target_name = 'CANONICAL_NAME'
     mode = 'review_queue'
     dry_run = $false
     process_now = $false
   } | ConvertTo-Json
   $run = Invoke-RestMethod -Method Post -Uri "$api/runs/url" -Headers $headers -Body $body
   $candidate = (Invoke-RestMethod -Uri "$api/candidates?run_id=$($run.id)&limit=1&offset=0" -Headers $headers).items[0]
   ```

2. **Inspect the extraction plan before processing.** Stop if the plan has no bounded jobs, exceeds
   the reviewed source/page/cost budget, routes an unofficial source, or lacks objectives needed
   for identity, routes, eligibility, funding, and application timing.

   ```powershell
   $plan = Invoke-RestMethod -Uri "$api/candidates/$($candidate.id)/extraction-plan" -Headers $headers
   $plan | ConvertTo-Json -Depth 10
   ```

3. **Process the existing run in the protected catalogue worker.** Do not create a second run.

   ```powershell
   python -m app.cli.ingest_catalogue_seeds --resume $run.id --batch-size 1
   ```

4. **Inspect extraction and conflicts.** Read the candidate and observability responses, verify all
   cited excerpts against their official pages, and require `conflicts` and release-critical
   `validation_errors` to be empty. Conflicts are never auto-resolved. Request changes, add a
   reviewed official supporting source, and reprocess when evidence disagrees.

   ```powershell
   $candidate = Invoke-RestMethod -Uri "$api/candidates/$($candidate.id)" -Headers $headers
   $observability = Invoke-RestMethod -Uri "$api/candidates/$($candidate.id)/observability" -Headers $headers
   $candidate.conflicts
   $candidate.validation_errors
   ```

5. **Submit and approve the exact proposal version.** Fetch the review after submission and pass its
   current hash on every state-changing call. Approval starts materialization atomically; it is not
   a separate manual data-write command.

   ```powershell
   Invoke-RestMethod -Method Post -Uri "$api/candidates/$($candidate.id)/submit-for-review" -Headers $headers -Body '{"notes":"Flagship source and scoped evidence reviewed."}'
   $review = Invoke-RestMethod -Uri "$api/candidates/$($candidate.id)/review" -Headers $headers
   $version = @{ expected_proposal_hash = $review.current_proposal_hash; notes = 'Approved against official evidence.' } | ConvertTo-Json
   $review = Invoke-RestMethod -Method Post -Uri "$api/candidates/$($candidate.id)/review/approve" -Headers $headers -Body $version
   if ($review.state -ne 'materialized') { throw "Materialization did not complete: $($review.materialization_failure_code)" }
   ```

6. **Check readiness, mark publication-ready, then publish.** Re-fetch the hash before each action.
   Stop on any blocker; do not edit the materialized record to make a gate pass.

   ```powershell
   $ready = Invoke-RestMethod -Uri "$api/candidates/$($candidate.id)/review/publication-readiness" -Headers $headers
   if (-not $ready.ready) { throw ($ready.blockers -join ', ') }
   $review = Invoke-RestMethod -Uri "$api/candidates/$($candidate.id)/review" -Headers $headers
   $version = @{ expected_proposal_hash = $review.current_proposal_hash } | ConvertTo-Json
   $review = Invoke-RestMethod -Method Post -Uri "$api/candidates/$($candidate.id)/review/mark-publication-ready" -Headers $headers -Body $version
   $review = Invoke-RestMethod -Uri "$api/candidates/$($candidate.id)/review" -Headers $headers
   $version = @{ expected_proposal_hash = $review.current_proposal_hash; notes = 'Published for truth-first staging validation.' } | ConvertTo-Json
   $review = Invoke-RestMethod -Method Post -Uri "$api/candidates/$($candidate.id)/review/publish" -Headers $headers -Body $version
   if ($review.state -ne 'published') { throw "Publication did not complete." }
   ```

Repeat until all 12 canonical scholarships are public and evidence-backed.

## Validate and promote staging

1. Configure the protected `azure-staging` environment with `E2E_STAGING_EMAIL`,
   `E2E_STAGING_PASSWORD`, both existing smoke users, and the Azure deployment variables. The E2E
   account must be a dedicated verified student with an existing baseline profile and no existing
   DAAD EPOS application. The source-controlled journey sets target degree to `bachelors` and
   requires DAAD EPOS to return the exact `not_eligible` / `ineligible` branch with the degree
   mismatch explanation. It restores the baseline profile and deletes only the match evaluation
   and application created by that run; it never deletes pre-existing saved or application data.
2. Dispatch **Azure staged application deployment** with `environment=staging` and
   `deployment_confirmation=DEPLOY_STAGING`.
3. The workflow applies the expand migration, deploys the zero-traffic candidate, and runs, in
   order:
   - a noninteractive Container App Job running
     `python -m app.cli.audit_launch_catalogue --minimum-records 12 --manifest data/launch-scholarships.json`;
   - `python scripts/staging_smoke.py --base-url <candidate>` for product and tenant isolation;
   - the protected Chromium catalogue-to-application journey against the real staging APIs.
4. Any non-zero command, invalid/missing JSON, `catalogue-audit.json` with `ready` other than
   `true`, skipped/missing Chromium evidence, or missing smoke evidence stops before promotion.
   The audit is read-only and must never delete or auto-correct records.
5. The staging artifact upload runs even when an audit or Chromium gate fails, so inspect the raw
   audit log, job execution status, JUnit, screenshots, and traces that exist. A failed workflow or
   an artifact without a valid signed-off receipt is diagnostic only and cannot be promoted.
6. After the candidate receives traffic and passes promoted readiness, download the
   `release-provenance` artifact. Record its workflow run URL and SHA-256 digest in the release
   ticket. It must contain:
   - `release-provenance.json` with schema version 3, immutable repository/workflow/commit/image,
     run ID and run attempt, the launch-manifest SHA-256, plus SHA-256 hashes for each required
     evidence file;
   - `catalogue-audit.json` (machine-readable audit result);
   - `candidate-smoke.json` (product and tenant-isolation result);
   - `truth-first-chromium.xml`, the success screenshot, and any retained failure trace.
7. Inspect the JSON and JUnit files directly. Confirm all 12 manifest entries have exactly one
   publishable name/source-root match, `ready=true`, smoke status `staging_smoke_passed`, one passed
   Chromium journey, the expected commit SHA, and an image digest reference. Do not describe a
   staging run as complete until this protected artifact exists.
8. To promote beta, dispatch the same workflow from the exact staging commit with
   `environment=beta`, the successful staging run ID, and
   `deployment_confirmation=PROMOTE_BETA`. Before import, beta queries the GitHub Actions API and
   verifies the source workflow path, successful conclusion, event, repository, head SHA, run ID,
   run attempt, receipt schema, and every evidence-file hash and content. It then imports the
   immutable staging image, deploys a zero-traffic candidate, and runs the same manifest-aware,
   read-only audit against the isolated beta catalogue before beta smoke and traffic promotion.

If any gate fails, leave stable traffic unchanged, preserve the artifact/logs, correct the evidence
through ingestion and human review, and start a new staging run. Never mutate or delete catalogue
records from a release gate.
