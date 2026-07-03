# Support Guidance

> [!NOTE] These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

## Beta Support Scope

Reponomics is open source software, not a commercial hosted service. After you copy the template, the dashboard repository, workflows, secrets, retained artifacts, and published outputs are under your control. Reponomics does not receive telemetry from your dashboard repository and does not handle your repository data.

During the external beta, Reponomics support is focused on the official generated workflows and action runtime:

- setup workflow behavior;
- collect and publish workflow behavior;
- Pages publication checks;
- retained artifact restore/upload behavior;
- dashboard unlock, rendering, and export behavior;
- key rotation and incident-reset workflow behavior;
- managed docs update behavior.

Because of that design, support works best when you share the smallest useful diagnostic material. Reponomics does not have access to your repository data, dashboard secrets, retained artifacts, or workflow outputs unless you choose to share them.

## Ways To Reach The Project

- Open an issue in `reponomics/reponomics-dashboard-action` for technical problems, bugs, documentation errors, and concrete change requests.
- Start a discussion in that repository for ideas, questions, and feedback from other users.
- Contact `support@reponomics.org` for serious support problems that are sensitive but do not require a private vulnerability report.

Security or vulnerability reports should use private vulnerability reporting rather than public issues or discussions.

## Reporting A Problem

Start with **Actions -> Doctor -> Run workflow** when a generated workflow fails or the dashboard does not look right.

Useful beta reports include:

- the dashboard repository owner/name, if it is public or you are comfortable sharing it;
- the failed workflow name and run URL;
- the Doctor workflow summary and report artifact;
- the relevant `config.yaml` fields, with secrets omitted;
- the action version shown in the workflow summary;
- a screenshot when the issue is visual.

Do not share `COLLECTION_TOKEN`, `DASHBOARD_SECRET_DO_NOT_REPLACE`, retained artifact contents, private repository data, or exploit details in public issues.

## Response Expectations

For invited beta participants, actionable bug reports should receive acknowledgement within 24 hours. The response may be a workaround, an active fix, a request for a Doctor report or workflow summary, or an explanation that the behavior is outside the current beta scope.

Feature requests and product-shaping feedback are welcome during beta, especially requests for repository signals that fit the existing GitHub permissions, data model, and dashboard architecture.

Reponomics cannot promise commercial support coverage, but beta users are treated as collaborators rather than anonymous traffic. Reports that improve the official generated workflows, docs, and dashboard behavior are especially valuable.

## First Places To Check

- [Dashboard Essentials](dashboard-essentials.md)
- [Troubleshooting](troubleshooting.md)
- [Dashboard repository guide](repository-guide.md)
- [FAQ](faq.md)
- [Privacy and artifacts](privacy-and-artifacts.md)
- [Security guidance](security.md)
