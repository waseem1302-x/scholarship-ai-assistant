# Slice 06 — Structured Opportunity Ingestion

## Goal

Help administrators add opportunity records in batches without weakening the
project's source-first trust model.

The importer supports structured JSON rows and CSV text. CSV rows are parsed
into the same row contract so validation, duplicate detection, forced review,
and row-level reporting stay consistent.

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

CSV request shape:

```json
{
  "source_format": "csv",
  "dry_run": true,
  "csv_content": "name,provider_name,country,degree_level,source_url,source_title,source_relevant_excerpt\nExample Scholarship,Example Provider,Malaysia,masters,https://example.edu/scholarship,Official scholarship page,Official source excerpt with eligibility and deadline details."
}
```

CSV column notes:

- regular opportunity fields use their API names, such as `name`,
  `provider_name`, `country`, `degree_level`, and `funding_type`
- source fields can use `source_url`, `source_title`,
  `source_relevant_excerpt`, `source_type`, `source_content_hash`, and
  `source_verification_status`
- `required_documents` and `eligibility_warnings` use semicolon-separated
  values

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

Build JSON batch import first, then add CSV parsing as a layer that maps
spreadsheet columns into the same validated row format.

## Reason

The hard part is not reading CSV bytes. The hard part is trusted validation,
duplicate detection, forced review, and row-level reporting. The CSV parser now
feeds that same JSON row format instead of bypassing it.

## Alternative considered

Add multipart CSV upload immediately.

## Tradeoff

Multipart CSV upload would feel more complete in the UI, but it would add file
handling before the core parser and safety behavior need it. The API accepts
CSV text now; file upload UI can wrap this later.

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
- CSV rows are parsed into the same safe import contract.
- Formula-like CSV cells are neutralized and reported as row warnings.

## Known limitations

- No multipart `.csv` file upload UI yet.
- No column-mapping UI yet.
- No persistent import-job history table yet.
- No assisted webpage/PDF extraction yet.
- Deployment scheduling for source monitoring depends on the eventual hosting
  environment.

## Recommended next slice

Stage 7 should add a small verified seed dataset and/or improve the public
search filters. The seed dataset will make demos more realistic, while stronger
filters will make the backend more useful before RAG.
