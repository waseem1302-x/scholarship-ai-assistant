# Phase 4 milestone 2: authoritative structured eligibility

Structured rules are the only source for consequential eligibility decisions.
Free-text requirements remain visible as source evidence, but result in `unknown`
until a curator creates a typed rule. They never silently produce an ineligible
decision.

## Supported rules

The evaluator supports nationality, residence, target degree, field, CGPA,
percentage, IELTS, TOEFL, Duolingo, GRE, English/GRE test status, work experience,
study mode, target intake year, current education level, and effective application
window. Categorical rules use `equals`, `in`, and `not_in`; numeric rules also use
`gte` and `lte`. Missing, waiver-dependent, ambiguous, or unsupported evidence is
always `unknown`.

Each newly created rule is automatically linked to the newly supplied official
source and an immutable excerpt captured from it. The admin data-quality endpoint
flags public records whose stored eligibility text has no corresponding structured
rule, as well as legacy rules with missing or invalid official evidence.
