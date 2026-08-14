# Weaknesses 107–145 — architecture review

Baseline reviewed: `main` commit `0c92104527e412824c754ed11596a921e5c94253`.

This review re-evaluates the original audit against the current implementation. It does not treat the original recommendation as automatically correct. “Partial” means a real external proof or data-curation outcome remains and must not be presented as closed by code alone.

## Weakness 107 — route-level code splitting

1. **Original problem:** Every feature page is eagerly imported into the initial React bundle.
2. **Current implementation:** `frontend/src/App.tsx` statically imports catalogue, application detail, Assistant, Document Lab, Community, and administrator pages.
3. **Validity:** Valid.
4. **Root cause:** The router was built before feature bundles became substantial.
5. **Impact:** Slower first load and unnecessary parsing of privileged/high-cost feature code.
6. **Scaling impact:** Bundle cost grows with every future Research/mobile-supporting web feature.
7. **Mobile impact:** Backend contracts are unaffected; mobile clients benefit indirectly because business logic stays server-side.
8. **Options:** Keep eager imports; manually split only admin; use `React.lazy` at all feature boundaries.
9. **Recommendation:** Lazy-load all feature pages behind route-level `Suspense`, while keeping the small public/auth shell eager.
10. **Why simplest scalable:** Native React/Vite splitting adds no dependency and gives each future feature a clear boundary.
11. **Files:** `frontend/src/App.tsx`, frontend build tests.
12. **Migration:** None.
13. **Compatibility:** Routes and API contracts remain unchanged.
14. **Regression risk:** Missing fallback or a named/default export mismatch.
15. **Tests:** Assert lazy chunks are emitted and key routes still render.
16. **CI:** Frontend tests, TypeScript build, browser E2E.
17. **Decision:** **FIX**.

## Weakness 108 — manual server-state handling

1. **Original problem:** Pages duplicate loading/error/effect/reload state.
2. **Current implementation:** The pattern remains across catalogue, matching, command centre, Community, Document Lab, Assistant, and admin pages.
3. **Validity:** Valid, but the current product does not yet justify a large state framework migration.
4. **Root cause:** Each feature added its own fetch lifecycle.
5. **Impact:** Inconsistent retry, stale-response, and error behaviour.
6. **Scaling impact:** Duplication compounds as web modules and teams grow.
7. **Mobile impact:** No business rule may move into the hook; stable backend APIs remain canonical.
8. **Options:** Do nothing; add TanStack Query now; introduce a small typed cancellable query hook and reassess when cache/invalidation complexity grows.
9. **Recommendation:** Centralize read lifecycle in a typed `useServerQuery` hook, with explicit reload/invalidation and abort support; do not introduce a larger dependency prematurely.
10. **Why simplest scalable:** Removes the repeated failure-prone lifecycle while preserving an easy later migration to TanStack Query.
11. **Files:** New frontend query hook and major feature pages.
12. **Migration:** None.
13. **Compatibility:** No route or API change.
14. **Regression risk:** Incorrect dependency keys or reload semantics.
15. **Tests:** Hook cancellation, stale-result suppression, error and reload tests; page regressions.
16. **CI:** Frontend tests/build and browser E2E.
17. **Decision:** **FIX**.

## Weakness 109 — incomplete request cancellation

1. **Original problem:** Components ignore stale results but leave network requests running.
2. **Current implementation:** Several effects use an `active` boolean; `ApiClient.request` can forward a signal but feature adapters do not consistently accept one.
3. **Validity:** Valid.
4. **Root cause:** Cancellation was not part of feature API signatures.
5. **Impact:** Wasted work and possible late refresh/retry activity after navigation.
6. **Scaling impact:** More concurrent searches and AI/document requests increase wasted capacity.
7. **Mobile impact:** Mobile clients need the same cancellable HTTP semantics; no server contract change is required.
8. **Options:** Continue ignoring results; add component-local controllers; centralize cancellation in the query hook.
9. **Recommendation:** Pass `AbortSignal` through feature adapters and abort on dependency change/unmount.
10. **Why simplest scalable:** Uses the platform standard and composes with the Weakness 108 solution.
11. **Files:** `frontend/src/api/client.ts`, feature API adapters, query hook.
12. **Migration:** None.
13. **Compatibility:** Optional signals preserve callers.
14. **Regression risk:** Treating `AbortError` as a user-visible failure.
15. **Tests:** Abort actually reaches `fetch`; aborted requests do not replace newer data.
16. **CI:** Frontend unit/build and E2E navigation tests.
17. **Decision:** **FIX**.

## Weakness 110 — oversized frontend pages

1. **Original problem:** Large pages mix containers, cards, forms, rendering, and data access.
2. **Current implementation:** Largest feature pages are roughly 200–240 lines; several are compressed into difficult single-line render blocks.
3. **Validity:** Valid as a maintainability issue, not a runtime blocker.
4. **Root cause:** Vertical features were delivered quickly in one file.
5. **Impact:** Review difficulty, conflicts, and weak component-level tests.
6. **Scaling impact:** Future Research and richer application workflows would amplify the problem.
7. **Mobile impact:** Extraction must remain presentation-only; domain rules stay in backend services.
8. **Options:** Arbitrary line limit; wholesale design-system rewrite; split the highest-change pages into container/components/hooks.
9. **Recommendation:** Extract catalogue cards/freshness, navigation, loading/error states, and the largest Assistant/application sections; keep small pages intact.
10. **Why simplest scalable:** Targets real hotspots without a premature component taxonomy.
11. **Files:** `App.tsx`, catalogue, Assistant, applications, shared frontend components.
12. **Migration:** None.
13. **Compatibility:** Rendering and routes remain compatible.
14. **Regression risk:** Prop wiring and accessibility names.
15. **Tests:** Component tests and existing journey tests.
16. **CI:** Frontend tests/build/E2E.
17. **Decision:** **FIX**.

## Weakness 111 — displayed deadline can disagree with the effective cycle

1. **Original problem:** UI displays the top-level deadline while availability uses the current cycle.
2. **Current implementation:** `effective_application_window()` chooses the cycle, but `OpportunitySummaryResponse.application_deadline` still serializes `opportunity.application_deadline`.
3. **Validity:** Valid and directly reproduced in code.
4. **Root cause:** Window state and displayed projection are calculated separately.
5. **Impact:** A student can see a deadline inconsistent with the “open/upcoming/closed” state.
6. **Scaling impact:** Recurring global programmes make this increasingly common.
7. **Mobile impact:** Must be fixed in the backend contract so every client receives the same canonical deadline.
8. **Options:** Recompute in each client; overwrite history; expose an effective-cycle projection.
9. **Recommendation:** Add effective opening/deadline/timezone/cycle ID to the backend projection and display that value; retain the existing field as the canonical effective deadline for backward compatibility.
10. **Why simplest scalable:** One deterministic backend projection serves web, Android, and iOS.
11. **Files:** opportunity lifecycle/schemas/service, frontend catalogue types/pages, tests.
12. **Migration:** No schema change; existing materialized projection remains.
13. **Compatibility:** Existing `application_deadline` stays present but becomes correct; additive cycle metadata is safe.
14. **Regression risk:** Archived/rolling/no-cycle edge cases.
15. **Tests:** Current-cycle deadline differs from top-level; response and UI use the cycle value.
16. **CI:** Backend, frontend, and browser E2E.
17. **Decision:** **FIX**.

## Weakness 112 — verification badge lacks freshness meaning

1. **Original problem:** “Verified official source” can imply current evidence indefinitely.
2. **Current implementation:** API exposes `source_is_fresh` and timestamp, but the catalogue badge is always the same.
3. **Validity:** Valid.
4. **Root cause:** Freshness data was added after the original badge.
5. **Impact:** Users can over-trust old evidence.
6. **Scaling impact:** Reverification workload grows with catalogue size.
7. **Mobile impact:** Backend should expose a stable machine-readable freshness state.
8. **Options:** Timestamp only; client-calculated state; backend freshness enum.
9. **Recommendation:** Add `verification_freshness` (`recent`, `recheck_recommended`, `historical`) and safe labels/tooltips, derived by the evidence policy.
10. **Why simplest scalable:** One enum is consistent across all clients and future freshness thresholds.
11. **Files:** evidence policy, opportunity response, catalogue UI/tests.
12. **Migration:** None.
13. **Compatibility:** Additive response field.
14. **Regression risk:** Boundary dates and archived sources.
15. **Tests:** Each freshness state at exact threshold boundaries.
16. **CI:** Backend/frontend/E2E.
17. **Decision:** **FIX**.

## Weakness 113 — authenticated navigation is too broad

1. **Original problem:** Eleven top-level destinations present tools rather than a guided journey.
2. **Current implementation:** The top bar exposes Dashboard, Profile, Matches, Tracker, Applications, Assistant, Document Lab, Community, Admin, and Security.
3. **Validity:** Valid.
4. **Root cause:** Every new module received a top-level link.
5. **Impact:** Cognitive load and unclear user journey.
6. **Scaling impact:** Future Research/admissions modules would make the navigation unmanageable.
7. **Mobile impact:** Information architecture should map cleanly to mobile tabs and deep links.
8. **Options:** Keep all links; hide features; group them into stable product domains.
9. **Recommendation:** Use Discover, My Scholarships, Applications, Assistant, Community, and Account; place profile/security/admin capabilities in contextual/account navigation.
10. **Why simplest scalable:** Stable domains absorb future features without new top-level tabs.
11. **Files:** `App.tsx`, navigation component, styles, browser tests.
12. **Migration:** None.
13. **Compatibility:** Existing routes remain valid/deep-linkable.
14. **Regression risk:** Tests and users relying on old visible link names.
15. **Tests:** Role-aware navigation, keyboard access, deep-link redirects.
16. **CI:** Frontend and E2E.
17. **Decision:** **FIX**.

## Weakness 114 — Tracker and Applications overlap

1. **Original problem:** `saved_opportunities` and the Application Command Centre hold overlapping state.
2. **Current implementation:** Migration 0010 backfilled applications and links legacy rows, but the old UI/API remain writable and the detail page writes both models.
3. **Validity:** Valid.
4. **Root cause:** Compatibility was retained without a retirement phase.
5. **Impact:** Status drift, duplicate privacy behaviour, and two user experiences.
6. **Scaling impact:** Synchronization becomes costly with reminders, documents, mobile clients, and background jobs.
7. **Mobile impact:** Mobile must have one canonical application resource and stable ID.
8. **Options:** Permanent dual-write; immediate destructive drop; expand/migrate/deprecate/contract.
9. **Recommendation:** Make Applications canonical now, remove Tracker from the web journey, stop new frontend dual-writes, mark legacy endpoints deprecated with a documented sunset, verify complete backfill, and defer table removal to a later contract release.
10. **Why simplest scalable:** Eliminates new divergence without a risky same-release table drop.
11. **Files:** frontend routes/pages/adapters, application service/routes, migration/deprecation documentation and tests.
12. **Migration:** Add a no-loss backfill/assertion migration only if current migration coverage finds missing rows; do not drop legacy data in this release.
13. **Compatibility:** Legacy endpoints remain temporarily with deprecation headers; existing deep link redirects.
14. **Regression risk:** Orphaned saved rows or broken old clients.
15. **Tests:** Backfill completeness, one canonical create, legacy deprecation contract, privacy export/delete.
16. **CI:** Clean PostgreSQL migration, backend/frontend/E2E.
17. **Decision:** **FIX** using expand/migrate/deprecate; physical contract remains scheduled.

## Weakness 115 — Python dependencies are not fully locked

1. **Original problem:** Range-based resolution can change between releases.
2. **Current implementation:** `pyproject.toml` constrains ranges; only Ruff is exact. No Python lock exists.
3. **Validity:** Valid.
4. **Root cause:** Editable installs were used as both development and release installation.
5. **Impact:** Non-reproducible CI/image builds and surprise dependency drift.
6. **Scaling impact:** More workers/providers increase transitive dependency risk.
7. **Mobile impact:** Stable backend releases reduce unexpected API behaviour.
8. **Options:** Pin every direct dependency manually; `pip freeze`; maintain a resolved `uv.lock`.
9. **Recommendation:** Commit `uv.lock`, use `uv sync --locked` in CI and `uv export --locked`/locked installation in the production image, with deliberate update workflow.
10. **Why simplest scalable:** One modern resolver lock covers production and dev groups without hand-maintained transitive pins.
11. **Files:** `uv.lock`, Dockerfile, CI, dependency documentation.
12. **Migration:** None.
13. **Compatibility:** Project metadata remains installable; release paths become locked.
14. **Regression risk:** Extras/group mismatch between CI and image.
15. **Tests:** Lock check, clean sync, image build.
16. **CI:** `uv lock --check`, locked sync, full suite.
17. **Decision:** **FIX**.

## Weakness 116 — mutable production base-image tags

1. **Original problem:** Node and Python base tags can resolve to different bytes.
2. **Current implementation:** Dockerfile uses mutable `node:24-bookworm-slim` and `python:3.12-slim-bookworm`.
3. **Validity:** Valid.
4. **Root cause:** Tags were chosen for readability without digest provenance.
5. **Impact:** Non-reproducible and potentially compromised builds.
6. **Scaling impact:** Multiple environments can silently run different bases.
7. **Mobile impact:** None directly; backend release reliability matters to all clients.
8. **Options:** Floating tags; private mirrored bases; reviewed tag plus digest.
9. **Recommendation:** Pin reviewed official images by digest while retaining readable tags and automate deliberate refresh PRs.
10. **Why simplest scalable:** Digest pinning needs no new registry architecture.
11. **Files:** Dockerfile and release documentation.
12. **Migration:** Rebuild only.
13. **Compatibility:** Same major runtimes.
14. **Regression risk:** Architecture-specific digest or stale security fixes.
15. **Tests:** Multi-stage image build and Trivy scan.
16. **CI:** Release image build/security scan.
17. **Decision:** **FIX**.

## Weakness 117 — external Compose volume blocks fresh onboarding

1. **Original problem:** A fresh `docker compose up` requires a pre-created external volume.
2. **Current implementation:** `postgres_data` is explicitly external and named for an old project.
3. **Validity:** Valid.
4. **Root cause:** Preservation of one existing development database was made the default.
5. **Impact:** New contributors receive an avoidable startup failure.
6. **Scaling impact:** More contributors and CI/dev environments increase friction.
7. **Mobile impact:** None.
8. **Options:** Document manual creation; make external optional override; use a managed default volume.
9. **Recommendation:** Use a normal managed volume in `compose.yaml`; provide an opt-in legacy-volume override and migration note.
10. **Why simplest scalable:** Fresh environments work immediately while existing data has an explicit path.
11. **Files:** Compose files and README.
12. **Migration:** Developer-only volume copy/override; no production data.
13. **Compatibility:** Existing users can select the legacy override.
14. **Regression risk:** A developer accidentally starts with an empty database.
15. **Tests:** `docker compose config` for default and legacy override.
16. **CI:** Compose validation.
17. **Decision:** **FIX**.

## Weakness 118 — Document Lab capability can appear enabled without workers

1. **Original problem:** API enablement does not prove scanner, worker, or provider readiness.
2. **Current implementation:** Policy returns an `enabled` flag; Compose enables the API by default while scanner/worker live behind an optional profile.
3. **Validity:** Valid.
4. **Root cause:** Feature permission and operational readiness are represented by one flag.
5. **Impact:** Users can upload into a workflow that cannot progress.
6. **Scaling impact:** Separate replicas/workers make capability state more important.
7. **Mobile impact:** Mobile needs machine-readable capability/reason codes rather than web assumptions.
8. **Options:** Disable locally always; force all workers; expose component readiness and fail closed for intake.
9. **Recommendation:** Return `feature_enabled`, `scanner_ready`, `worker_ready`, `analysis_provider_ready`, and `accepting_uploads`; default Compose to disabled unless the complete documents profile is selected.
10. **Why simplest scalable:** Explicit capability status works for local, Azure, web, and mobile without service discovery complexity.
11. **Files:** config, Document Lab schemas/routes/service, health, Compose, frontend/tests.
12. **Migration:** None.
13. **Compatibility:** Preserve `enabled` temporarily as a derived alias.
14. **Regression risk:** False negatives if worker health TTL is too strict.
15. **Tests:** Every partial configuration, stale worker, provider-unavailable editorial mode.
16. **CI:** Backend/frontend/Compose and feature-gate tests.
17. **Decision:** **FIX**.

## Weakness 119 — coverage is measured but not enforced

1. **Original problem:** Coverage can regress without failing CI.
2. **Current implementation:** CI emits coverage but has no `--cov-fail-under` threshold; the verified baseline is approximately 88%.
3. **Validity:** Valid.
4. **Root cause:** Coverage reporting was introduced before a ratchet policy.
5. **Impact:** Important paths can silently lose regression tests.
6. **Scaling impact:** More modules make unaudited coverage decline likely.
7. **Mobile impact:** Backend contract regressions affect all clients.
8. **Options:** 100% immediately; no threshold; conservative ratchet below the current baseline.
9. **Recommendation:** Start at 85%, publish the report, and raise deliberately after each remediation phase.
10. **Why simplest scalable:** Prevents material regression without incentivising meaningless tests.
11. **Files:** CI and test policy documentation.
12. **Migration:** None.
13. **Compatibility:** None.
14. **Regression risk:** Platform-dependent branches may move coverage slightly.
15. **Tests:** CI self-evidence that threshold is applied.
16. **CI:** Backend pytest must fail below threshold.
17. **Decision:** **FIX**.

## Weakness 120 — security-scan name overstates coverage

1. **Original problem:** The named step claims filesystem, dependency, secret, and image scanning while configuration performs one image scan.
2. **Current implementation:** The claim remains in `.github/workflows/ci.yml`; `scan-type: image` is the only Trivy invocation.
3. **Validity:** Valid; the prior green run proves the configured image scan, not every named scanner.
4. **Root cause:** The step label was expanded without expanding scanner invocations.
5. **Impact:** False assurance and missed source/IaC/secrets findings.
6. **Scaling impact:** Infrastructure and provider integrations increase attack surface.
7. **Mobile impact:** Compromised backend/release artifacts affect every client.
8. **Options:** Rename narrowly; add separate source/IaC/secret and image scans; introduce a large security platform.
9. **Recommendation:** Run explicit Trivy filesystem/misconfiguration/secret scanning plus image vulnerability scanning, each fail-closed and clearly named.
10. **Why simplest scalable:** Uses the existing scanner and produces honest gates without a new service.
11. **Files:** CI workflow and security documentation.
12. **Migration:** None.
13. **Compatibility:** None.
14. **Regression risk:** Legitimate secret-test fixtures or IaC false positives need reviewed ignores, never blanket suppression.
15. **Tests:** Deliberate safe fixture/config verification and workflow lint.
16. **CI:** Both scan steps must execute and pass.
17. **Decision:** **FIX**.

## Weakness 121 — Actions are tag-pinned rather than SHA-pinned

1. **Original problem:** Mutable action tags widen the CI supply-chain trust boundary.
2. **Current implementation:** Checkout, setup, Azure login/CLI, and Trivy use version tags.
3. **Validity:** Valid.
4. **Root cause:** Readable major tags were used as defaults.
5. **Impact:** Tag compromise or retargeting can execute unreviewed code with repository/OIDC permissions.
6. **Scaling impact:** More release workflows increase privileged action exposure.
7. **Mobile impact:** Release provenance is shared by all clients.
8. **Options:** Keep tags; vendor actions; pin reviewed immutable SHAs with version comments.
9. **Recommendation:** Pin every third-party action to a reviewed full commit SHA and update intentionally.
10. **Why simplest scalable:** Strong immutability without vendoring maintenance.
11. **Files:** All GitHub workflows and dependency-update policy.
12. **Migration:** None.
13. **Compatibility:** Action inputs remain unchanged.
14. **Regression risk:** Incorrect SHA or cross-major behaviour.
15. **Tests:** Workflow syntax and actual CI execution.
16. **CI:** Every workflow must start and complete using the pins.
17. **Decision:** **FIX**.

## Weakness 122 — Chromium-only browser validation

1. **Original problem:** Firefox and WebKit/Safari behaviour is untested.
2. **Current implementation:** CI installs only Chromium; pytest-playwright supports other engines but is not invoked for them.
3. **Validity:** Valid.
4. **Root cause:** Full-suite runtime was minimised for beta speed.
5. **Impact:** Authentication, forms, layout, and WebAuthn-related behaviour can differ.
6. **Scaling impact:** A broader global/mobile-web audience increases browser diversity.
7. **Mobile impact:** WebKit is especially relevant to iOS web views and Safari users.
8. **Options:** Full suite on all browsers; Chromium only; small cross-browser compatibility matrix.
9. **Recommendation:** Keep the full suite on Chromium and run a focused public/auth/catalogue compatibility marker on Firefox and WebKit.
10. **Why simplest scalable:** Captures engine differences without tripling the whole E2E cost.
11. **Files:** CI, pytest markers, browser tests.
12. **Migration:** None.
13. **Compatibility:** None.
14. **Regression risk:** Timing differences and unsupported browser-specific APIs.
15. **Tests:** Keyboard/auth/catalogue/API error journeys in all three engines.
16. **CI:** Chromium full pass plus Firefox/WebKit compatibility passes.
17. **Decision:** **FIX**.

## Weakness 123 — accessibility is not a strong automated gate

1. **Original problem:** Manual checklist and one keyboard test do not catch common accessibility regressions.
2. **Current implementation:** Semantic markup is generally good and manual guidance exists, but no page-level automated audit gate exists.
3. **Validity:** Valid.
4. **Root cause:** Accessibility was documented before repeatable automation was added.
5. **Impact:** Missing names, landmark/heading errors, duplicate IDs, and inaccessible controls can reach beta.
6. **Scaling impact:** More pages increase manual review burden.
7. **Mobile impact:** Accessible semantics also improve mobile web and future cross-client design contracts.
8. **Options:** Manual-only; add a dependency-heavy suite; add an E2E DOM/accessibility contract plus retain screen-reader testing.
9. **Recommendation:** Add fail-closed automated checks for named controls, labels, landmarks, headings, duplicate IDs, images, and critical ARIA on registration, catalogue, matches, applications, Assistant, and account/security; retain manual AT testing.
10. **Why simplest scalable:** Meaningful release automation without pretending it replaces assistive-technology validation.
11. **Files:** browser test helper/suite, accessibility runbook.
12. **Migration:** None.
13. **Compatibility:** None.
14. **Regression risk:** Audit helper false positives; rules must be explicit and reviewed.
15. **Tests:** Required key journeys and a deliberate violation unit test for the helper.
16. **CI:** Accessibility tests are part of Browser E2E, not optional.
17. **Decision:** **FIX**.

## Weakness 124 — `main` is not protected

1. **Original problem:** GitHub does not enforce PR/CI/no-force-push rules.
2. **Current implementation:** Live branch metadata still reports `protected: false`; Rulesets API reports that the private repository requires GitHub Pro or public visibility.
3. **Validity:** Valid and externally verified.
4. **Root cause:** GitHub plan capability, not application code.
5. **Impact:** A direct push can bypass all otherwise trustworthy CI.
6. **Scaling impact:** Risk rises immediately with more collaborators or automation.
7. **Mobile impact:** Release governance protects the stable API used by old mobile versions.
8. **Options:** Make code public temporarily (rejected); remain unprotected; upgrade to Pro and enforce rules.
9. **Recommendation:** Keep private, upgrade to GitHub Pro, require PR plus Test/Browser E2E/Security Scan (and infrastructure when relevant), block force push/deletion, require conversation resolution.
10. **Why simplest scalable:** Native GitHub enforcement is the correct trust boundary.
11. **Files/config:** Repository settings/ruleset; no code file can substitute.
12. **Migration:** None.
13. **Compatibility:** Workflow check names must be stable before enabling.
14. **Regression risk:** Misnamed required checks can block merges.
15. **Tests:** Attempt a direct push and a red-check merge after enabling.
16. **CI:** Required checks must be observed as enforced, not merely green.
17. **Decision:** **PARTIAL / EXTERNAL BLOCKER** until GitHub Pro protection is actually enabled and verified.

## Weakness 125 — unsigned latest release commit

1. **Original problem:** Release provenance lacked signature evidence at audit time.
2. **Current implementation:** GitHub’s live commit API reports `main` commit `0c921045…` as `verified: true`, reason `valid`, committed by verified `web-flow` with a valid PGP signature.
3. **Validity:** No longer valid for the latest release commit.
4. **Root cause:** The old audit inspected an earlier commit/state.
5. **Impact:** Current release provenance is cryptographically verified by GitHub.
6. **Scaling impact:** Future release commits/tags must preserve the verified path.
7. **Mobile impact:** Signed releases help trace backend versions serving mobile clients.
8. **Options:** Add a private signing key to CI (rejected); use GitHub verified merges; later sign release tags with an approved key/keyless process.
9. **Recommendation:** Preserve GitHub verified merges and document verified signed release tags for formal releases.
10. **Why simplest scalable:** No new long-lived signing secret is introduced.
11. **Files:** Release documentation only.
12. **Migration:** None.
13. **Compatibility:** None.
14. **Regression risk:** Direct/local unsigned commits if governance remains unenforced.
15. **Tests:** Check `verification.verified` for final release SHA.
16. **CI:** Record final SHA verification in release evidence.
17. **Decision:** **ALREADY FIXED** for current `main`; governance follow-through belongs to Weakness 124.

## Weakness 126 — candidate receives traffic before readiness

1. **Original problem:** Deployment passes `initialTrafficToLatest=true`, routing users before smoke validation.
2. **Current implementation:** Container Apps uses multiple revisions, but the workflow explicitly sets 100% latest traffic before checking the shared FQDN.
3. **Validity:** Valid and high severity.
4. **Root cause:** Bootstrap and subsequent-deployment behaviour share one parameter.
5. **Impact:** An unhealthy candidate can receive all live traffic.
6. **Scaling impact:** More revisions and users make rollback exposure larger.
7. **Mobile impact:** Mobile retries/offline queues make transient incompatible deployments more harmful.
8. **Options:** Shared-FQDN check after promotion; temporary app; zero-traffic revision with revision-specific URL then atomic traffic shift.
9. **Recommendation:** Deploy at zero traffic, resolve the candidate revision name/FQDN, run protected smoke against it, then shift 100% traffic; automatically retain/restore the prior revision on failure.
10. **Why simplest scalable:** Uses native Container Apps multiple revisions without another environment or orchestrator.
11. **Files:** Azure workflow, application Bicep, release scripts/tests.
12. **Migration:** Deployment-process change only.
13. **Compatibility:** Bootstrap requires an explicit separately confirmed path; normal releases are zero traffic.
14. **Regression risk:** Incorrect revision-label/FQDN or traffic command.
15. **Tests:** Static workflow assertions and an actual staging promotion/rollback drill.
16. **CI:** Bicep compile; workflow validation; staging evidence required.
17. **Decision:** **FIX** in code; actual staging proof is tracked under 131.

## Weakness 127 — required GitHub Environments are absent

1. **Original problem:** Workflow comments assume approval gates that repository configuration does not contain.
2. **Current implementation:** Live API reports zero environments; workflow references `azure-staging`/`azure-beta` dynamically.
3. **Validity:** Valid.
4. **Root cause:** Deployment code preceded repository/Azure account setup.
5. **Impact:** A workflow can create an unprotected environment name and run without the claimed review boundary.
6. **Scaling impact:** Multiple deployers make implicit approval unsafe.
7. **Mobile impact:** Controlled promotion is essential for API backward compatibility.
8. **Options:** Comments only; hard-code jobs but leave environments unprotected; create environments with reviewers/branch rules and verify protection.
9. **Recommendation:** Create both environments, configure separate required reviewers and main-only deployment policy, bind separate OIDC subjects, and add a preflight that refuses deployment without approved environment evidence.
10. **Why simplest scalable:** Uses native GitHub/Azure identity boundaries.
11. **Files/config:** GitHub Environments, Entra federated credentials, workflow preflight/runbook.
12. **Migration:** External configuration only.
13. **Compatibility:** Workflow environment names remain stable.
14. **Regression risk:** Self-approval/plan limitations or incorrect OIDC subject.
15. **Tests:** API/UI inspection of protection rules and a denied unapproved deployment.
16. **CI:** Deployment workflow must remain blocked pending approval.
17. **Decision:** **PARTIAL / EXTERNAL BLOCKER** until environments and reviewers are actually configured and observed.

## Weakness 128 — beta digest lacks staging provenance

1. **Original problem:** Any syntactically valid ACR digest can be supplied for beta.
2. **Current implementation:** Workflow validates registry/repository shape only; no signed staging attestation is consumed.
3. **Validity:** Valid.
4. **Root cause:** Promotion was modelled as a text input rather than evidence.
5. **Impact:** Untested image promotion can bypass staging.
6. **Scaling impact:** More releases/operators increase accidental or malicious substitution risk.
7. **Mobile impact:** Immutable, proven backend releases protect older clients.
8. **Options:** Manual copy/paste; query the last staging run loosely; generate a signed/checksummed promotion manifest artifact.
9. **Recommendation:** Staging writes a manifest with digest, commit, CI run, deployment run, smoke result, environment, and timestamp; beta downloads the exact artifact from an approved successful staging run and verifies every field.
10. **Why simplest scalable:** GitHub artifact provenance is sufficient before introducing a separate release service.
11. **Files:** Deployment workflow, manifest validation script/tests, runbook.
12. **Migration:** None.
13. **Compatibility:** Beta input changes from arbitrary digest to staging run ID/artifact.
14. **Regression risk:** Artifact retention/permissions and repository dispatch ambiguity.
15. **Tests:** Reject altered digest/commit/environment/failed smoke; accept exact manifest.
16. **CI:** Script tests plus actual staging-to-beta drill.
17. **Decision:** **FIX** in code; production proof remains coupled to 131.

## Weakness 129 — migrations precede candidate validation

1. **Original problem:** A new schema is applied before candidate compatibility is demonstrated.
2. **Current implementation:** Migration job is the first environment mutation; API is deployed afterwards.
3. **Validity:** Valid.
4. **Root cause:** Readiness was treated as post-migration startup only.
5. **Impact:** Existing revision can break against an incompatible schema.
6. **Scaling impact:** Longer deployments and more replicas enlarge mixed-version windows.
7. **Mobile impact:** API downtime or contract drift affects clients that cannot be instantly updated.
8. **Options:** Deploy new code first regardless of schema; migrate first; require expand/contract compatibility and validate old/new combinations before mutation.
9. **Recommendation:** Run compatibility gates before Azure mutation, require an expand migration, apply it, deploy zero-traffic candidate, smoke, promote, and defer contract migrations to a later release after old revisions are retired.
10. **Why simplest scalable:** Preserves the modular monolith and PostgreSQL while making rolling deployment safe.
11. **Files:** CI compatibility tests, migration policy script, Azure workflow/runbook.
12. **Migration:** Future destructive operations require explicit contract phase; current chain is classified.
13. **Compatibility:** Old app + new schema is mandatory.
14. **Regression risk:** Static policy alone misses semantic incompatibility.
15. **Tests:** Old app/new schema, new app/new schema, rollback app/new schema for high-risk migrations.
16. **CI:** Migration compatibility gate before deploy workflow can run.
17. **Decision:** **FIX** policy/mechanics; actual drill under 131.

## Weakness 130 — migration safety is not mechanically enforced

1. **Original problem:** Expand/contract exists only in prose.
2. **Current implementation:** Clean upgrade is tested; downgrade coverage exists, but no dangerous-operation classifier or mixed-version release gate exists.
3. **Validity:** Valid.
4. **Root cause:** Migration testing focused on schema correctness rather than rolling compatibility.
5. **Impact:** DROP/rename/not-null/type changes can silently violate rollback.
6. **Scaling impact:** Larger tables also introduce lock/backfill risk.
7. **Mobile impact:** Stable API requires schema changes that tolerate multiple backend versions.
8. **Options:** Manual review only; block every schema change; lint high-risk Alembic operations and require an explicit reviewed exception/phase.
9. **Recommendation:** Add a migration-safety checker for destructive/locking operations, require migration metadata (`phase`, backfill, lock, rollback), and run mixed-version tests for flagged migrations.
10. **Why simplest scalable:** A focused checker catches the dominant hazards without a database migration platform.
11. **Files:** migration checker script/tests, migration template, CI, runbook.
12. **Migration:** Existing revisions are baseline-allowlisted with rationale; new revisions comply.
13. **Compatibility:** No runtime API change.
14. **Regression risk:** Regex-only linting can miss dynamic operations; AST/operation inspection and explicit review remain necessary.
15. **Tests:** Known safe/unsafe migration fixtures and clean PostgreSQL head.
16. **CI:** Checker and compatibility suite are mandatory.
17. **Decision:** **FIX**.

## Weakness 131 — deployment workflow has never run

1. **Original problem:** Compilation is not staging proof.
2. **Current implementation:** Live GitHub data reports zero runs of `azure-application-deploy.yml`.
3. **Validity:** Valid.
4. **Root cause:** Azure staging/OIDC/environments have not been provisioned in this connected environment.
5. **Impact:** Networking, identities, secrets, migration, smoke, traffic, and rollback remain unproven.
6. **Scaling impact:** Production uncertainty is unacceptable before real users.
7. **Mobile impact:** Deployment reliability protects mobile availability and backward compatibility.
8. **Options:** Claim based on compile (rejected); deploy without gates (rejected); run a controlled staging drill after code and external prerequisites.
9. **Recommendation:** Complete 126–130/132–133, configure 127, then run and preserve staging deployment, rollback, migration, smoke, and restore evidence.
10. **Why simplest scalable:** One production-like staging environment is sufficient for beta proof.
11. **Files/config:** Workflow/runbook plus Azure/GitHub external resources.
12. **Migration:** Execute clean and upgrade paths in staging.
13. **Compatibility:** Drill must use the exact release candidate digest.
14. **Regression risk:** Credit/cost and accidental beta traffic; staging resource group must be isolated.
15. **Tests:** Actual workflow, revision traffic, rollback, PITR, smoke.
16. **CI:** All code gates plus successful deployment run.
17. **Decision:** **PARTIAL / EXTERNAL VALIDATION REQUIRED**; cannot be honestly closed in a code-only environment.

## Weakness 132 — readiness smoke is too shallow

1. **Original problem:** `/health/ready` proves little beyond DB connectivity/startup.
2. **Current implementation:** Deployment workflow checks only the shared health URL.
3. **Validity:** Valid.
4. **Root cause:** Infrastructure smoke preceded product-journey smoke.
5. **Impact:** Broken frontend, auth, catalogue, Redis, email, and authorization can be promoted.
6. **Scaling impact:** More dependencies make a single probe less representative.
7. **Mobile impact:** Stable API smoke should validate machine-readable auth/catalogue/application contracts.
8. **Options:** Huge destructive E2E against beta; health only; protected, synthetic staging smoke with isolated test account/data.
9. **Recommendation:** Add a redacted smoke script covering frontend asset, readiness, registration policy, auth, catalogue, owner isolation, Redis-backed limiting, application create/delete, and configured provider/worker capability; execute against the candidate revision.
10. **Why simplest scalable:** One bounded script covers the critical dependency graph without production test data.
11. **Files:** smoke script/tests, workflow, runbook.
12. **Migration:** None.
13. **Compatibility:** Uses public/stable API contracts.
14. **Regression risk:** Email/destructive steps need a dedicated staging account and cleanup.
15. **Tests:** Script unit tests with mocked HTTP plus real staging run.
16. **CI:** Static/script tests; deployment run must pass smoke.
17. **Decision:** **FIX** in code; environment execution under 131.

## Weakness 133 — mutable Azure CLI validation version

1. **Original problem:** `azcliversion: latest` changes infrastructure compilation behaviour.
2. **Current implementation:** Azure validation uses `azure/cli@v2` and `latest`.
3. **Validity:** Valid.
4. **Root cause:** Toolchain version was not treated as release input.
5. **Impact:** Non-reproducible Bicep builds and surprise breaking changes.
6. **Scaling impact:** Multiple environments require identical validation/deploy tooling.
7. **Mobile impact:** None directly.
8. **Options:** Latest; custom image; pin Azure CLI and install/pin a reviewed Bicep version.
9. **Recommendation:** Pin action SHA, Azure CLI version, and Bicep CLI version; record them in release evidence.
10. **Why simplest scalable:** Version inputs provide reproducibility without maintaining a runner image.
11. **Files:** Azure workflows and infra README.
12. **Migration:** None.
13. **Compatibility:** Verify templates compile with the chosen versions.
14. **Regression risk:** Old tooling missing a required API feature.
15. **Tests:** Compile every template with the exact pins.
16. **CI:** Azure infrastructure validation.
17. **Decision:** **FIX**.

## Weakness 134 — ACR public network exposure

1. **Original problem:** GitHub-hosted runners require public ACR access while other data services are private.
2. **Current implementation:** ACR admin/anonymous access are disabled and managed identity is used for pull; public network remains enabled for build/push.
3. **Validity:** Valid as residual exposure, not evidence of unauthorized access.
4. **Root cause:** No private self-hosted build runner exists.
5. **Impact:** Registry endpoint is internet reachable, bounded by Entra/RBAC.
6. **Scaling impact:** More builds increase credential/endpoint exposure.
7. **Mobile impact:** None directly; image supply-chain security affects the API.
8. **Options:** Self-hosted private runner; ACR Tasks with controlled identity; retain public endpoint with least privilege for beta.
9. **Recommendation:** Accept for closed beta with OIDC/RBAC, immutable digests, admin disabled, audit alerts, and no broad credentials; move to private build execution when sustained deployment volume justifies it.
10. **Why simplest scalable:** Avoids premature runner infrastructure while maintaining strong authentication.
11. **Files:** Foundation policy assertions, threat model, future infrastructure backlog.
12. **Migration:** Future network transition only.
13. **Compatibility:** None.
14. **Regression risk:** Accidental admin/anonymous enablement.
15. **Tests:** Bicep policy tests assert admin and anonymous disabled; verify role assignments/logging.
16. **CI:** IaC/security scan and staging evidence.
17. **Decision:** **ACCEPTED RISK for closed beta**, with explicit controls and review trigger.

## Weakness 135 — budget is currency-sensitive

1. **Original problem:** Numeric thresholds assume MYR but Azure budgets use subscription billing currency.
2. **Current implementation:** Documentation warns operators; the Bicep parameter itself does not mechanically bind a confirmed currency.
3. **Validity:** Valid.
4. **Root cause:** Budget resources do not perform currency conversion.
5. **Impact:** A “500” budget could represent the wrong financial exposure.
6. **Scaling impact:** Multiple subscriptions/environments increase configuration error likelihood.
7. **Mobile impact:** None.
8. **Options:** Documentation only; hard-code MYR; require an explicit expected/observed currency preflight and evidence.
9. **Recommendation:** Add an explicit allowed billing-currency input and a pre-deployment validation script/workflow that compares Azure-reported cost currency before applying the budget.
10. **Why simplest scalable:** Fails before provisioning without introducing a billing service.
11. **Files:** Cost Bicep, validation script/tests, workflow/runbook.
12. **Migration:** Existing budget must be reviewed/redeployed after confirmation.
13. **Compatibility:** Default remains MYR only when explicitly confirmed.
14. **Regression risk:** Azure API returns mixed/empty currency before usage; require operator evidence fallback.
15. **Tests:** Mismatch rejects; exact currency/amount accepts.
16. **CI:** Script unit tests and Bicep compile.
17. **Decision:** **FIX**.

## Weakness 136 — alerts are not hard spend caps

1. **Original problem:** Azure budgets notify but cannot automatically prevent expensive application behaviour.
2. **Current implementation:** Strong feature gates, beta cap, Assistant per-user daily/monthly/minute limits, Document Lab upload/analysis limits, and Container Apps max replicas already exist; global provider/storage/email circuit breakers are incomplete.
3. **Validity:** Partially valid; the old audit under-described existing controls.
4. **Root cause:** Limits are per-user or infrastructure-specific rather than one operational high-cost policy.
5. **Impact:** Aggregate abuse or misconfiguration can exceed credit before a human reacts.
6. **Scaling impact:** Horizontal replicas need shared global limits.
7. **Mobile impact:** Server-side quotas must apply equally to web and mobile.
8. **Options:** Azure automation that shuts resources down; alerts only; server-side shared quotas plus kill switches and bounded scale.
9. **Recommendation:** Preserve current caps, add explicit global daily/monthly high-cost-operation limits in Redis with fail-closed production behaviour, and expose protected utilization/kill-switch status.
10. **Why simplest scalable:** Extends the existing Redis limiter instead of adding billing-event infrastructure.
11. **Files:** config/rate-limit/capability services, Azure environment values, operations tests/docs.
12. **Migration:** None.
13. **Compatibility:** Return stable 429 machine codes when exhausted.
14. **Regression risk:** Shared store outage or incorrect window calculation.
15. **Tests:** Concurrent cross-replica quota exhaustion, reset windows, kill switch, failure mode.
16. **CI:** Backend Redis integration and config tests.
17. **Decision:** **FIX** remaining aggregate guardrails; existing controls are retained.

## Weakness 137 — product documentation is stale

1. **Original problem:** The README roadmap and product description no longer match implemented phases and operational constraints.
2. **Current implementation:** Detailed subsystem documents exist, but the README still describes completed work as future work and is not a reliable current-state entry point.
3. **Validity:** Valid.
4. **Root cause:** Delivery documents accumulated without one versioned product-state authority.
5. **Impact:** Operators, contributors, and reviewers can deploy or evaluate the wrong capability set.
6. **Scaling impact:** Documentation drift becomes more expensive as teams and environments multiply.
7. **Mobile impact:** Mobile teams need one authoritative list of stable, experimental, and deprecated API capabilities.
8. **Options:** Rewrite every historical document; keep README only; add a concise canonical current-state document and link historical plans as non-authoritative.
9. **Recommendation:** Add `docs/current-product-state.md`, update the README to link it, and explicitly label plans/audits as historical snapshots.
10. **Why simplest scalable:** One maintained authority prevents conflicting rewrites while retaining decision history.
11. **Files:** README and product/operations documentation.
12. **Migration:** None.
13. **Compatibility:** Documentation-only.
14. **Regression risk:** New work can drift again; add a release-review checklist item.
15. **Tests:** Documentation link and terminology checks.
16. **CI:** Existing documentation/reference tests plus a lightweight current-state assertion.
17. **Decision:** **FIX**.

## Weakness 138 — documented deployment assumptions are not fully enforced

1. **Original problem:** Important production assumptions are prose rather than executable policy.
2. **Current implementation:** Settings already fail production startup without Redis, SMTP, operations authentication, external metrics, and Document Lab isolation; environment protection, migration policy, provenance, and cost assumptions remain partly manual.
3. **Validity:** Partially valid; the previous audit missed significant configuration enforcement.
4. **Root cause:** Runtime invariants and release-control invariants evolved in different places.
5. **Impact:** A syntactically valid deployment can violate the intended security or reliability posture.
6. **Scaling impact:** Manual policy interpretation does not survive multiple operators and environments.
7. **Mobile impact:** Misconfigured API deployments break stable contracts for installed clients.
8. **Options:** Documentation only; a large policy platform; focused startup, workflow, and IaC assertions.
9. **Recommendation:** Keep existing startup validation and add mechanical checks for migration metadata, environment provenance, cost currency, zero-traffic candidates, and infrastructure security properties.
10. **Why simplest scalable:** Extends current validation boundaries without introducing a new control plane.
11. **Files:** Settings, deployment scripts/workflows, Bicep validation tests, runbooks.
12. **Migration:** None except release metadata introduced under Weaknesses 128–130.
13. **Compatibility:** Development remains usable through explicit development defaults; production fails closed.
14. **Regression risk:** Overly strict checks can block emergency recovery; document audited break-glass paths.
15. **Tests:** Every invariant has an accept and reject case.
16. **CI:** Backend config tests, workflow policy tests, and Bicep compile.
17. **Decision:** **FIX** remaining unenforced assumptions; retain already-enforced controls.

## Weakness 139 — product positioning exceeds the default AI implementation

1. **Original problem:** The product is branded as an AI assistant while the safe default provider is deterministic and evidence-template based.
2. **Current implementation:** Provider abstraction and grounded deterministic responses are implemented; real inference is configuration-dependent and not the source of truth.
3. **Validity:** Valid as a product-trust issue, not an architectural defect.
4. **Root cause:** Aspirational branding was not separated from currently enabled capability.
5. **Impact:** Users may infer generative reasoning or personalized intelligence that is not active.
6. **Scaling impact:** Trust problems become material when marketing and provider configurations differ by environment.
7. **Mobile impact:** All clients must receive the same server-declared capability and provider-neutral contract.
8. **Options:** Force a model provider; remove AI architecture; use truthful source-backed positioning and expose configured capability.
9. **Recommendation:** Describe the current product as a source-backed scholarship assistant, retain the orchestrator/provider boundary, and expose whether generative inference is enabled without exposing secrets.
10. **Why simplest scalable:** Truthful wording requires no unsafe dependency and remains accurate as providers change.
11. **Files:** README/current-state documentation, user-facing copy, capability response/tests.
12. **Migration:** None.
13. **Compatibility:** API remains additive.
14. **Regression risk:** Copy may diverge across clients; centralize capability wording where practical.
15. **Tests:** Default and configured-provider capability tests; frontend wording tests.
16. **CI:** Backend/frontend tests and production build.
17. **Decision:** **FIX**.

## Weakness 140 — matching and funding language can overstate certainty

1. **Original problem:** Labels such as `strong_match`, `likely_eligible`, and `fully_funded` can be read as guarantees.
2. **Current implementation:** Matching is deterministic and evidence-linked, and `fully_funded` requires confirmed components; however labels and UI rendering still communicate more certainty than the evidence warrants, including `likely_eligible` when information is missing.
3. **Validity:** Valid.
4. **Root cause:** Internal classification names leaked into product language.
5. **Impact:** Applicants can make high-stakes decisions from probabilistic or incomplete evidence.
6. **Scaling impact:** More countries and scholarship schemas increase ambiguity.
7. **Mobile impact:** Safe, stable machine codes must be distinct from localized display text.
8. **Options:** Remove ranking; disclaimer-only; preserve stable internal scores while adding conservative status codes/display labels.
9. **Recommendation:** Return additive `fit_band` and `display_label` fields, map missing information to `requires_verification`, and present funding as confirmed tracked components rather than a guarantee.
10. **Why simplest scalable:** Keeps ranking utility and compatibility while correcting the trust boundary.
11. **Files:** Matching/eligibility/funding response schemas and services, frontend presenters, tests/docs.
12. **Migration:** None.
13. **Compatibility:** Retain legacy fields during a documented deprecation window.
14. **Regression risk:** Clients sorting by legacy labels; numerical ordering remains unchanged.
15. **Tests:** Missing-information, evidence-gap, full-component, serialization, and UI-copy regressions.
16. **CI:** Backend/frontend tests, build, browser journey.
17. **Decision:** **FIX**.

## Weakness 141 — evidence policy is duplicated

1. **Original problem:** Different modules could apply inconsistent evidence thresholds.
2. **Current implementation:** `app/modules/opportunities/evidence_policy.py` is the shared policy used by opportunity, application, and Assistant flows; matching consumes the same canonical opportunity projection.
3. **Validity:** No longer valid on current `main`.
4. **Root cause:** Earlier phase-specific implementations were consolidated after the audit.
5. **Impact:** Current centralization removes the cited inconsistency risk.
6. **Scaling impact:** One policy module is suitable for horizontal API/worker replicas.
7. **Mobile impact:** All clients receive backend-canonical decisions.
8. **Options:** Further policy engine extraction; retain the modular-monolith service.
9. **Recommendation:** Retain the shared module and add a dependency/conformance regression test rather than a new service.
10. **Why simplest scalable:** Avoids a premature service boundary.
11. **Files:** Evidence policy and conformance tests only.
12. **Migration:** None.
13. **Compatibility:** Unchanged.
14. **Regression risk:** Future modules bypass the policy.
15. **Tests:** Cross-module fixtures must yield identical evidence decisions.
16. **CI:** Backend regression suite.
17. **Decision:** **ALREADY FIXED**; strengthen regression evidence.

## Weakness 142 — structured catalogue coverage is incomplete

1. **Original problem:** Reliable eligibility and funding decisions require structured criteria, but many records remain narrative-only.
2. **Current implementation:** Typed eligibility rules, normalized values, funding-component statuses, and quality flags exist. The bundled seed records are draft and lack complete structured rules; they are not safe for high-confidence public decisions.
3. **Validity:** Valid as a data-completion constraint; much of the required schema and enforcement foundation already exists.
4. **Root cause:** Official-source curation is human/data-pipeline work and cannot be safely inferred from prose.
5. **Impact:** Publishing incomplete records as decision-ready would create false eligibility and funding claims.
6. **Scaling impact:** Catalogue growth requires measurable coverage and a bounded review queue, not manual intuition.
7. **Mobile impact:** APIs need explicit completeness/status fields so clients never guess.
8. **Options:** Fabricate rules with AI; block the entire catalogue; keep drafts quarantined, enforce publication thresholds, and report coverage.
9. **Recommendation:** Enforce minimum structured/evidence coverage for decision-ready publication, expose machine-readable completeness, add coverage reporting/backfill tooling, and keep incomplete records draft until official-source review.
10. **Why simplest scalable:** Builds on the existing schema and truth hierarchy without inventing facts.
11. **Files:** Catalogue quality policy, admin/operations metrics, import tooling, tests/docs.
12. **Migration:** Existing drafts remain drafts; any status tightening must be backfilled before enforcement.
13. **Compatibility:** Additive completeness fields; no fabricated eligibility result.
14. **Regression risk:** Over-strict thresholds reduce catalogue breadth; use explicit informational vs decision-ready tiers.
15. **Tests:** Publication rejection, draft visibility, coverage metrics, and incomplete-rule API behavior.
16. **CI:** Backend catalogue/import tests and migration check if status fields change.
17. **Decision:** **PARTIAL / CONTROLLED LIMITATION**: implement enforcement and tooling; official-source curation remains necessary product work.

## Weakness 143 — legacy saved opportunities coexist with canonical Applications

1. **Original problem:** Two writable persistence models represent the same user intent.
2. **Current implementation:** Migration 0010 backfilled and linked saved opportunities, but legacy routes/table remain writable and the frontend still dual-writes.
3. **Validity:** Valid and overlaps Weakness 114.
4. **Root cause:** Expand/migrate was completed without deprecate/contract.
5. **Impact:** Divergent state, duplicate writes, confusing deletion/export semantics.
6. **Scaling impact:** Every new client and job otherwise multiplies reconciliation cost.
7. **Mobile impact:** Mobile must target Applications as the single stable resource.
8. **Options:** Immediate table drop; perpetual synchronization; stop new writes, provide bounded compatibility, verify migration, then contract in a later release.
9. **Recommendation:** Make Applications canonical, remove frontend dual writes/Tracker mutation, emit explicit deprecation metadata for legacy endpoints, retain read compatibility for one release, and document a verified contract migration.
10. **Why simplest scalable:** Ends divergence now without breaking rolling deployments or older clients.
11. **Files:** Frontend routes/adapters, saved-opportunity routes/services, migration verification and deprecation document.
12. **Migration:** No immediate destructive drop; later contract migration only after usage and no-loss checks.
13. **Compatibility:** Time-bounded legacy read compatibility; writes return a stable deprecation error or translate atomically to Applications.
14. **Regression risk:** Old clients still write legacy resources; telemetry and a sunset window are required.
15. **Tests:** No dual write, canonical create/update/delete, legacy compatibility/deprecation headers, export/delete consistency, migration no-loss.
16. **CI:** Backend/frontend/build/browser and clean PostgreSQL migration.
17. **Decision:** **FIX** via expand/migrate/deprecate now; destructive contract is a later verified release.

## Weakness 144 — privacy export and deletion are inconsistent across modules

1. **Original problem:** Each feature implemented data rights independently, risking omissions.
2. **Current implementation:** Account export/closure already covers profile, applications, Assistant, Community, Document Lab, and legal data, and modules expose scoped export/delete. Match history and legacy tracker coverage plus a reusable contract are incomplete.
3. **Validity:** Partially valid; the audit predates substantial remediation.
4. **Root cause:** Ownership was encoded in endpoint orchestration rather than a registered module contract.
5. **Impact:** A user export can be incomplete or closure can leave personal records.
6. **Scaling impact:** Every new module creates another omission opportunity.
7. **Mobile impact:** Rights operations must be server-side, asynchronous-ready, and client-independent.
8. **Options:** Maintain one large endpoint manually; event-driven deletion service; lightweight registered data-rights contributors inside the modular monolith.
9. **Recommendation:** Define a module contributor contract for export/delete inventory, include matches and legacy saved records, and add aggregate conformance tests; retain storage deletion before database cascade.
10. **Why simplest scalable:** A registry provides completeness without introducing a distributed workflow prematurely.
11. **Files:** Auth/account rights service, module contributors, schemas, tests/docs.
12. **Migration:** None unless an omitted non-cascading ownership relation is discovered.
13. **Compatibility:** Preserve existing export envelope and add versioned sections.
14. **Regression risk:** Partial external-storage failure; closure must stop and remain retryable rather than claim success.
15. **Tests:** Complete export inventory, closure residue scan, idempotent retry, storage failure, and legacy/match coverage.
16. **CI:** Backend integration and clean PostgreSQL cascade tests.
17. **Decision:** **FIX** remaining contract and coverage gaps.

## Weakness 145 — concurrency controls are inconsistent

1. **Original problem:** Several high-risk writes used different or insufficient race-control patterns.
2. **Current implementation:** Current `main` has atomic document job claiming, conditional Application version updates, atomic refresh-token rotation, reminder idempotency, audit advisory locking, and PostgreSQL tenant-isolation tests. The cited core races have been remediated.
3. **Validity:** The broad architectural concern remains worth guarding, but the cited concrete defects are already fixed.
4. **Root cause:** Features originally selected locking strategies independently.
5. **Impact:** Without regression evidence, later refactors can reintroduce duplicate work, lost updates, or token reuse.
6. **Scaling impact:** Horizontal API/worker replicas turn latent races into production failures.
7. **Mobile impact:** Retries and offline clients increase concurrent mutation frequency; stable conflict/idempotency codes are required.
8. **Options:** Global pessimistic locking; distributed lock service; document and test a small approved set of database/Redis patterns.
9. **Recommendation:** Retain per-case atomic SQL, optimistic versioning, uniqueness/idempotency, advisory locks, and Redis primitives; document the selection rules and add true simultaneous PostgreSQL/Redis regression tests for the critical paths.
10. **Why simplest scalable:** Uses existing transactional systems and avoids a fragile universal lock abstraction.
11. **Files:** Concurrency design note and integration/security tests; production code only if tests reveal a defect.
12. **Migration:** None expected.
13. **Compatibility:** Preserve 409/429/idempotent outcomes and resource versions.
14. **Regression risk:** SQLite tests can falsely pass; PostgreSQL/Redis tests must be mandatory.
15. **Tests:** Simultaneous refresh rotation, application version conflict, document claim, reminder idempotency, audit append, and shared quota exhaustion.
16. **CI:** Real PostgreSQL and Redis integration jobs must genuinely execute.
17. **Decision:** **ALREADY FIXED** for the cited races; strengthen standards and real concurrency regression evidence.
