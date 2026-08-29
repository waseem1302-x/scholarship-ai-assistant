# Catalogue worker configuration

The catalogue worker has a separate environment because the API, frontend, and ordinary
background workers do not need Azure catalogue credentials.

## Files

| Path | Purpose | Commit? |
| --- | --- | --- |
| `config/catalogue/worker.env.example` | Safe, disabled worker baseline | Yes |
| `.local/env/catalogue-worker.env` | Live local overrides and Entra credential | Never |
| `.catalogue-local/STOP` | Operator kill switch | Never |
| `.catalogue-local/model-capability.json` | Expiring endpoint/deployment capability receipt | Never |
| `.catalogue-local/capability-evidence.json` | Sanitized evidence from the approved probe | Never |
| `.local/azure-cli/` | Optional repo-local Azure CLI state | Never |
| `.local/backups/catalogue/` | Temporary sensitive recovery copies | Never |
| `.local/tools/catalogue/` | Local diagnostics and one-off pilot helpers | Never |

Compose loads the committed baseline first and the ignored live file second. The live file
therefore contains only reviewed overrides and credentials, while safe defaults remain visible
in version control. The host-only `.local` directory is never mounted. The `.catalogue-local`
directory contains only the kill switch and capability evidence and is mounted read-only into the
catalogue worker at `/run/catalogue`; the API service never receives the Azure credential.

## Initialize local configuration

1. Create `.local/env/` and `.catalogue-local/`.
2. Copy `config/catalogue/worker.env.example` to
   `.local/env/catalogue-worker.env`.
3. Keep `.catalogue-local/STOP` present while editing or recreating the worker.
4. Never print, commit, or place real values in the example file.

## Future Azure tenant/subscription migration

Replace the following values together in `.local/env/catalogue-worker.env`:

- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`;
- `APP_CATALOGUE_AI_ENDPOINT` and `APP_CATALOGUE_AI_MODEL`;
- reviewed input/output pricing and explicit run ceilings.

An endpoint or deployment change invalidates the old capability receipt. Keep `STOP` armed,
remove or archive the old receipt, recreate only the catalogue worker, verify the Entra token
without calling the model, and run the bounded capability probe only after explicit approval.
Revoke the old tenant credential only after the new identity and deployment have passed those
checks. Historical proof documents should retain the old resource names as evidence.
