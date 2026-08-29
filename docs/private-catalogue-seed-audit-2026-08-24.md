# Private catalogue seed audit - 2026-08-24

## Scope and safety boundary

This is a private discovery-stage audit for a future 500+ verified scholarship catalogue.
It does not authorize publication, deployment, merge, push, production flags, or automatic
approval. The six operator-supplied PDFs and Scholars4Dev are discovery material only. Their
claims are not evidence for catalogue facts.

An accepted catalogue review proposal must eventually contain current official owner evidence for
every supported decision-critical fact. Missing facts stay `unknown`; blocked, login-only, CAPTCHA,
conflicting, or stale sources stay in review.

## Material reviewed

All 43 pages were text-extracted and visually inspected:

- Indonesia guide: 2 pages.
- Australia guide: 3 pages.
- UK list: 5 pages.
- Europe list: 21 pages.
- China list: 7 pages.
- US list: 5 pages.

The PDFs' titles and row counts are not treated as proof that the named opportunities exist or are
current.

## Important quality findings

### Europe PDF

The file is not safe to import as 500 scholarships. It repeatedly combines generic names such as
`National Excellence Fellowship Type-*`, `Top University ... Tier-*`, and
`... Selection-*` with country labels. The same five Erasmus/Horizon/mobility labels are also
repeated as country cohorts. All 500 rows are quarantined as untrusted discovery text. Erasmus
Mundus remains in the seed only because it was separately supplied by the operator and already has
an official European Commission URL hint.

### UK PDF

Rows labelled `Track Variant 4`, `Track Variant 5`, `Track Variant 6`, and `Track Variant 7` are
artificial repetitions, not new scholarship identities. They are removed. Genuine separately named
Commonwealth schemes remain separate candidates; a degree or cycle alone does not create a new
scholarship.

### China PDF

The seven CSC entries are routes or programme variants under one Chinese Government Scholarship
identity until official evidence proves an independently awarded scheme. Shanghai Type A/Type B are
also treated as funding tracks beneath one Shanghai Government Scholarship. Generic university
labels are not automatically accepted; only a small high-priority subset has been retained for
official-source discovery.

### US PDF

Need-based financial aid, assistantships, grants, and professional fellowships are not assumed to be
standalone international scholarships. Rhodes and Gates Cambridge are not US-destination awards and
are deduplicated against their UK canonical identities. Boren and Marshall have audience-mismatch
risks for the Asia/Africa focus and are not high-priority catalogue targets.

### Australia and Indonesia PDFs

Australia Awards, RTP, and KNB are retained as canonical candidates. University awards that offer
tuition only are below the primary funding gate. Darmasiswa is retained only as a lower-priority
non-degree government programme. Degree levels under KNB are scopes, not separate scholarships.

## Seed outcome

`data/seed/private_priority_scholarship_candidates.v1.json` is the ingestion-compatible private
manifest. Each object is only a candidate identity. `possible_official_url` is an owner-domain hint,
not proof that the page is current or that any funding claim is correct.

Priority semantics:

- `priority-0`: famous/government or strong Asia/Africa fit, with a claimed full-tuition-plus-stipend
  package that must still be proven from official sources.
- `priority-1`: potentially strong full-funding candidate, but scope, audience, route, or benefit
  completeness needs closer review.
- `priority-2`: partial funding, non-degree, audience mismatch, ambiguous identity, or a known gap
  against the primary funding gate.

## Review-queue entry gate

A seed may move into a review proposal only after all of the following are true:

1. canonical identity and provider are resolved;
2. owner/government/institution domain is classified as official;
3. source content is safely fetched and its final URL revalidated;
4. full tuition and stipend are both evidenced, or the candidate is explicitly downgraded;
5. Asia/Africa nationality scope is evidenced or marked unknown;
6. current cycle/status and scoped deadline are evidenced or marked unknown;
7. exact excerpts are attached to each supported fact;
8. duplicate, route, institution, and programme relationships are resolved;
9. the proposal remains review-only and unpublished.

## First extraction order

Start with a protected proof batch before bulk work:

1. Fulbright Foreign Student Program.
2. Chevening Scholarships.
3. Commonwealth Master's Scholarships.
4. Erasmus Mundus Joint Masters Scholarships.
5. DAAD EPOS.
6. Australia Awards Scholarships.
7. Japanese Government MEXT Scholarship.
8. Turkiye Scholarships.
9. Stipendium Hungaricum.
10. Chinese Government Scholarship.
11. Global Korea Scholarship.
12. KNB Scholarship.

This batch exercises country routes, umbrella schemes, multiple study levels, institution-linked
programmes, changing annual calls, and the target Asia/Africa audience before scaling toward 500.

## Live local acquisition audit - 2026-08-25

The first 20 priority candidates were processed locally in `candidate_only` mode. The run made zero
model calls, created no catalogue opportunity, and performed no publication action. It only tested
official-source classification, safe fetching, immutable artifact storage, and evidence-block
generation.

Initial run `e453ffc1-177d-4a2f-8f2e-dcdaa096b022` exposed two system defects rather than scholarship
facts:

- five Commonwealth pages returned standards-compliant `gzip` responses that the fetch boundary
  previously rejected;
- seven reviewed owner domains were not deterministically connected to their providers.

The fetcher now supports bounded gzip decompression with an expanded-size ceiling, and the local
review configuration explicitly allowlists the manually reviewed owner domains. Verification run
`7c57da35-af6b-431e-9c25-367f3a680f73`, plus the two alternative official-source checks below,
produced this result:

| Result | Scholarships | Evidence result |
|---|---|---|
| Acquired | Fulbright; five Commonwealth schemes; Erasmus Mundus; DAAD EPOS; MEXT; Türkiye Scholarships; Stipendium Hungaricum; Swiss Government Excellence; Gates Cambridge; Rhodes; Knight-Hennessy | 15 official artifacts with deterministic evidence blocks |
| Acquired through reviewed alternative | Chinese Government Scholarship; Global Korea Scholarship | Chinese Embassy notice: 1 artifact / 2 blocks. Study in Korea GKS page: 1 artifact / 25 blocks. |
| Manual review | Chevening; Australia Awards | Official owner confirmed, but `robots.txt` was unreachable. The crawler correctly failed closed. |
| Manual review | Clarendon Fund | Oxford returned HTTP 403. No browser shell or unsupported content was stored as evidence. |

Final acquisition coverage is therefore **17 of 20** priority scholarships with at least one fetched
official artifact. The remaining three are explicit external-access failures, not silently missing
facts. No claim from these artifacts has been promoted into the public catalogue.

Full structured fact extraction remains unavailable in this local environment because
`APP_CATALOGUE_AI_INGESTION_ENABLED=false` and the provider/model are unconfigured. Enabling it is
not inferred from this acquisition audit; extraction output must still pass the private gold-set
quality gate and human review before any record can be published.
