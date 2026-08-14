# Repository release controls

These controls are external GitHub settings and cannot be proved by workflow YAML.

## Required before protected release execution

- keep the repository private;
- enable a `main` ruleset/branch protection when the account plan supports private-repository
  rulesets: pull requests required, force pushes/deletion blocked, conversation resolution required,
  and exact required checks `CI / test`, `CI / browser-e2e`, `CI / security-scan`;
- create `azure-staging` and `azure-beta` GitHub Environments, each with environment-scoped OIDC
  identifiers and deployment branch restrictions; require independent human approval for beta;
- configure the two synthetic staging students described in the Azure runbook;
- enable automatic deletion of merged branches and remove obsolete stacked branches/PRs only after
  confirming no unique commits remain.

Current live verification on 14 August 2026 found `main` unprotected and zero GitHub Environments.
GitHub reported that private-repository protection requires an account-plan upgrade. This is an
explicit **external release blocker**, not something CI or code may mark as passed. The repository
must not be made public temporarily to bypass the protection requirement.
