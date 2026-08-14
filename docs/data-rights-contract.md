# Modular data-rights contract

Every module that stores student-owned data must satisfy the account-level export and erasure
contract before its API is enabled:

1. declare its owned database tables and external storage objects;
2. add a versioned owner-only export section without fixed row truncation;
3. implement retry-safe explicit external deletion before database cascade;
4. make database ownership reference `users.id` with a reviewed cascade or explicit deletion;
5. add aggregate export and post-closure residue tests on PostgreSQL;
6. keep export/erasure routes available when the feature kill switch is off.

The current aggregate sections are account, profile, Applications (including legacy saved records),
matching history, Assistant, Community, Document Lab, and beta legal acceptances. A new module is
not complete until it is added to this inventory and its conformance test. Audit and operational
records are excluded from the portable user export; audit actor identifiers are nulled on closure
while immutable historical event evidence remains.
