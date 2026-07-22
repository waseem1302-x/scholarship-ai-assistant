# Slice 04: Rule-based matching

## Goal

Rank verified opportunities against a student's profile using explicit, inspectable rules before adding AI ranking or recommendations.

## Acceptance criteria

- Matching requires an authenticated user and an existing student profile.
- Only public, active, officially verified opportunities are considered.
- Each result includes a score, label, satisfied requirements, missing requirements, uncertain requirements, and next steps.
- Missing profile data produces uncertainty, not false eligibility or ineligibility.
- The score is documented as a fit/ranking signal, not a probability of admission or selection.
- Tests cover ranking, explanation content, unverified-opportunity exclusion, missing profile handling, and uncertainty behavior.

## Rule categories

- Degree level fit
- Nationality fit
- Field fit
- Academic requirement fit
- Deadline status
- English-language requirement fit
- Destination-country preference
- Funding fit

## Known limitations

- Eligibility text is still partly free-form, so some rules use simple keyword and pattern matching.
- Academic parsing currently supports basic CGPA expressions only.
- This baseline is intentionally deterministic; later slices can add structured eligibility rules and evaluation metrics.
