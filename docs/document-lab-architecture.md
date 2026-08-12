# Document Lab architecture and threat model

Document Lab is a separate private domain. `application_documents` remains coordination metadata; it never stores uploaded bytes, extracted text, feedback, or provider payloads.

## Data flow

1. An authenticated student uploads raw PDF/DOCX bytes with a declared MIME type and filename header.
2. The API enforces rate, size, extension, declared-MIME, magic-byte, PDF encryption/page, and DOCX archive/macro checks. It stores only an encrypted copy under an opaque user-scoped key, then creates a quarantined version and scan job.
3. The worker must pass a malware-scanner adapter before extraction. Scanner failure/unavailability fails closed.
4. A short-lived restricted subprocess extracts only text with a timeout and character bound. It executes no macros and rejects image-only/OCR inputs. Production must provide OS/container no-network isolation for this subprocess.
5. A student explicitly consents to each analysis using the displayed notice version. Only then can the worker send extracted text to a reviewed provider adapter.
6. Output is schema validated. Feedback needs a short exact document excerpt or a `general suggestion` label. Unsupported decision, guarantee, plagiarism, or authorship language is rejected.

## Privacy and operations

- Original names, bytes, extracted text, summaries, excerpts, and feedback are encrypted at rest. Storage keys are opaque and are never API responses.
- Database job/audit state contains IDs, timestamps, counters, policy versions, and safe codes only. Never log document content, filenames, author metadata, or provider request/response bodies.
- Owners are checked on every asset, version, download, analysis, export, delete, and application-link access. Application linking is explicit and confirmed.
- Retention removes storage objects and cascaded records. Export is owner-only. Deleting an asset removes its versions, extracted text, analyses, feedback, jobs, and links.
- `local-encrypted` storage is development-only. Production requires a reviewed encrypted object storage provider, managed encryption key, malware scanner, shared rate limiter, and parser isolation.

## Incident response

Disable `APP_DOCUMENT_LAB_ENABLED`, stop document workers, preserve only safe job identifiers, revoke affected provider credentials, and investigate storage access/audit records without opening document content. Re-enable only after remediation, retention verification, and a regression test.
