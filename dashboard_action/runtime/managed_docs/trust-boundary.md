# Repository Access And Trust Boundary

> [!WARNING]
> The Reponomics Dashboard template is currently in a pre-release public hardening phase. It is not intended for public use, and documentation in this managed-docs bundle should not be considered authoritative.

Reponomics stores its long-lived dashboard state in GitHub Actions artifacts and controls encrypted dashboard access through repository secrets and workflows. That means repository access is part of the dashboard security model, not just a source-code collaboration setting.

The strongest practical rule is:

> Only add a collaborator to a personal dashboard repository if you trust them not to exfiltrate data, hijack dashboard control, delete retained history, disrupt operations, or take over the dashboard.

This is stronger than "would I be comfortable with this person reading dashboard data?" A collaborator in a personal-account repository may be able to affect secrets, workflow execution, generated outputs, and retained artifact continuity. A hostile collaborator with the relevant workflow or secret access can use the repository control plane to expose dashboard data, replace dashboard keys, publish altered outputs, delete retained workflow runs or artifacts, or make current dashboard state inaccessible until the owner intervenes.

## Personal Repositories

Personal-account repositories have a much coarser permission model than organization repositories. For a private personal repository, a collaborator is effectively a write-capable collaborator; you do not get the same read, triage, write, maintain, and admin role ladder that organization repositories provide.

Branch rulesets and branch protection are still useful. They can protect `main`, require pull requests, and prevent direct changes to protected refs. They do not turn a collaborator into a read-only user, and they should not be treated as a Reponomics data-access boundary.

A collaborator's personal access token is not more powerful than the collaborator's account access. If a ruleset blocks the collaborator from pushing to a protected branch, their token should be blocked as well. The issue is that collaborator status still places the person inside important parts of the repository control plane.

In a personal dashboard repository, treat collaborators as trusted with:

- private repository read access
- Actions artifacts and logs visible to collaborators
- workflow dispatch ability where GitHub grants write-level users that ability
- repository secret management paths available to collaborators
- the ability to interfere with dashboard setup, rotation, reset, and publication flows
- the ability, if hostile, to exfiltrate data through workflow changes or generated artifacts, take over rotation/publication flows, delete retained workflow runs or artifacts, or deny access to current encrypted state

Repository secrets are especially important. Collaborators cannot read existing secret values directly, but if they can update repository secrets and run workflows, they can still disrupt encrypted state, replace dashboard keys, exfiltrate decrypted outputs through workflow changes, or cause data loss if old keys are not preserved. This is a dashboard control-plane takeover risk, not only an operational accident risk. A hostile collaborator could exfiltrate retained data, run the incident-response or rotation flow with a key they control, and delete prior workflow runs or artifacts; if the owner has never exported an independent copy, GitHub-hosted retained history may no longer be available as a recovery path. The rotation flow is intentionally careful because replacing `DASHBOARD_SECRET_DO_NOT_REPLACE` at the wrong time can make retained encrypted artifacts unrecoverable.

## Organization Repositories

Organization repositories provide a better model when the dashboard needs multiple humans with different responsibilities. Organizations can assign more specific repository roles, such as read, triage, write, maintain, and admin, and can use teams, branch protections, rulesets, environments, and organization policies to narrow operational access.

This does not remove every trust concern. Anyone who can manage Actions secrets, alter trusted workflows, approve protected environments, or administer the repository can still affect the dashboard control plane. But organization repositories make it possible to separate "can view repository contents" from "can administer workflows, secrets, and protected branches" in a way personal repositories generally do not.

Use an organization repository when you need real separation between:

- people who can view documentation or generated README output
- people who can edit configuration
- people who can run collection and publication workflows
- people who can manage secrets and rotate dashboard keys
- people who can administer repository settings

## Public Repositories

Public repository Actions artifacts should be treated as publicly accessible. Reponomics therefore requires `data-mode: encrypted` and rejects `data-mode: plaintext` for public repositories.

Public repositories also reject README dashboard generation because that would commit metrics into public git history. A hosted encrypted Pages dashboard can still disclose metadata such as the existence of the dashboard, update timing, and artifact size even when contents are encrypted.

## Practical Guidance

For a personal private dashboard repository, keep the collaborator list short. Add only people you trust with the dashboard's operational integrity, not merely people you would allow to read a report.

Do not treat GitHub policy enforcement, support, or retained workflow history as a backup plan. If retained dashboard history matters, periodically export an independent copy outside the repository control plane.

For less-trusted viewers, prefer sharing rendered outputs outside the repository boundary, or use an organization repository with explicit roles and policies.

For teams, prefer an organization repository before the dashboard becomes operationally important. Moving later is possible, but secrets, artifacts, workflow history, Pages settings, and access policies all become part of the migration.
