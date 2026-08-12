# Document Lab evaluation and release gate

Run deterministic fixtures before enabling a remote provider. Required cases
include clean PDF/DOCX extraction, MIME spoofing, malformed PDF/DOCX, archive
and macro rejection, password protection, ZIP expansion limits, size/page/text
limits, scanner unavailable/failure, extraction timeout, prompt-like document
text, provider timeout/outage/quota/invalid response, ownership isolation,
retention/export/delete, concurrent retries, and log redaction.

The release threshold is zero cross-user access, zero document content/filename/
author/provider-payload log leaks, 100% safe rejection for hostile-file fixtures,
100% abstention or failure for unavailable/malformed providers, and 100% exact
excerpt matching for non-general feedback. UI release requires keyboard access,
visible text status labels, screen-reader announcements, mobile upload and
failure states, plus upload to scan to extract to consent to feedback to
export/delete browser journeys.

Provider quality is editorial, not predictive: reviewers assess whether feedback
is actionable, grounded, non-deceptive, and avoids guarantees. Any incident
blocks provider rollout until it has a minimal regression fixture.
