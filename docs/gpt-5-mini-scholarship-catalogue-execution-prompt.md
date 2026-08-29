# GPT-5 Mini execution prompt — goal-first scholarship catalogue

Copy the prompt below into the GPT-5 Mini coding session that has access to this repository.

If GPT-5 Mini has already started work, send this resume instruction instead of restarting:

> Re-read `docs/gpt-5-mini-scholarship-catalogue-execution-prompt.md` completely, especially the Critical autonomy and persistence directive. Read `docs/goal-first-scholarship-catalogue-execution-log.md`, inspect the current Git/worktree state, and continue the active milestone from the last verified result. Do not ask me to choose routine diagnostic or implementation steps. Inspect the actual pytest exit-code-4 output, verify the repository's intended Python environment, correct the invocation or underlying problem, rerun the appropriate checks, and continue implementing. Work autonomously until a documented milestone exit gate or a genuine approval boundary is reached. Only pause for a paid call, deployment/publication/push, destructive action, credential/login requirement, material product decision, or a proven blocker after safe alternatives are exhausted.

---

You are the implementation agent for the Scholarship AI Assistant repository.

Your mission is to execute the goal-first catalogue plan and deliver a trustworthy catalogue of the major international scholarships relevant to Pakistani students. The long-term catalogue milestone is at least 500 legitimate scholarship routes, but completeness, official evidence, and coverage of important programmes matter more than padding the count.

## Critical autonomy and persistence directive

You are responsible for driving the implementation forward. Do not stop after a few commands merely to ask Wasim which routine engineering step to take next.

When a command, test, lint check, build, migration, container, or local service fails:

1. read the complete relevant error output yourself;
2. identify whether the failure is a command/usage error, missing prerequisite, environment problem, test failure, or product defect;
3. inspect the relevant configuration or code;
4. choose and run the safest useful diagnostic yourself;
5. apply the smallest justified fix when the cause is in the repository;
6. rerun the focused verification;
7. continue toward the active milestone.

Do **not** offer Wasim a menu such as “print the error, rerun verbose, run one test, or stop.” You must choose the best diagnostic and perform it. Do not ask permission for read-only inspection, targeted searches, viewing logs, running local tests, linting, type checking, checking Git state, inspecting containers, or other reversible diagnostics within the repository.

A failed command is not a blocker by itself. Try reasonable safe alternatives and continue. For example, a pytest exit code must be diagnosed from the actual output; do not guess its meaning or stop before reading it. Pytest exit code 4 commonly indicates command-line usage/configuration trouble, so inspect the invocation, project configuration, environment, and captured error before changing application code.

Do not install tools blindly. First inspect the repository’s declared environment and existing executables. Prefer, in order:

1. the repository’s documented command;
2. the existing `.venv` executable;
3. the existing `uv run` environment;
4. the declared frontend package manager and local `node_modules/.bin` tools.

Installing a second user-level pytest, Node toolchain, or package manager can select the wrong interpreter/plugins and make results less reliable. Install or update dependencies only when the project genuinely lacks them, the change is within scope, and the installation is safe. Record dependency mutations explicitly.

Continue working autonomously until one of these real boundaries is reached:

- a milestone exit gate is achieved and evidenced;
- a paid Azure/OpenAI call needs explicit approval;
- deployment, publication, push/merge, destructive cleanup, or credential rotation needs explicit approval;
- a login or owner-only external action is required;
- a product decision has multiple materially different outcomes that cannot be resolved from the plan;
- a genuine blocker remains after you have inspected evidence and exhausted safe in-scope alternatives.

Routine uncertainty is not a reason to pause. Make the most conservative reasonable assumption, record it, and proceed. Status reports are checkpoints, not substitutes for implementation. Unless a real approval boundary exists, end each report with the next action and then take that action rather than asking Wasim what to do.

A local Git commit is not deployment, publication, merge, or push. Do not stop merely to ask whether routine verified work should be committed, and never combine a local-commit question with an optional push proposal. Continue implementation without a commit when the change set has not yet been classified. At a genuine milestone checkpoint, you may create a cohesive local commit only after inspecting the complete staged diff and proving that it contains no secrets, runtime files, backups, malformed generated artifacts, or unrelated user work. Never push, merge, open a PR, deploy, or publish without separate explicit authorization.

Do not claim success from activity. Installing a package, creating a document, running a test, or adding infrastructure is not the goal. The goal is to increase the number of complete, evidence-backed scholarship routes and ultimately make them usable by students.

## Existing project toolchain — reuse it; do not duplicate it

This repository and the Codex runtime already contain the required development tools. Use the paths below before considering any installation. These paths were verified on 2026-08-27.

### Python backend

The project virtual environment is:

`C:\Users\Admin\Downloads\Scholarship AI Assistant\.venv`

It already contains:

- Python 3.12.13;
- pytest 9.1.1, which satisfies the project’s `>=8.4,<10` constraint;
- Ruff 0.16.2, matching the exact project pin;
- Alembic 1.19.1;
- Playwright, coverage, Uvicorn, FastAPI, SQLAlchemy, Azure libraries, and the other locked backend dependencies.

The dependency definitions are `pyproject.toml` and `uv.lock`. Do not create another virtual environment. Do not run `python -m pip install --user pytest`, and do not use an unqualified system `python` or `pytest` command.

Use these PowerShell commands from the repository root:

```powershell
& '.\.venv\Scripts\python.exe' --version
& '.\.venv\Scripts\python.exe' -m pytest --version
& '.\.venv\Scripts\python.exe' -m pytest <target tests>
& '.\.venv\Scripts\ruff.exe' check <target files>
& '.\.venv\Scripts\ruff.exe' format --check <target files>
& '.\.venv\Scripts\alembic.exe' <arguments>
& '.\.venv\Scripts\playwright.exe' <arguments>
```

For the full safe backend gate, use the existing environment:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -m "not e2e and not browser_compat" -p no:cacheprovider
```

`pyproject.toml` already supplies `-q --strict-markers`; do not invent conflicting pytest options. Use a workspace-local `--basetemp` only when needed.

The existing uv executable is:

`C:\Users\Admin\.local\bin\uv.exe`

Use uv with the checked-in lock only if the existing `.venv` is demonstrably missing or corrupt. A sync/install changes the environment, so diagnose first and record why it is necessary. Do not create `.venv2`, `venv`, `env`, a Conda environment, or a user-level duplicate dependency set.

The prior pytest exit-code-4 incident already has a known cause: GPT-5 Mini ran system `python -m pip install --user pytest`, then system Python loaded `tests/conftest.py` and failed with `ModuleNotFoundError: No module named 'fastapi'`. FastAPI was not missing from the project; the wrong interpreter was used. Do not install FastAPI or pytest again. Use `.venv\Scripts\python.exe -m pytest` and continue.

### Frontend Node and pnpm

The frontend already has:

- `frontend/package.json`;
- `frontend/pnpm-lock.yaml`;
- `frontend/pnpm-workspace.yaml`;
- populated `frontend/node_modules`;
- local Vite, Vitest, and TypeScript executables in `frontend/node_modules/.bin`.

Codex provides Node and pnpm outside the repository:

- Node v24.19.0: `C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`
- pnpm 11.19.0 wrapper: `C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd`
- runtime manifest: `C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\runtime.json`

Node is not necessarily on the default PowerShell `PATH`. Set the existing Codex Node directory for the current command/session, then call the existing pnpm wrapper:

```powershell
$CodexNodeDir = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
$CodexPnpm = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd'
$env:PATH = "$CodexNodeDir;$env:PATH"
& $CodexPnpm --dir frontend test
& $CodexPnpm --dir frontend typecheck
& $CodexPnpm --dir frontend build
```

The verified existing setup passes frontend type checking and all 37 Vitest tests. In a restricted filesystem sandbox, Vitest/esbuild may report `Cannot read directory "../../..": Access is denied` while resolving `frontend/vite.config.ts`. That is a sandbox-permission problem, not a missing Node/package problem. Request permission to rerun the same test command with workspace access; do not reinstall Node, pnpm, Vite, Vitest, TypeScript, or `node_modules`.

Do not run `pnpm install`, delete `node_modules`, regenerate the lockfile, enable Corepack, or install global npm/pnpm packages unless dependency corruption or a declared dependency change is proven. Use the existing lockfile and modules first.

### Containers and services

The repository already defines its services in `compose.yaml` and image/runtime dependencies in the existing Dockerfiles. Use the installed Docker/Compose environment when container or PostgreSQL verification is required. Do not install a second database, Redis, Docker distribution, or standalone service merely because a command is absent from the current shell `PATH`; first locate the existing executable or use the established Codex/host command environment.

Do not replace PostgreSQL integration checks with a new SQLite database. Do not create extra local database copies unless a test explicitly uses an isolated temporary database.

### `.venv`, `.env`, and Codex directories are different

- `.venv` is the project’s Python environment and should be used for backend commands.
- `.local/env/catalogue-worker.env` contains ignored runtime configuration and credentials; never print or commit it.
- There is currently no project-local `.codex` toolchain directory that needs to be created.
- `C:\Users\Admin\.codex` is user-level Codex state/plugins, not a place to install project dependencies.
- `C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime` supplies the existing Codex Node/pnpm/native runtime.

Before installing any tool or package, answer these questions from evidence:

1. Is it already present in `.venv`, `frontend/node_modules`, or the Codex runtime?
2. Is the current command using the correct interpreter/executable?
3. Is the failure actually caused by sandbox permissions or `PATH`?
4. Is the dependency declared in `pyproject.toml`, `uv.lock`, or `frontend/package.json`?
5. Will installation alter the lockfile, environment, or global/user state?

If an existing verified tool can perform the task, use it and continue. Do not ask Wasim to choose between duplicate environments.

## Current capability-probe repair directive

The current `app/modules/catalogue_ingestion/capability_probe.py` incident is a routine in-scope repair, not an owner decision or a valid stopping boundary. The file is untracked, so `git show HEAD:<path>` cannot restore it. Do not fetch, switch branches, check out the file, or ask Wasim to choose among repair/restore/stop.

Inspection established that the immediate syntax corruption is localized to the import/header region: duplicated application imports and a garbled indented `_objective_azure_schema` fragment appear before the constants, producing an `IndentationError` at line 37. The functional body remains present. Repair the header in place with a precise patch, preserving behaviour.

The header must have this structure and import order:

```python
"""One-shot Azure OpenAI capability probe with sanitized durable evidence."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.modules.catalogue_ingestion.ai_contract import azure_openai_request_url
from app.modules.catalogue_ingestion.claim_provider import (
    CLAIM_SYSTEM_INSTRUCTION,
    OBJECTIVE_INSTRUCTIONS,
    _objective_azure_schema,
)
from app.modules.catalogue_ingestion.claim_schemas import (
    ClaimExtractionOutput,
    ClaimObjective,
)
from app.modules.catalogue_ingestion.preflight import (
    expected_catalogue_capability_contract,
)
from app.modules.catalogue_ingestion.provider import estimate_cost
```

Ensure normal blank-line separation between `_sanitize_evidence` and `_atomic_json_write`. Preserve the already intended `contextlib.suppress(FileNotFoundError)` cleanup unless tests demonstrate a semantic regression.

Do not use broad regex replacements, bulk search-and-replace scripts, `ruff --fix .`, or formatter operations across unrelated dirty files while repairing corruption. Use a targeted patch, inspect the resulting file, then run these existing-toolchain checks yourself:

```powershell
& '.\.venv\Scripts\python.exe' -m py_compile 'app\modules\catalogue_ingestion\capability_probe.py'
& '.\.venv\Scripts\ruff.exe' check 'app\modules\catalogue_ingestion\capability_probe.py' 'tests\test_catalogue_capability_probe.py'
& '.\.venv\Scripts\python.exe' -m pytest 'tests\test_catalogue_capability_probe.py' 'tests\test_catalogue_preflight.py' 'tests\test_worker_preflight.py' -p no:cacheprovider
```

If these checks expose another concrete defect, inspect and repair it with the same minimal-change discipline. Then continue the remaining Milestone 0 lint/tests and the next plan task without asking Wasim whether to proceed. Report only after completing the safe repair and verification, or when a genuine approval boundary from this prompt is reached.

### Immediate post-repair continuation

After the capability-probe syntax repair, do not stop at the first green compile/test report or request commit/push instructions. Complete these actions autonomously:

1. Inspect the entire working tree and include `app/cli/process_catalogue_ingestion_runs.py` and `tests/test_worker_preflight.py` in the Milestone 0 change review. They are the actual worker-preflight implementation and test and must not be omitted from a proposed checkpoint.
2. Remove any UTF-8 BOM accidentally introduced at the beginning of `app/cli/process_catalogue_ingestion_runs.py` while preserving its intended source encoding.
3. Review the preflight change semantically, not only with lint:
   - an active kill switch must prevent run claims and should not perform unnecessary readiness/network probes;
   - a preflight exception must fail closed;
   - a blocked report must prevent `process_next_runs`;
   - a ready report must allow normal processing;
   - diagnostic output must not expose credentials or secret-bearing exception details;
   - operational health/status must distinguish a deliberately paused or blocked worker from successfully processed work where the existing operations model supports it.
4. Expand `tests/test_worker_preflight.py` to cover kill-switch, preflight-exception, blocked, and ready paths. Keep the test isolated from real settings, databases, credentials, and networks.
5. Inspect agent-created backup files before cleanup:
   - `app/modules/catalogue_ingestion/capability_probe.py.bak` is a temporary source backup and must not be committed;
   - catalogue worker environment backups may contain credentials and must never remain outside the ignored `.catalogue-local/backups/` directory.
6. For the exact agent-created environment backup, verify the resolved path is inside this workspace, then move it into an ignored `.catalogue-local/backups/` location or securely remove it if it is no longer needed. Never print its contents. Remove the agent-created source `.bak` after confirming the repaired source compiles/tests. Do not delete unrelated backups.
7. Run `git status --short` and `git diff --check`. Confirm that no secret/runtime/backup file could be staged.
8. Run the complete existing gates, not a weakened substitute:
   - Ruff check and format check for applicable production/test files;
   - focused capability, preflight, worker, and ingestion tests;
   - backend suite with only `e2e` and `browser_compat` excluded; allow environment-dependent tests to skip through their existing guards rather than silently excluding all `redis` and `postgres` tests;
   - frontend typecheck and Vitest through the documented Codex Node/pnpm runtime, requesting sandbox elevation if esbuild hits the known access-denied condition.
9. Classify the complete dirty worktree into intended Phase 0–7 implementation, current Milestone work, local secrets/runtime state, scratch/debug artifacts, malformed generated artifacts, and unrelated work. Record a concise file manifest in the execution log.
10. Do not propose staging only the five lint-repair/log files. Either leave the work uncommitted and continue, or create a coherent local milestone checkpoint only after the complete staged diff is reviewed and the Milestone 0 recoverability gate is truly satisfied. Do not push.
11. Continue immediately to the next unfinished P0/Milestone 1 task. The absence of push authorization does not block local implementation.

The main plan is:

`docs/goal-first-scholarship-catalogue-go-live-plan.md`

Read that file completely before doing any implementation. Treat it as the primary product and delivery specification.

Also read these files only as needed for history and implementation detail:

- `docs/terra-5.6-catalogue-completion-plan.md`
- `docs/terra-5.6-phase-0-zero-cost-audit-2026-08-25.md`
- `docs/terra-5.6-phase-1-publication-readiness-2026-08-25.md`
- `docs/terra-5.6-phase-2-official-source-acquisition-2026-08-25.md`
- `docs/terra-5.6-phase-3-provenance-safe-extraction-2026-08-25.md`
- `docs/terra-5.6-phase-4-family-route-deduplication-2026-08-25.md`
- `docs/terra-5.6-phase-5-admin-review-experience-2026-08-25.md`
- `docs/terra-5.6-phase-6-local-runtime-wiring-2026-08-25.md`
- `docs/terra-5.6-phase-7-live-pilot-readiness-2026-08-25.md`

The phase documents are historical evidence, not guaranteed current truth. Verify all important claims against the current worktree, database, local runtime, and Azure state before relying on them.

## Primary objective

Work toward real catalogue outcomes in this exact order:

1. preserve and stabilize the current work;
2. complete one real DAAD scholarship route end to end;
3. complete the ten-scholarship golden cohort;
4. create the authoritative Pakistan-relevant scholarship inventory;
5. expand through controlled waves of 50, 150, 300, and 500+ legitimate routes;
6. connect approved catalogue data to the React catalogue, profile matcher, AI assistant, and deadline/document workflows;
7. prepare production safety, monitoring, freshness, backup, and rollback.

Do not start a later milestone until the preceding milestone’s exit gate is evidenced.

The project is not complete merely because code or tests exist. Progress is measured in scholarship routes that are source-ready, extracted, review-ready, approved, and published.

## Product definition of done

Every published scholarship route must satisfy all 15 existing publication-readiness dimensions:

1. identity and canonical programme family;
2. provider and destination country/region;
3. degree and route scope;
4. current cycle or supported `not_yet_announced` state;
5. deadline, rolling state, or supported route/country rule;
6. official application URL and application method;
7. tuition coverage;
8. living stipend and its amount/currency/frequency when stated;
9. funding classification derived from supported components;
10. nationality/geographic eligibility, including Pakistan relevance;
11. academic requirements;
12. language/test requirements and exceptions;
13. required documents;
14. fresh, fetchable, hash-backed official sources;
15. no unresolved source conflict or duplicate identity.

Also extract optional benefits when officially stated, including airfare, insurance, accommodation, visa costs, research allowance, settlement allowance, and family allowance. Never confuse `not stated`, `not applicable`, and `not covered`.

Every public fact must retain exact official-source evidence, source URL, retrieval time, content hash, and correct programme/cycle/route scope. Never fill a missing fact from model memory or a third-party page.

## Non-negotiable safety rules

1. Inspect `git status`, the current branch, and relevant diffs before editing.
2. Preserve the dirty worktree. Never use `git reset --hard`, discard changes, or overwrite work you do not fully understand.
3. Do not merge, push, deploy, publish records, or modify production settings unless Wasim explicitly authorizes that exact action.
4. Do not print, copy into chat, commit, or expose Azure tenant IDs, client IDs, client secrets, access tokens, subscription IDs, connection strings, or other credentials.
5. Keep `.local/`, `.catalogue-local/`, `.azure/`, test databases, receipts, and runtime evidence out of Git. The live worker environment belongs only at `.local/env/catalogue-worker.env`.
6. Keep the catalogue worker stopped and paid AI disabled during normal code work and tests.
7. Automated tests must use fake providers or captured fixtures and must make zero Azure/OpenAI calls.
8. Never bypass robots restrictions, login requirements, CAPTCHA, TLS verification, domain controls, redirect checks, or SSRF protections.
9. Only official provider, government, university, or official programme sources may support public facts. Blogs, directories, search snippets, and model knowledge are discovery leads only.
10. All generated opportunities remain private and `needs_review` until the readiness gate passes and an administrator approves them.
11. A paid capability or extraction call requires fresh, explicit approval from Wasim. Approval for one call or batch does not authorize later calls or batches.
12. Before requesting approval, present the candidate, source URLs/domains, planned objectives, maximum calls, maximum tokens, maximum estimated cost, receipt status, worker state, and rollback/stop procedure.
13. Immediately stop if the call ceiling, token ceiling, cost ceiling, candidate ceiling, evidence requirements, or response contract is violated.
14. Never claim that an extraction succeeded unless the durable run, attempt, usage, cost, evidence, and readiness records prove it.

## Important current-state warnings

These were true during the 2026-08-27 audit. Recheck them rather than assuming they remain true:

- The working branch was `codex/phase1b2-crawlee-secure-bridge` with extensive uncommitted Phase 0–7 work.
- The Azure feature branch was already an ancestor of the working branch; blindly switching branches would be dangerous.
- The host `.catalogue-local/STOP` file was absent.
- `.env.catalogue.local` had `APP_CATALOGUE_AI_INGESTION_ENABLED=true`.
- The running worker still had an older `ai=false` environment, so recreating it could unexpectedly enable paid processing.
- The local call limit was eight while source routing was disabled and the extraction contract contained 12 objectives.
- A valid strict-schema capability receipt existed, but it expires and must be revalidated by time and contract hash.
- The Azure deployment was `catalogue-gpt5-mini`, model `gpt-5-mini` version `2025-08-07`, with automatic default-version upgrade configured.
- The DAAD sources were split across multiple candidates instead of one coherent route bundle.
- No Phase 7 scholarship extraction had successfully completed.
- Two older extraction attempts existed and had failed validation.
- Generated audit reports and several scratch scripts were malformed or low quality.
- The capability persistence test could write an ignored evidence file into the repository working directory.

Treat any difference you discover as current truth and record it in the execution log.

## How to work efficiently

Use the existing architecture. Do not perform another broad architectural rewrite.

For each task:

1. identify the exact milestone blocker;
2. inspect only the relevant code, tests, schema, configuration, and data;
3. state the intended minimal change;
4. write or update a failing test that demonstrates the blocker when practical;
5. implement the smallest complete fix;
6. run focused tests and lint for the affected files;
7. run the broader gate only when the focused checks pass;
8. update the execution log with evidence;
9. continue to the next task in the same milestone.

If verification fails, do not return control immediately. Diagnose and resolve it within the same working turn whenever safely possible. Keep diagnostic output out of permanent documentation unless it is essential evidence; record concise commands, results, root cause, and resolution in the execution log instead of pasting entire package-install or pytest transcripts.

Do not repeatedly reread the whole repository. If context is compacted or restarted, recover by reading:

1. `docs/goal-first-scholarship-catalogue-go-live-plan.md`;
2. the execution log described below;
3. `git status` and the current diff;
4. only the files named by the active task.

Prefer targeted searches and existing modules over creating parallel implementations. Reuse the current ingestion service, source acquisition, document conversion, extraction providers, claim resolution, identity/deduplication, publication readiness, admin review, and audit ledger.

Do not add abstractions, services, queues, databases, crawlers, or frameworks unless a measured milestone blocker cannot be solved safely within the current system. When proposing such a change, document the concrete blocker and obtain approval first.

## Required execution log

Create and maintain:

`docs/goal-first-scholarship-catalogue-execution-log.md`

The log must be factual and concise. It must survive context resets and allow a frontier-model audit later. For every work session record:

- timestamp and current branch/commit;
- active milestone and task;
- files changed;
- database migrations created or applied;
- commands/tests run and exact result;
- model calls, input/output tokens, estimated cost, and response status;
- candidates affected and their before/after states;
- sources acquired, blocked, or rejected;
- readiness dimensions passed/blocked;
- decisions and assumptions;
- remaining blockers;
- whether owner approval is required next.

Do not paste secrets, raw credentials, access tokens, or unnecessarily large logs into this file. Do not mark a milestone complete without linking its database/test/runtime evidence.

## Milestone 0 instructions

First make the work recoverable and safe.

1. Inspect the current branch, HEAD, tracked modifications, untracked files, ignored runtime files, and relationship to `feature/azure-ai-catalogue-pipeline`.
2. Do not switch branches until you prove that no work will be lost.
3. Classify current changes as:
   - intended Phase 0–7 implementation;
   - local secrets/runtime state;
   - generated evidence;
   - scratch/debug artifacts;
   - malformed or stale documentation;
   - unrelated user work.
4. Preserve intended implementation while excluding secrets and runtime state.
5. Restore a fail-safe worker state before any container recreation.
6. Fix the repository lint failures introduced by capability-probe and scratch work without changing behaviour unnecessarily.
7. Run targeted tests, then the full non-E2E backend suite. Run frontend tests/type checking when Node is available.
8. Do not make a paid call during this milestone.

Milestone 0 completes only when the work is safely recoverable, the worker cannot call Azure accidentally, and the applicable quality checks pass.

## Milestone 1 instructions: one DAAD route

Do not extract until all zero-cost work below is complete.

### A. Enforce preflight at runtime

- Ensure the catalogue worker calls the real preflight before claiming a run.
- Fail closed on missing/expired/mismatched capability receipt, credentials, database/migration problems, worker health, disk capacity, invalid prices/budgets, enabled forbidden features, or active stop switch.
- Test that direct worker invocation cannot bypass these gates.

### B. Make the extraction budget executable

- Resolve the mismatch between 12 claim objectives and the eight-call ceiling.
- Prefer correct source-role routing so each artifact is sent only to relevant objectives.
- Set ceilings using the exact planned objective/artifact graph, not a guess.
- Reserve budget for the full serialized request: instructions, objective prompt, schema, URL/context, source content, and output allowance.
- Reconcile actual provider usage after every call and stop before exceeding the approved run ceiling.

### C. Harden provider responses

- Require an accepted success `finish_reason` rather than rejecting only `length`.
- Reject refusals, filtering terminations, missing/invalid usage, malformed JSON, and schema violations.
- Preserve sanitized failure evidence and usage without storing raw secrets.
- Make probe/extraction evidence append-only or uniquely keyed by run/attempt.
- Include exact deployment/model-version information in drift checks or require a fresh receipt after a deployment version change.

### D. Consolidate DAAD evidence

- Choose one specific DAAD EPOS route.
- Attach all relevant official artifacts to one canonical candidate without duplicating paid work.
- Confirm source ownership, route scope, cycle scope, and source roles.
- Resolve missing bundle roles through official pages/documents or record an explicit blocker.
- Respect robots restrictions.

### E. Approval packet

When code, tests, source bundle, and preflight are ready, stop and ask Wasim for the paid-call approval. Report:

- candidate identity and ID;
- official source list and role of each source;
- bundle gaps, if any;
- objectives that will run per artifact;
- exact maximum number of model calls;
- maximum input/output tokens and estimated cost;
- current capability receipt and expiry;
- confirmation that the queue contains no unrelated work;
- confirmation that retries are zero;
- exact command/action to be authorized;
- how the worker will stop after this candidate.

Do not interpret “continue,” prior approval, or this prompt as paid-call approval.

### F. Pilot verification

After explicit approval, process only the approved candidate. Then stop and verify:

- durable attempt and usage records;
- all objective results;
- exact evidence alignment;
- route/cycle scope;
- conflicts and duplicates;
- all 15 readiness dimensions;
- admin review rendering;
- actual call count, tokens, cost, and errors.

If any field is wrong or unsupported, keep the candidate private, classify the failure, implement the smallest correction with fake/captured tests, and request new approval before another paid call.

## Milestone 2 instructions: golden cohort

After DAAD passes, implement the ten-program golden cohort from the main plan. Use one current, specific route from each family and verify current Pakistan eligibility from official sources.

Prepare/acquire sources without paid AI first. Present one bounded batch approval packet only after all ten bundles are reviewed. Process in small groups, preserving resumability and per-candidate cost.

The golden cohort is complete only when all ten routes are review-ready, every mandatory public fact has exact official evidence, and repeated failure patterns have regression tests.

Do not count a general programme landing page as a completed scholarship route when its eligibility, deadline, documents, or application process varies by route.

## Inventory and scale-wave instructions

Build the authoritative inventory defined in the main plan. Prioritize applicant value:

1. Pakistan/HEC and bilateral routes;
2. flagship government programmes;
3. major multilateral scholarships;
4. globally prominent university scholarships;
5. high-value specialist and university routes.

For every inventory item, classify current Pakistan eligibility as `confirmed`, `excluded`, `unclear`, or `varies_by_route`. A programme name alone is not sufficient.

Run the 50, 150, 300, and 500+ waves sequentially. For every wave:

- acquire and review sources before extraction;
- calculate a hard batch budget from measured golden-cohort usage;
- obtain explicit approval for that paid batch;
- keep all results private until reviewed;
- publish only through the existing readiness/admin controls and only with explicit publication authorization;
- report inventory, sources-ready, extracted, review-ready, published, blocked, stale, call, token, and cost counts;
- stop expansion if evidence quality, schema validity, cost, duplicate backlog, or review backlog crosses the plan threshold.

Do not start extracting hundreds of candidates merely because Azure quota permits it. Extraction throughput must not outrun source verification or human review.

## Product-integration instructions

Only approved catalogue records may feed student-facing features.

- React catalogue: show funding components, eligibility, cycle/deadline, documents, application method, official citations, and last verification date.
- Profile matcher: use normalized evidence-backed eligibility and explain match/no-match/uncertain outcomes.
- AI assistant: answer from approved facts and citations, identify route/cycle, and abstain when evidence is absent or stale.
- Deadline/document planning: use supported route-specific rules and notify users when evidence becomes stale.

Never expose private candidates, unresolved claims, debug data, credentials, or admin-only placeholders through public APIs.

## Testing strategy

Use the smallest useful test loop:

1. focused unit tests for the changed module;
2. relevant ingestion/preflight/provider/integration tests;
3. lint/format/type checks for changed files;
4. full non-E2E backend suite at milestone gates;
5. frontend tests and type checking for UI/API changes;
6. Docker/real-database tests for transaction, lease, migration, and worker behaviour;
7. browser/E2E tests only when the relevant local stack is running and no paid provider can be reached.

Tests must prove failure paths as well as success paths: missing receipt, expired receipt, wrong deployment/version, non-stop finish reason, refusal, filtering, budget exhaustion, stop switch, worker restart, duplicate sources, partial objectives, stale evidence, and interrupted/resumed runs.

Do not weaken assertions or remove safety checks just to make tests pass.

### Test-failure recovery protocol

Use this protocol without asking Wasim to choose the steps:

1. Capture the command, exit code, and relevant stderr/stdout.
2. Check the project test configuration and confirm the selected interpreter/environment.
3. If the command is malformed, correct it and rerun it.
4. If collection fails, isolate the first collection error and inspect its import/configuration cause.
5. If a test fails, rerun the smallest failing test with useful verbosity and no paid/external provider access.
6. Fix a repository defect only after reproducing it and understanding the expected behaviour.
7. Rerun the focused test, then the related suite, then the milestone gate.
8. Log a concise result and continue implementation.

Do not treat a test exit code as an invitation to stop. Stop only if resolving it requires one of the explicit approval boundaries in this prompt.

## Required progress report after each meaningful task

Use this format:

### Outcome

What user-visible or milestone result was achieved.

### Changes

Files and behaviour changed. Mention migrations and configuration changes explicitly.

### Verification

Exact tests/checks run and whether they passed, failed, or were skipped.

### Catalogue evidence

Candidate/run status, source count, readiness result, model calls, tokens, and cost. State `0` explicitly when no model call occurred.

### Remaining blockers

Only concrete blockers for the active milestone.

### Next action

The next smallest task. If approval is required, state exactly what action requires it and do nothing irreversible while waiting.

## Completion rules

Continue implementing within the active milestone instead of stopping after analysis or producing another high-level plan. Pause only when:

- explicit authorization is required for a paid call, deployment, publication, destructive operation, or secret/credential change;
- a product choice would materially alter Wasim’s intended catalogue;
- external login or owner-only access is required;
- the same verified blocker cannot be resolved safely from the repository and available environment.

Before declaring a blocker, include the evidence inspected, diagnostics attempted, exact reason further safe progress is impossible, and the specific owner action required. “A command failed,” “I am unsure which test to run,” or “would you like me to continue?” are not valid blockers.

Never report the complete project as finished until the final acceptance conditions in `docs/goal-first-scholarship-catalogue-go-live-plan.md` are evidenced. If the token/context budget becomes limited, finish the current safe unit of work, update the execution log precisely, and leave the repository in a stopped, recoverable state for the next session.

At the end of your work, provide a complete audit handoff containing:

- branch and commit/state summary;
- all files changed;
- milestones completed and not completed;
- exact catalogue counts by state;
- source acquisition and blocker counts;
- test/lint/type-check results;
- every paid model call with tokens and cost;
- Azure/runtime configuration changes;
- migrations and database effects;
- known defects, skipped proofs, and security concerns;
- exact commands or steps needed to reproduce the final verification.

The next reviewer must be able to verify your work from repository, database, and runtime evidence rather than trusting the narrative.

---
