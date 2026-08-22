# MEXT live validation - 2026-08-23

## Boundary

This validation used public official sources, the existing read-only Azure OpenAI deployment, and
a local SQLite staging database. It did not change Azure, publish an opportunity, or write a graph.

## Official sources checked

- Study in Japan MEXT overview:
  `https://www.studyinjapan.go.jp/en/planning/scholarships/mext-scholarships/`
- Study in Japan 2027 Embassy Recommendation research page:
  `https://www.studyinjapan.go.jp/en/smap-stopj-applications-research.html`
- Study in Japan 2027 Research Students guidelines PDF:
  `https://www.studyinjapan.go.jp/en/_mt/2026/04/01-2027_Research_Guidelines_E.pdf`
- Embassy of Japan in Pakistan 2027 Research Scholarship page:
  `https://www.pk.emb-japan.go.jp/itpr_en/MEXT_Research_Scholarship.html`

The Pakistan embassy page was readable interactively but denied the bounded automated fetch. The
candidate therefore failed closed before model use. The other three sources were acquired through
the safe fetch boundary, including the 416,454-byte PDF.

## Results

The final fresh three-source run produced three successful, current-prompt model calls with an
estimated cost of 0.015656. All three normalized artifact hashes matched, and all 24 accepted claim
spans matched their exact artifact offsets. The resolver rejected unsupported or invalid claims,
retained a same-tier application-method conflict, and reported missing degree-level and University
Recommendation evidence. No opportunity, snapshot, or field-evidence row was created.

After adding deterministic support for entity-qualified snake-case field aliases, a compatible
reuse control accepted 26 claims and verified all 26 evidence spans exactly. It still blocked the
record on the same-tier application-method conflict and missing degree-level evidence. All three
attempts were recorded as reused, model calls and added cost were zero, and canonical writes stayed
at zero.

A control run using only the two 2027 sources canonicalized their source-local cycle aliases to
`intake_2027`. It remained non-materializable because the current evidence bundle did not establish
the University Recommendation route and the two same-tier application-method claims differed. This
is the intended review outcome; the workflow did not relabel an older university guideline or
silently choose one wording.

The deployed model had a 10,000-token-per-minute and 10-request-per-minute limit. Azure returned
`Retry-After: 30` during validation. The provider now honors that hint within a configured cap and
surfaces exhausted throttling as `ai_rate_limited`.

Extraction reuse now requires the stored prompt hash in addition to URL, content hash, schema,
provider, and model. This prevents a successful result from an older prompt contract being treated
as compatible after prompt hardening.

## Conclusion

The workflow is operational for bounded multi-source acquisition, immutable source evidence,
per-source extraction, deterministic resolution, reuse, cycle canonicalization, and fail-closed
review gating. A complete current-cycle canonical MEXT graph still requires an official,
cycle-compatible University Recommendation source. Until that source exists and passes the same
checks, the correct production result is a review blocker rather than a fabricated complete record.
