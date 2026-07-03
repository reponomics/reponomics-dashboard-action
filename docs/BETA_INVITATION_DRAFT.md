# Reponomics Maintainer Beta Invitation Draft

Status: working draft

Purpose: language for inviting a small group of maintainers to try Reponomics before the stable `v1` line. This is not legal terms or a public support policy. It is a plain-language invitation and beta compact.

## Semi-Public Invitation

I am opening a small maintainer beta for Reponomics Dashboard.

Reponomics is a GitHub-native dashboard for maintainers who want to keep and understand the repository data GitHub already makes available: traffic, clones, referrers, stars, forks, issues, releases, and related project signals. It runs in your own GitHub repository, stores retained data in your own workflow artifacts, and can publish an encrypted dashboard through GitHub Pages without sending your data to a hosted third-party service.

For this beta, I am looking for maintainers who are comfortable with GitHub Actions and who would be willing to try Reponomics on a real project or small portfolio of projects. The beta is meant for people who can tolerate a little roughness in exchange for direct access to the maintainer and a real chance to shape the product before the stable release line.

The current beta line is `v0`. If the beta proves out, the stable public release line will become `v1`.

## Who This Is For

This beta is probably a good fit if:

- You maintain one or more GitHub repositories and care about traffic, growth, contributor activity, or project health signals.
- You are comfortable editing a GitHub Actions workflow and adding repository or organization secrets.
- You can start with one GitHub owner or organization and a modest set of repositories.
- You are willing to run Doctor and share selected diagnostic output when something breaks.
- You want a private, GitHub-native analytics workflow rather than another hosted SaaS account.

It is probably not a good fit yet if:

- You need a polished managed service with formal support coverage.
- You need Reponomics to span many unrelated owners or organizations immediately.
- You are not comfortable managing GitHub Actions secrets.
- You need a stable compatibility promise before `v1`.

## What Beta Participants Get

During the beta, participants get direct maintainer attention.

For actionable bug reports, I will acknowledge the issue within 24 hours and either identify a workaround, begin a fix, or explain why the issue is outside the current beta scope. Some fixes may take longer than a day, especially if they involve GitHub API behavior, workflow permissions, or larger design changes, but beta reports will not disappear into a queue.

Each beta participant may also nominate one repository signal they would like Reponomics to collect or surface. I will make a good-faith effort to implement that request during the beta when it can be supported by the existing GitHub permissions, data model, and dashboard architecture. Examples might include a specific issue-comment signal, release cadence view, traffic rollup, repository comparison, or maintainer workload indicator.

The intent is simple: if you are willing to try Reponomics while it is still rough, you should get a meaningful voice in what it becomes.

## Guardrails

The beta is privacy-preserving by design, so support has some boundaries.

I cannot inspect your private repository data, dashboard secrets, retained artifacts, or workflow outputs unless you choose to share specific diagnostic material. Most support will be based on workflow logs, Doctor reports, configuration excerpts, screenshots, and reproducible symptoms.

Requested data signals should fit the existing product shape. I will avoid requests that require broader token permissions, unrelated private data, a bespoke fork that cannot be maintained, or a large re-architecture. If GitHub does not expose a signal reliably through the API, I may not be able to collect it.

Priority will go to fixes and signals that are useful to more than one maintainer, but beta participants will have a much stronger voice than they would after a general public release.

## What I Ask In Return

Beta participants should be willing to:

- try the generated template on a real but bounded repository set;
- report where setup is confusing or broken;
- run Doctor when requested;
- share only the diagnostic material they are comfortable sharing;
- tell me which dashboard views are useful, noisy, or missing;
- be candid about whether the tool would become part of their maintainer workflow.

## Direct Message Version

I am opening a small maintainer beta for Reponomics Dashboard and wanted to ask whether you would be interested.

It is a GitHub-native analytics dashboard that runs in your own repository, keeps retained data in your own workflow artifacts, and can publish an encrypted dashboard through GitHub Pages. The beta is still on the `v0` line, so I am mostly inviting maintainers who are comfortable with GitHub Actions and willing to tolerate some rough edges.

The offer is direct maintainer support and real product influence. If you hit an actionable bug, I will acknowledge it within 24 hours and either find a workaround, start a fix, or explain the current scope. I am also offering each beta participant one serious repository-signal request that I will try to implement if it fits the existing permissions, data model, and dashboard architecture.

The privacy boundary is important: I do not need access to your private data unless you choose to share specific diagnostic output. Support is based on logs, Doctor reports, config excerpts, screenshots, and reproducible behavior.

If this sounds useful, I can send setup instructions and help you decide whether your repository set is a good beta fit.

## Short Website Notice

Reponomics Dashboard is preparing for a small maintainer beta.

Beta participants get direct maintainer support, early influence over the dashboard, and the opportunity to request one repository signal for implementation consideration before the stable `v1` line.

The beta is intended for maintainers comfortable with GitHub Actions who want private, GitHub-native repository analytics without sending their data to a hosted third-party service.

If you maintain open source or public-facing GitHub projects and want to try the beta, get in touch.

## Beta Compact

Reponomics will:

- treat external beta users as collaborators, not anonymous traffic;
- acknowledge actionable bug reports within 24 hours;
- provide a workaround, active fix, or scope explanation for actionable reports;
- make a good-faith effort to implement one feasible repository-signal request per beta participant;
- keep the beta on the `v0` line until the project is ready for a stable `v1` release;
- avoid asking for private dashboard data unless the participant chooses to share diagnostic material.

Beta participants will:

- start with a bounded repository set;
- use the official generated workflow path unless they are intentionally testing a modification;
- report setup confusion, runtime failures, and misleading dashboard output;
- run Doctor and share selected diagnostics when useful;
- understand that the beta is not a hosted service or formal support contract.
