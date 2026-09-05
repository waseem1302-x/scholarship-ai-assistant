# Evidence-Accounted Catalogue Extraction Design

## Goal

Make catalogue extraction complete with respect to the acquired official evidence without adding
scholarship-specific rules. Every student-relevant semantic unit must either produce supported,
evidence-bound claims or receive an explicit disposition explaining why it did not. Completeness is
then computed from that ledger instead of trusting the extraction model to certify its own work.

This corrects the evidence-to-claims stage. The existing official-site crawler, browser rendering,
document/PDF extraction, OCR fallback, URL safety, persisted artifacts, Azure provider, review queue,
and publication controls remain in place.

## Root cause

Acquisition already retrieves the relevant official material. Information is lost afterward because:

1. HTML block boundaries are flattened before evidence is divided into fixed-size character chunks.
2. A routed evidence chunk is sent to the model with all extraction objectives, even when only a few
   objectives are relevant.
3. The claim schema drops valid student information that does not fit a predefined typed field.
4. Scalar-only resolution treats legitimate repeated values, such as aliases, as conflicts.
5. The same model that extracts claims reports whether extraction is complete.
6. Any conflict or rejected claim can suppress recovery for unrelated missing evidence.

Increasing page, context, or output limits cannot repair these logical losses. It only gives the same
contract more data to omit.

## Extraction contract

A candidate is evidence-accounted only when every persisted semantic evidence unit has one terminal
disposition:

- `mapped`: at least one accepted claim cites an exact span inside the unit;
- `duplicate`: its normalized content duplicates a named canonical unit;
- `irrelevant`: it contains no student-relevant scholarship fact for the routed scope;
- `unresolved`: it is relevant but could not be represented, validated, or extracted.

`mapped` and `duplicate` are validated deterministically. A model cannot mark a unit mapped without
an accepted claim reference, and a duplicate must identify a unit with the same normalized content
hash. Missing dispositions and `unresolved` units prevent a complete result. They remain visible in
the review payload and may drive one bounded gap pass.

The contract is corpus-relative: it covers public, authorized official evidence acquired by the
existing crawler. Login-only, blocked, disallowed, or unreachable sources continue to be reported by
the acquisition frontier and are not silently treated as absent facts.

## Semantic evidence units

The current persisted `CatalogueEvidenceBlock` remains the evidence-unit record. No parallel storage
system is introduced.

HTML normalization preserves line boundaries around headings, paragraphs, list items, table rows,
FAQ entries, rule clauses, and resource links. Document text keeps page/paragraph boundaries supplied
by the existing extractors. The block builder produces the smallest useful contiguous unit and only
splits a unit when it exceeds the existing safety limit. Exact artifact offsets remain authoritative.

The existing immutable artifact identity plus `block_key` is the stable evidence ID. Block-builder
and router versions are advanced so old cached blocks are never mistaken for newly segmented units.

## Focused extraction jobs

Routing remains generic and scholarship-independent. For each selected unit, the planner derives the
job objectives from that unit's selected routes. It no longer assigns every objective to every
artifact chunk. Adjacent units may share a provider call when their combined routed scope remains a
small bounded set of at most four objectives and fits existing request limits. This avoids both one
call per line and the previous all-objectives prompt.

Provider output includes a disposition for every unit in the request. Validation requires unique,
known unit IDs. `mapped` units must have accepted evidence-bound claims; unsupported or invalid claims
leave the unit `unresolved`, not complete. Units with no selected route are deterministically recorded
as `irrelevant` and are not sent to the provider.

## Claim representation and cardinality

Typed claims remain the preferred representation for fields used by catalogue filters and UI
sections. The existing `guidance` entity becomes the generic evidence-backed fallback for any valid
student-relevant fact that does not fit a typed field. It is permitted under every objective and must
carry `title`, `guidance_type`, and `text` with exact evidence. This prevents rules, FAQs, work rights,
appeal rules, technical interview requirements, certificates, and similar facts from being dropped
while preserving strict evidence validation.

A declarative field-cardinality registry replaces the implicit scalar default:

- `singleton`: exactly one unscoped value; differing same-tier values conflict;
- `set`: distinct normalized values merge without conflict;
- `ordered`: distinct values merge and retain explicit order;
- `scoped_singleton`: one value per entity scope/cycle/track.

Aliases and other naturally repeated fields are sets. Existing resolution precedence and exact
evidence rules are unchanged.

## Completeness and recovery

Provider-reported objective coverage remains diagnostic but is no longer sufficient for completeness.
The scoped completeness evaluator also consumes the evidence ledger. A selected unit that is missing
a disposition or is `unresolved` adds a stable completeness error. A complete model response cannot
override that error.

The gap pass targets unresolved units/objectives. Recoverable claim rejection or a conflict in one
field no longer prevents extraction of unrelated unresolved units. Such issues may still block final
materialization; they simply do not disable recovery work. Existing pass limits, budget checks, and
job terminal-state rules prevent loops.

## Compatibility and persistence

New disposition fields default to empty when reading historical provider payloads and historical
candidate resolution JSON. New extraction output must satisfy the stricter accounting validator.
Ledger data is persisted inside the existing structured claim-resolution/review payload, avoiding a
new database subsystem or migration. Prompt, bundle schema, planner, block-builder, router, and
resolver versions are advanced to invalidate incompatible caches.

## Verification

Red-green tests cover:

- preserved HTML semantic boundaries and exact stable unit offsets;
- route-focused jobs that never receive unrelated objectives;
- required and validated per-unit dispositions;
- singleton conflicts versus set/ordered merging;
- generic guidance retention for an otherwise unsupported official fact;
- ledger-driven completeness and recovery despite an unrelated rejection/conflict;
- an Open-Doors-shaped fixture containing subject names, university names, rules, FAQ facts, and
  resources, proving that every relevant unit is mapped or explicitly unresolved without a paid call.

After focused tests, run the complete backend suite, Ruff, frontend tests, lint, and production build.
A paid live run is explicitly outside this implementation step and requires the user's approval after
all local verification passes.

## Non-goals

- No Open Doors, CSC, Erasmus, DAAD, host, or field-name special cases.
- No external university-site expansion.
- No new crawler, browser, OCR engine, LLM provider, framework, or dependency.
- No cost/infrastructure redesign or UI redesign.
- No claim without exact persisted evidence and no automatic publication.
