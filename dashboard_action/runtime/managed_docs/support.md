# Support

## Ways To Reach The Project

- Open an issue in [`reponomics/reponomics-dashboard-action`](https://github.com/reponomics/reponomics-dashboard-action/issues) for technical problems, bugs, documentation errors, and concrete change requests.
- Start a [discussion](https://github.com/reponomics/reponomics-dashboard-action/discussions) for ideas, questions, and feedback from other users.
- Contact `support@reponomics.org` for serious support problems that are sensitive but do not require a private vulnerability report.

Security or vulnerability reports should use private vulnerability reporting rather than public issues or discussions. See [Vulnerability Reporting](vulnerability-reporting.md).

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

Feature requests and product-shaping feedback are welcome during the pre-wide-release beta, especially requests for repository signals that fit the existing GitHub permissions, data model, and dashboard architecture.

Reponomics cannot promise commercial support coverage, but beta users are treated as collaborators rather than anonymous traffic. Reports that improve the official generated workflows, docs, and dashboard behavior are especially valuable.

## First Places To Check

- [Setup](setup.md)
- [Troubleshooting](troubleshooting.md)
- [Workflows](workflows.md)
- [FAQ](faq.md)
- [Data and artifacts](data-and-artifacts.md)
- [Privacy and security](privacy-and-security.md)
