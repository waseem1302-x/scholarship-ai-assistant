# ADR 0013 implementation corrections

- Status: Normative implementation correction to ADR 0013
- Date: 2026-08-19
- Applies to: PR6 claim persistence and corroboration

Implementation of the pure PR6 claim/resolution core exposed one unsafe uniqueness proposal in ADR 0013 before any database migration was created.

## 1. Claim uniqueness is source-extraction scoped

ADR 0013 originally proposed both:

```text
UNIQUE(source_extraction_id, ordinal)
UNIQUE(bundle_id, claim_fingerprint)
```

The second constraint is rejected.

Two different official source snapshots can independently assert the same normalized claim. Those rows must both survive so the resolver can record real corroboration and preserve both evidence chains.

The persistence contract is instead:

```text
UNIQUE(source_extraction_id, ordinal)
UNIQUE(source_extraction_id, claim_fingerprint)
```

or an equivalent source-extraction-scoped idempotency rule.

`claim_fingerprint` identifies the assertion content within one extraction context; it is **not** a global or bundle-wide evidence identity.

Example:

```text
Provider source -> deadline 20 May
Mission source  -> deadline 20 May
```

must produce two claims and may resolve to `CORROBORATED`.

Repeated duplicate output from the same immutable source extraction should be deduplicated/idempotent and does not count as independent corroboration.

## 2. First runtime slice is deliberately narrower than the full ADR claim taxonomy

The first pure-domain implementation proves only the highest-risk claim families:

```text
DEGREE_LEVEL
APPLICATION_OPENING
APPLICATION_DEADLINE
FUNDING_COMPONENT
ELIGIBILITY_RULE
```

The remaining ADR 0013 claim families are still architectural targets and will be added only with their own typed schemas/resolver tests. The implementation must not introduce a generic arbitrary JSON claim as a shortcut.

## 3. Corroboration means independent accepted source contexts agree

Two equal claims from the same `source_key` do not establish independent corroboration.

Two equal claims from different accepted source contexts can produce `CORROBORATED` after evidence, authority, scope, and applicability checks pass.

This does not create majority voting: source count cannot select between conflicting values.

## 4. Temporal equality preserves precision

Date-only facts remain dates.

Exact datetimes are compared by their offset-aware instant so equivalent timestamps expressed in different UTC offsets do not create a false conflict.

A matching exact datetime may refine a date-only claim only when its source-local calendar date agrees with the date claim. This is recorded as partial/refining support rather than pretending the date-only source stated the exact time.

## 5. Source assertion states are structurally constrained

The v1 pure claim contract requires:

- `ASSERTED_VALUE` -> typed value + at least one `VALUE` evidence proposal;
- `ASSERTED_ABSENT` / `ASSERTED_NOT_APPLICABLE` -> no typed value + explicit `NEGATION` evidence;
- source silence -> no claim, never an asserted absence/unknown.

These invariants must be carried into the later SQLAlchemy/Pydantic persistence layer.
