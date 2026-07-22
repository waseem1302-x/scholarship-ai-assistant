# Slice 06 — Structured Opportunity Ingestion

## Goal

Help administrators add opportunity records in batches without weakening the
project's source-first trust model.

The importer supports structured JSON rows now. CSV support can be added later
by parsing CSV rows into the same row contract.

## Implemented API

```text
POST /api/v1/admin/opportunities/import
```

Request shape:

```json
{
  "source_format": "json",
  "dry_run": false,
  "rows": [
    {
      "name": "Example Scholarship",
      "provider_name": "Example Provider",
      "country": "Malaysia",
      "degree_level": "masters",
      "funding_type": "unknown",
      "source": {
        "url": "https://example.edu/scholarship",
        "source_type": "official",
        "title": "Official scholarship page",
        "relevant_excerpt": "Official source excerpt with eligibility and deadline details."
      }
    }
  ]
}
```

Response shape:

- total rows
- imported count
- duplicate count
- failed count
- row-level status
- row-level errors
- row-level data-quality warnings

## Safety behavior

Imported records are never made public automatically.

Even if an import row says:

- `status = active`
- source `verification_status = officially_verified`

the system forces:

- opportunity `status = draft`
- source `verification_status = needs_review`

An admin must use the existing verification endpoint before the opportunity can
appear in public search, matching, or saved-opportunity workflows.

## Data-quality warnings

The importer reports warnings for issues such as:

- missing application deadline
- unknown funding type
- missing required documents
- missing English-language requirement
- missing minimum academic requirement
- low data confidence
- imported status/source verification being forced back to review-safe values

Warnings do not block import. They tell the curator what needs attention.

## Duplicate detection

The importer detects:

- existing database duplicates
- duplicate rows inside the same import batch

The duplicate key is:

```text
provider_name + opportunity name + country + intake_year
```

## Dry-run support

`dry_run = true` validates rows and reports warnings/duplicates without writing
new records to the database.

## Decision

Build JSON batch import first, not direct CSV file upload.

## Reason

The hard part is not reading CSV bytes. The hard part is trusted validation,
duplicate detection, forced review, and row-level reporting. A future CSV parser
can map spreadsheet columns into the same JSON row format.

## Alternative considered

Add multipart CSV upload immediately.

## Tradeoff

Direct CSV upload would feel more complete in the UI, but it would add file
handling, column mapping, encoding issues, and spreadsheet edge cases before the
core ingestion rules are proven.

## What this teaches

- Batch API design
- Row-level validation
- Partial success reporting
- Defensive data-provenance design
- Import review workflows
- Why ingestion is more than “just upload a CSV”

## Portfolio evidence

This slice proves that the platform is moving toward real operational use by
curators. It can accept structured opportunity data safely while preserving the
core promise: public records must be verified against official sources.

## Tests added

- Imported opportunities are forced to draft/needs-review.
- Imported opportunities stay hidden from public search until verification.
- Dry-run validates without creating records.
- Existing duplicates are skipped without failing the whole batch.
- Invalid rows return row-level validation errors.
- Duplicate rows inside the same batch are detected.

## Known limitations

- No direct `.csv` file upload yet.
- No column-mapping UI yet.
- No persistent import-job history table yet.
- No assisted webpage/PDF extraction yet.
- No scheduled source monitoring yet.

## Recommended next slice

Stage 7 should add a small verified seed dataset and/or improve the public
search filters. The seed dataset will make demos more realistic, while stronger
filters will make the backend more useful before RAG.
