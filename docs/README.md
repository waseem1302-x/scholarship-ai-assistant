# Documentation index

Start with these authoritative documents:

- `current-product-state.md` — what is implemented, disabled, or environment-dependent now.
- `blueprint.md` — product and system direction.
- `catalogue-ingestion-pipeline.md` — catalogue ingestion behavior and safety boundary.
- `scholarship-information-contract.md` — required scholarship information model.
- `scholarship-extraction-stability-gate.md` — acceptance criteria for extraction proofs.
- `repository-release-controls.md` — repository and release safeguards.
- `../config/catalogue/README.md` — local catalogue/Azure configuration ownership.

Supporting material is grouped by naming convention rather than moved, preserving existing links:

- `decisions/` — architecture decision records.
- `slices/` — incremental implementation handoffs.
- `phase9-*` — beta hardening, operations, privacy, and release evidence.
- `terra-5.6-phase-*`, `*-audit*`, `*-log*`, and dated `*-proof-*` files — historical execution
  evidence. They describe the repository at a point in time and do not override
  `current-product-state.md` or executable configuration.

This index intentionally avoids a broad documentation move while the worktree contains an
uncommitted catalogue implementation. File relocation can happen later as a separate,
link-checked documentation-only change.
