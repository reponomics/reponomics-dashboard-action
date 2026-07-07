# Repository Access And Trust Boundary

Reponomics stores long-lived dashboard state in GitHub Actions artifacts and controls encrypted dashboard access through repository secrets and workflows. Repository access is therefore part of the dashboard security model.

## Practical Rule

Only add a collaborator to a personal dashboard repository if you trust them with the dashboard control plane: data confidentiality, workflow integrity, key rotation, retained history, publication settings, and operational continuity.

That is stronger than trusting someone to read a report.

## Personal Repositories

Personal private repositories have a coarse collaborator model. Branch rulesets and branch protection can protect refs, but they do not turn collaborators into read-only dashboard viewers.

Treat collaborators as potentially able to affect:

- private repository contents;
- Actions artifacts and logs;
- workflow dispatch where GitHub grants it;
- repository secrets and variables where GitHub grants it;
- workflow files, generated outputs, key rotation, incident reset, and publication flows;
- retained workflow runs and artifacts when workflow permissions allow deletion.

Collaborators cannot read existing secret values directly through the normal GitHub UI. But a collaborator who can change trusted workflows, update secrets, or run privileged workflows can still disrupt encrypted state, exfiltrate decrypted outputs, replace keys, or delete retained history.

## Organization Repositories

Use an organization repository when more than one person needs access and roles matter. Organizations support read, triage, write, maintain, and admin roles, plus teams, branch protections, rulesets, environments, and organization policies.

This does not remove every trust concern. Anyone who can manage Actions secrets, alter trusted workflows, approve protected environments, or administer the repository can still affect the dashboard control plane.

## Public Repositories

Public repository Actions artifacts should be treated as public. Reponomics requires `data_mode: encrypted` and rejects `data_mode: plaintext` for public repositories.

Public repositories also reject README dashboard generation because it would commit metrics into public git history. Hosted encrypted Pages dashboards can still disclose metadata such as existence, update timing, and payload size.

## Safer Patterns

- Keep personal dashboard collaborator lists short.
- Use organization repositories for role separation before the dashboard becomes operationally important.
- Share rendered outputs outside the repository boundary for less-trusted viewers.
- Periodically export an independent copy if retained dashboard history matters.
- Do not treat GitHub policy enforcement, support, or retained workflow history as a recovery plan.

## Continue

- [Privacy and security](privacy-and-security.md)
- [Publication](publication.md)
