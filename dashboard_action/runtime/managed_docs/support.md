# Support Guidance

> [!NOTE] These docs describe the official Reponomics generated workflows for the `v0` external beta. Repository owners can modify their copies; modified workflows may behave differently from what these docs describe.

## Ways To Reach The Project

- Open an issue in `reponomics/reponomics-dashboard-action` for technical problems, bugs, documentation errors, and concrete change requests.
- Start a discussion in that repository for ideas, questions, and feedback from other users.
- Contact `support@reponomics.org` for serious support problems that are sensitive but do not require a private vulnerability report.

Security or vulnerability reports should use private vulnerability reporting rather than public issues or discussions.

## Reporting A Problem

Start with **Actions -> Doctor -> Run workflow** when a generated workflow fails or the dashboard does not look right.

Useful reports include:

- the dashboard repository owner/name, if it is public or you are comfortable sharing it;
- the failed workflow name and run URL;
- the Doctor workflow summary and report artifact;
- the relevant `config.yaml` fields, with secrets omitted;
- the action version shown in the workflow summary;
- a screenshot when the issue is visual.

Do not share `COLLECTION_TOKEN`, `DASHBOARD_SECRET_DO_NOT_REPLACE`, retained artifact contents, private repository data, or exploit details in public issues.

## Response Expectations

Feature requests and product-shaping feedback are welcome during beta, especially requests for repository signals that fit the existing GitHub permissions, data model, and dashboard architecture.

Reponomics cannot promise commercial support coverage, but beta users are treated as collaborators rather than anonymous traffic. Reports that improve the official generated workflows, docs, and dashboard behavior are especially valuable.

## First Places To Check

- [Dashboard Essentials](dashboard-essentials.md)
- [Troubleshooting](troubleshooting.md)
- [Dashboard repository guide](repository-guide.md)
- [FAQ](faq.md)
- [Privacy and artifacts](privacy-and-artifacts.md)
- [Security guidance](security.md)
