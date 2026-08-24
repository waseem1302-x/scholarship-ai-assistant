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

Current live verification on 24 August 2026 found `main` protected with
administrator enforcement, conversation resolution, linear history, and the
required `test`, `security-scan`, `browser-e2e`, and `bicep` checks. The
`azure-staging` environment has a branch policy; `azure-beta` has both a branch
policy and required reviewers. The remaining release-control gap is mandatory
pull-request review on `main`: it is not currently required. Enable at least
one independent approving review before production release. The repository
must not be made public temporarily to bypass any protection requirement.
