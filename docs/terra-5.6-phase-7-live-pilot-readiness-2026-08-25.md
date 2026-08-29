# Terra 5.6 Phase 7 — live-pilot readiness

Date: 2026-08-25
Branch: `codex/phase1b2-crawlee-secure-bridge`
Status: supporting-source acquisition attempted; capability request failed closed; extraction stopped

## Outcome

Phase 7 paid extraction has **not started**. After explicit owner approval, one and only one paid
strict-schema capability request was sent to `catalogue-gpt5-mini` with zero retries. Azure
returned a response, but it did not satisfy the required successful completion/refusal gate, so
the exact runtime contract was not proven and no capability receipt was created. The serialized
request was 13,417 bytes and its conservative one-token-per-byte plus 2,048-output-token cost
bound was `$0.00745025`, below the approved `$0.01` maximum.

The same approval authorized candidate-only acquisition of all six proposed official DAAD
supporting URLs. Two isolated three-page runs attempted all six with AI disabled. Five sources
were fetched and persisted; DAAD's robots policy denied the exact
`https://www.daad.de/sapportal/technische_voraussetzungen/PBF_en.html` URL. That denial was
recorded and was not bypassed. No scholarship extraction attempt was created, and nothing was
published, deployed, committed, pushed, or merged.

The receipt/API-route binding defect is fixed. A subsequent, explicit owner approval authorized
one dedicated local-worker identity. `scholarship-catalogue-local-worker` was created with exactly
one role assignment—`Cognitive Services OpenAI User`—at the `scholarship-ai-863780` resource
scope. Its 30-day secret is stored only in ignored `.env.catalogue.local` and was not printed. The
worker's credential-only token probe passed under the armed stop switch. The later approved
capability request did not satisfy the receipt gate, and no capability receipt was created.

The Phase 6 Docker/Compose exit gate is passed. Docker, Compose, PostgreSQL concurrency,
migrations, API/database health, worker build/start, kill-switch behavior, Crawlee availability,
and the in-container zero-cost preflight are no longer blockers.

The admin direct-URL action now creates a durable queue item instead of asking the HTTP endpoint
to process it synchronously. It always sends `mode=candidate_only`, `dry_run=true`, and
`process_now=false`. The UI calls this action “Queue official sources” and shows the run's
persisted candidate, page, call, input, output, and estimated-cost ceilings.

The example first-pilot configuration is deliberately narrow:

| Control | Configured ceiling |
| --- | ---: |
| Candidates per run | 1 |
| Candidates processed per worker invocation | 1 |
| Pages per candidate | 3 |
| Model calls per run | 8 |
| Input characters supplied to one provider request | 80,000 |
| Output tokens requested from one provider call | 4,000 |
| Estimated run cost | 1.00 in the configured billing currency |
| Automatic provider retries | 0 |

Preflight fails closed for an AI-enabled first-pilot configuration if candidates are not exactly
one, pages exceed three, calls exceed the 12 defined extraction objectives, or automatic provider
retries are nonzero. Positive input/output pricing, an exact deployment-matching capability
receipt, Azure credentials, worker health, current migrations, and sufficient disk are also
required.

## Evidence already available

- Direct-URL ingestion is queue-only; the backend rejects `process_now=true`.
- Candidate-only mode acquires and classifies sources without calling an extraction provider.
- Queue claims, fencing tokens, candidate checkpoints, objective attempts, retries, and dead
  letters are durable.
- Unchanged content/objective/schema/prompt/deployment attempts are reused by content hash.
- Run and attempt records retain provider calls, input/output tokens, estimated cost, latency,
  objective lineage, and reuse status.
- Each provider call consumes a fenced, atomic database reservation for one call and its projected
  cost before provider I/O. Returned usage reconciles that reservation afterward; a crash or an
  uncosted provider failure retains the conservative reservation.
- Provider request text and requested completion tokens are bounded.
- Estimated cost is checked before each provider call and reconciled against returned usage; a
  run transitions to `budget_exhausted` when a configured ceiling is reached.
- The worker profile processes at most one run and one candidate per polling invocation.
- The operator can create `.catalogue-local/STOP`; the worker observes it before queue claims,
  candidates, and extraction objectives. Completed objectives are committed before the next
  check and reused after the switch is removed.
- Draft/incomplete records remain private and publication remains a manual, separately guarded
  action.

## Verification

- Focused catalogue safety set: `104 passed`.
- Focused ingestion suite includes atomic pre-call persistence/reconciliation and a mid-candidate
  kill-switch resume proof with no repeated provider call.
- Frontend unit tests: `9 files passed`, `37 tests passed`.
- Frontend typecheck and production build: passed; Vite emitted the existing mixed
  static/dynamic import warning for `AccountLifecycle.tsx`.
- Full backend regression after the safety hardening: `773 passed, 23 skipped, 10 deselected`.
- Receipt/route focused regression after the binding fix: `105 passed`.
- Full non-browser backend regression after the binding fix: `783 passed, 24 skipped,
  10 deselected`.
- Final database check: 17 completed runs, zero pending/claimed runs, and the historical totals
  remained two attempts, 4,236 input tokens, 1,581 output tokens, and `0.004222` estimated cost.
  The two supporting-source runs each recorded zero model calls, tokens, and estimated cost.
- Dedicated-worker credential proof: service-principal count `1`, role-assignment count `1`, exact
  resource-scope match `1`, credential expiry `2026-09-23T21:50:41Z`, and in-container
  `azure_credential_probe=ready`.
- PostgreSQL ingestion/concurrency module: `4 passed`, including the two-worker atomic budget
  reservation; no PostgreSQL test was skipped. The temporary loopback-only port override was
  removed afterward, and the database is internal-only again.
- Ruff lint and `git diff --check`: passed. Ruff's format check reports 25 existing changed files
  would be reformatted, primarily because their current mixed line endings differ from Ruff's
  normalized output; no bulk formatting rewrite was applied to the dirty worktree.
- Scholarship extraction provider calls: `0`; approved capability calls: exactly `1`, with zero
  retries.
- Capability-call cost bound: at most `$0.00745025` USD; exact billed usage was not retained after
  the non-success terminal response, so no lower value is claimed.

The binding-fix verification commands were:

```powershell
& 'C:\Users\Admin\.local\bin\uv.exe' run pytest `
  tests/test_catalogue_preflight.py tests/test_catalogue_ingestion.py -q `
  --basetemp .pytest-tmp/phase7-receipt-route-v3
& 'C:\Users\Admin\.local\bin\uv.exe' run pytest `
  -m "not e2e and not browser_compat" -q `
  --basetemp .pytest-tmp/phase7-receipt-full-backend-v1
& 'C:\Users\Admin\.local\bin\uv.exe' run ruff check .
git diff --check
```

## Container and queue evidence

Docker was not on the shell `PATH`, so the installed executable was resolved at
`C:\Users\Admin\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe` and invoked
directly:

```powershell
$DockerExe = 'C:\Users\Admin\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
Test-Path -LiteralPath $DockerExe
& $DockerExe version
& $DockerExe compose version
& $DockerExe info
& $DockerExe compose --profile catalogue config
```

This returned `True` and reported Docker Engine `29.7.2`, Docker Desktop `4.86.0`, Compose
`5.3.1`, and a healthy `desktop-linux` context. Compose expansion passed with every paid and
autonomous feature off.

The local profile built and started these containers:

- `scholarship-ai-assistant-api-1` — healthy;
- `scholarship-ai-assistant-db-1` — healthy;
- `scholarship-ai-assistant-migrate-1` — exited `0` after reaching `20260825_0056`;
- `scholarship-ai-assistant-catalogue-worker-1` — running with Crawlee `1.9.2`.

The kill switch was installed before the worker started. Its log reported that catalogue
ingestion was paused, preflight reported `operator_kill_switch_active`, and no run was claimed.
The switch was removed only after the database showed no pending work. Preflight then returned
`ready` inside the worker with database/repository migration heads at `20260825_0056`, API
readiness HTTP `200`, and worker, disk, budget, and kill-switch checks ready. No `AZURE_*`
environment names were present; AI, crawling, discovery, browser, scheduling, and graph flags
were false. For the approved DAAD acquisition, an ignored `.env.catalogue.local` was subsequently
created from the safe example defaults with only `daad.de` added to the reviewed official-domain
allowlist. No Azure value was invented or added.

The worker's 512 MiB `/tmp` reported 536,870,912 bytes free. The example minimum was corrected
from an impossible 1 GiB to 268,435,456 bytes (256 MiB), after which the disk preflight passed.

Before startup, the database held 14 completed and zero pending runs, 62 candidates, and two
historical extraction attempts recording 4,236 input tokens, 1,581 output tokens, and `0.004222`
estimated cost. The stopped-worker proof, green preflight, and one empty invocation with
`--limit 1 --batch-size 1` left every count and total unchanged. The `0.004222` is pre-existing
local estimated usage, not new Azure billing. This proof made zero provider calls and incurred
zero new estimated or observed Azure cost.

## Approved Azure credential/capability probe

Azure CLI was not treated as unavailable after a short-command lookup. It was found in the
standard Windows installation and invoked by absolute path:

```powershell
$AzExe = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
Get-Command az -ErrorAction SilentlyContinue
where.exe az
Test-Path -LiteralPath $AzExe
& $AzExe version
& $AzExe account show --query '{name:name,state:state,userType:user.type}' -o json
```

The path exists and both lookup commands now resolve it. Azure CLI `2.89.1` reported an enabled
host user session in the `Azure for Students` subscription. No tenant ID, subscription ID, token,
secret, or credential cache was printed or inspected.

Read-only management-plane queries found one Azure OpenAI account and one deployment:

| Setting | Discovered value |
| --- | --- |
| Resource | `scholarship-ai-863780` |
| Resource group | `rg-scholarship-ai-dev` |
| Region / account SKU | `japaneast` / `S0` |
| Endpoint | `https://scholarship-ai-863780.openai.azure.com/` |
| Deployment | `catalogue-gpt5-mini` |
| Model | `gpt-5-mini`, version `2025-08-07`, GA |
| Deployment SKU / capacity | `GlobalStandard` / `10` |
| Provisioning state | `Succeeded` |
| Advertised capabilities | `chatCompletion=true`, `responses=true` |
| Limits | 10 requests/minute; 10,000 tokens/minute |
| Inference retirement | `2027-02-09` |

The resource/deployment evidence was obtained without emitting Azure identifiers beyond the
non-secret names above:

```powershell
& $AzExe cognitiveservices account list `
  --query "[?kind=='OpenAI'].{name:name,resourceGroup:resourceGroup,location:location,sku:sku.name,endpoint:properties.endpoint}" `
  -o json
& $AzExe cognitiveservices account deployment list `
  --name scholarship-ai-863780 --resource-group rg-scholarship-ai-dev `
  --query "[].{name:name,model:properties.model.name,version:properties.model.version,sku:sku.name,state:properties.provisioningState,capabilities:properties.capabilities}" `
  -o json
```

The signed-in host user has inherited management access and the data-plane
`Cognitive Services OpenAI User` role at or above the account scope. Only role names were emitted;
principal and scope identifiers were suppressed.

Microsoft's official [API lifecycle documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle)
states that the current GA data-plane API is `v1` and needs no dated `api-version` query
parameter. The current documented dated preview is `2025-04-01-preview`. Microsoft's official
[structured-output documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/structured-outputs)
states that structured outputs first appeared in `2024-08-01-preview` and lists
`gpt-5-mini` version `2025-08-07` as supported for strict JSON Schema. These are documentation
and management-metadata findings; they are not a model-call result.

The earlier receipt/API-version defect is fixed. `APP_CATALOGUE_AI_API_VERSION` was removed rather
than retaining a setting the provider does not send. Both provider implementations now build their
request URL through one canonical contract in `ai_contract.py`, which normalizes the configured
HTTPS origin and appends exactly `/openai/v1/chat/completions`. Receipt validation imports that
same contract and requires:

- receipt schema version `2`;
- provider `azure_openai`;
- the normalized endpoint and exact deployment;
- API mode `azure_openai_v1_chat_completions` and request path
  `/openai/v1/chat/completions`;
- `strict_json_schema=true`;
- deterministic SHA-256 identities for the complete legacy and objective-specific extraction
  schema set and prompt set;
- `live_strict_json_schema_request` evidence with non-empty provider request and response IDs; and
- timezone-aware verification and expiry timestamps with a currently valid interval.

For this code state the extraction identities are:

- schema set: `f47365e99c223166bd3cd43278c548f00e4239c5c0ca6aad57650ea2c764a938`;
- prompt set: `3fe84408d065b5fa1eeb41ee0e11b67a70e1068fcd432aaaab7a3c9f8ae0c0cf`.

Validation is closed over the exact top-level and nested fields. Legacy v1, missing or extra
fields, blank evidence IDs, mismatched providers/endpoints/deployments/routes/strict mode/schema
or prompt identities, future verification times, and expired or inverted validity windows are
rejected. The checked-in v2 example deliberately leaves request IDs and timestamps empty, so it
cannot be mistaken for a valid receipt before an approved live capability test.

The owner approved exactly one request to this deployment using the repository's generated
`response_format.type=json_schema`, `strict=true` schema. The request used the canonical
`/openai/v1/chat/completions` route, deployment `catalogue-gpt5-mini`, `reasoning_effort=minimal`,
`max_completion_tokens=2048`, and no retry loop. Its 13,417-byte payload and token ceiling gave a
conservative `$0.00745025` maximum at the confirmed prices. Azure returned a response that did
not satisfy the required `finish_reason=stop` and no-refusal gate; the exact-contract check
therefore failed closed. The request was not repeated, and
`.catalogue-local/model-capability.json` was not created.

The worker's existing identity chain was probed without printing a token:

```powershell
& $DockerExe compose exec -T catalogue-worker python -c `
  "from app.core.config import get_settings; from app.modules.catalogue_ingestion.preflight import _azure_credential_probe; _azure_credential_probe(get_settings()); print('azure_credential_probe=ready')"
```

The probe failed before any model endpoint access because `DefaultAzureCredential` found no
configured environment credential, workload identity, managed identity, shared token cache,
Azure CLI, Azure PowerShell, Azure Developer CLI, or broker credential inside the worker. The
host session is not visible because the Linux image contains no Azure CLI or PowerShell and the
host Azure CLI cache is neither mounted nor available in the container. No cache was searched,
copied, or mounted.

After explicit owner approval, the safest supported path was implemented: dedicated service
principal `scholarship-catalogue-local-worker`, scoped only to this Azure OpenAI account with the
`Cognitive Services OpenAI User` role. The identity has exactly one role assignment. Its
`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are non-empty only in ignored
`.env.catalogue.local`; no value was printed, committed, or copied elsewhere. The sole credential
is named `catalogue-local-worker-30d` and expires at `2026-09-23T21:50:41Z`. The host Azure CLI
cache was not searched, copied, or mounted.

With `.catalogue-local/STOP` present, only `catalogue-worker` was recreated to load the ignored
environment. The container confirmed `/run/catalogue/STOP`, its log continued to report
`Catalogue ingestion paused: operator kill switch is active`, and this token-only command passed:

```powershell
& $DockerExe compose exec -T catalogue-worker python -c `
  "from app.core.config import get_settings; from app.modules.catalogue_ingestion.preflight import _azure_credential_probe; _azure_credential_probe(get_settings()); print('azure_credential_probe=ready')"
```

This contacted Microsoft Entra ID only to obtain a Cognitive Services token. It made no Azure
OpenAI data-plane request and did not test model capability.

The official Azure OpenAI pricing page was inspected with region **Japan East**, deployment type
**Global**, and display currency **USD**. It showed `GPT-5-mini` public prices per one million
tokens of `$0.25` input, `$0.03` cached input, and `$2.00` output. The owner subsequently confirmed
the `$0.25` input and `$2.00` output USD basis for this pilot.

The ignored `.env.catalogue.local` remains on all-safe/off capability settings with the reviewed
`daad.de` allowlist. Capability validation still cannot pass because the one approved request did
not complete successfully and no evidence-backed local receipt exists.

## Approved DAAD candidate-only acquisition

The repository's sole DAAD priority route was selected:

- route: `DAAD Development-Related Postgraduate Courses EPOS`;
- provider: `German Academic Exchange Service DAAD`;
- official starting URL:
  `https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database?detail=50076777`.

The worker was paused first, and the database showed zero pending or claimed runs. The run was
created under the active kill switch and inspected before fetching:

```powershell
& $DockerExe compose exec -T catalogue-worker python -m app.cli.ingest_catalogue_seeds `
  --url 'https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database?detail=50076777' `
  --name 'DAAD Development-Related Postgraduate Courses EPOS' `
  --provider 'German Academic Exchange Service DAAD' --country Germany `
  --mode candidate_only --dry-run --batch-size 1
```

Inspection showed run `9c2099d2-e2db-4d78-a245-2e5bfafd556d` as `pending/queued`, with one
discovered candidate, `model_calls=0`, and `estimated_cost=0`. The background worker was then
stopped, the switch was removed, and only that inspected run was processed in an isolated
one-off worker:

```powershell
& $DockerExe compose run --rm --no-deps --entrypoint python catalogue-worker `
  -m app.cli.ingest_catalogue_seeds `
  --resume 9c2099d2-e2db-4d78-a245-2e5bfafd556d --batch-size 1
```

Result:

- run: `completed`, stage `complete`, checkpoint `1`, `candidate_only`, `dry_run=true`;
- candidate `e567410a-61da-47c5-8ea9-b6ca5c2f7607`: `needs_review` with the expected terminal
  code `candidate_only_complete`;
- source: fetched from and remained on the approved DAAD URL, official trust tier 1 through the
  reviewed `daad.de` allowlist;
- artifact `95229e91-d398-45a8-b466-6f4f323f3d35`: HTML, 39,585 bytes, 11,736 normalized
  characters, SHA-256
  `aaf210facdbcdfabfc5f3d683631fe3f20e29ea7fda15188ca9d3daa68ca35d3`;
- deterministic content checks found the EPOS identity, application-requirements and application-
  procedure sections, plus links for the 2027/2028 deadlines and eligible-country list;
- bundle: `reviewable=true`, `complete=false`, one accepted `identity_overview` artifact, no
  blocked sources;
- remaining bundle gaps: funding, eligibility, deadline, application-process, and required-
  documents sources;
- run usage: zero model calls, zero input/output tokens, and `0.000000` estimated cost;
- database-wide historical extraction totals remained exactly two attempts, 4,236 input tokens,
  1,581 output tokens, and `0.004222` estimated cost.

The kill switch was re-created before the background worker was restarted. The worker is running
but reports that ingestion is paused. There are now 15 completed runs and zero pending or claimed
runs. No extraction or publication occurred.

### Approved supporting sources and acquisition result

Artifact `95229e91-d398-45a8-b466-6f4f323f3d35` persisted the following links. They were grouped
offline without refetching. Every proposed URL is HTTPS and its parsed host is exactly
`www2.daad.de`, `www.daad.de`, or `static.daad.de`, all beneath the deterministically reviewed
`daad.de` domain:

| Evidence gap | Proposed new acquisition URL(s) | Already-persisted anchor evidence |
| --- | --- | --- |
| Funding | `https://static.daad.de/media/daad_de/pdfs_nicht_barrierefrei/in-deutschland-studieren-forschen-lehren/epos_faq_en.pdf` | `https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database?detail=50076777#ueberblick` |
| Eligibility / country list | `https://static.daad.de/media/daad_de/pdfs_nicht_barrierefrei/in-deutschland-studieren-forschen-lehren/dac_laenderliste_epos.pdf` | `https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database?detail=50076777#voraussetzungen` |
| Current deadline | `https://static.daad.de/media/daad_de/pdfs_nicht_barrierefrei/in-deutschland-studieren-forschen-lehren/daad_epos_deadlines.pdf` | — |
| Application process | `https://www.daad.de/en/study-and-research-in-germany/scholarships/important-information-for-scholarship-applicants/`<br>`https://www.daad.de/sapportal/technische_voraussetzungen/PBF_en.html` | `https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database?detail=50076777#prozess` |
| Required documents | `https://static.daad.de/media/daad_de/pdfs_nicht_barrierefrei/in-deutschland-studieren-forschen-lehren/epos_checkliste.pdf` | — |

The six proposed HTTPS URLs were approved and split into two bounded runs of three:

- run `4c8306bd-5315-464e-8ba3-c3804e96e25f` completed with candidate
  `9a86d770-7cf9-467a-8c0e-cf61923519ec` at `candidate_only_complete`; all three PDFs were fetched
  as official trust-tier-1 sources and persisted as text-bearing artifacts;
- run `78622260-b124-4403-a112-b10a3aa865c2` completed with candidate
  `fe80f055-06c8-4f54-8ffa-f85e11b7b272`; the scholarship-applicant page redirected within
  `daad.de` and was persisted as HTML, and `epos_checkliste.pdf` was persisted as PDF;
- the exact `PBF_en.html` source was attempted but recorded as `robots_disallowed`; no bypass or
  substitute URL was used;
- both runs were `candidate_only`, `dry_run=true`, page limit `3`, with zero model calls, zero
  input/output tokens, and `0.000000` estimated cost.

| Source | Result | Persisted evidence |
| --- | --- | --- |
| `epos_faq_en.pdf` | fetched, official tier 1 | artifact `fc07c313-5224-4ece-92fa-01ba4ca8557d`; 151,018 bytes; 9,802 characters |
| `dac_laenderliste_epos.pdf` | fetched, official tier 1 | artifact `87bc9f34-6cd3-4be6-93d7-749ba5014b88`; 19,256 bytes; 1,868 characters |
| `daad_epos_deadlines.pdf` | fetched, official tier 1 | artifact `e9e71fda-9911-495d-9945-2107ad2a028d`; 115,108 bytes; 4,178 characters |
| scholarship-applicant information page | fetched after official in-domain redirect | artifact `924e94d4-ccfc-4ba7-878a-0fe5842c7464`; 351,593 bytes; 42,906 characters |
| `epos_checkliste.pdf` | fetched, official tier 1 | artifact `26514547-beaf-4f3c-b6f6-b1508e19f565`; 420,657 bytes; 4,387 characters |
| `PBF_en.html` | blocked | `robots_disallowed`; no artifact |

The persisted `http://static.daad.de/.../daad_epos_application_form.docx` link is deliberately
excluded because it is HTTP-only. Search-result, print, duplicate, and unrelated-funder links are
also excluded. Fragment anchors are not proposed for refetch because HTTP does not send the
fragment and the underlying page is already the persisted primary artifact.

## Remaining Phase 7 blockers

Local implementation is not blocked: Docker, Compose, PostgreSQL, migrations, the worker, and the
zero-cost controls are proven. These owner-controlled readiness gates remain before paid
extraction:

The owner has now confirmed resource `scholarship-ai-863780`, deployment
`catalogue-gpt5-mini`, region Japan East, the GA v1 Chat Completions route, and the USD estimate
basis of `$0.25` input and `$2.00` output per million tokens. Local-worker authentication is now
proven. The remaining gates are:

1. The one approved strict-schema request did not satisfy its completion/refusal gate.
   A second request would require new, separate owner approval; no v2 receipt exists.
2. The approved DAAD URLs were all attempted, but `PBF_en.html` remains unavailable because the
   official host's robots policy disallows it. Any alternate official URL requires owner review
   and approval before acquisition.
3. Separate explicit approval for the paid extraction call after the source bundle and remaining
   robots-policy gap are reviewed. It has not been granted.

Azure billing telemetry may lag. The one capability request was conservatively bounded below
`$0.01`; no scholarship-extraction usage exists in the catalogue database.

Automatic provider retries remain zero for the first pilot because a provider-internal retry is
not independently reserved or accounted before it occurs.

## Required owner decisions

Before any further model-connected Phase 7 command runs, the owner must separately approve a new
capability request. The owner must also approve any alternate official URL proposed for the
robots-blocked application-process page. Paid extraction remains a later, separate approval after
source-bundle review and a valid v2 receipt.

## Safe continuation sequence

1. Keep `.catalogue-local/STOP` armed and all AI/source-acquisition flags off. Rotate or remove the
   dedicated credential no later than `2026-09-23T21:50:41Z`; do not broaden its scope or role.
2. The receipt/API-route binding defect is corrected, but the one approved capability request did
   not complete successfully. Do not retry without new approval; create a v2 receipt only after a
   later exact-contract success.
3. Review the five persisted supporting artifacts and the `robots_disallowed` record. Do not
   acquire an alternate URL without explicit approval.
4. Only after separate explicit paid-extraction approval, run extraction once and stop. Report
   provider calls, input/output tokens, estimated and Azure-observed cost, cache hits, extracted
   fields, blockers/conflicts, and evidence accuracy before considering CSC or Erasmus.

## Exit gate

Phase 6 is complete. The original DAAD page and five of six approved supporting URLs are now
persisted without scholarship extraction; the sixth supporting URL is recorded as robots-blocked.
Host Azure configuration, deployment metadata, and the dedicated worker credential are verified.
Evidence-backed strict-schema capability, a complete reviewed source bundle, and separately
authorized paid extraction do not yet exist. This is an intentional authorization boundary, not
a Docker, Compose, PostgreSQL, tool-availability, authentication, or receipt-binding defect. Work
stops here with `.catalogue-local/STOP` armed, before another source fetch or model request.
