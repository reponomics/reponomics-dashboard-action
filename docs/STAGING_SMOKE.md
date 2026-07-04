# Staging Smoke Placeholder

> [!IMPORTANT]
> This is not an executable runbook and not a release gate. It is a placeholder for the next staging design after the aborted staging repository implementation was removed.

Status: clean reset. The previous staging repository implementation was removed because it grew into a brittle private-repo fleet with local helper scripts, skipped assertions, and a separate template publication workflow. Do not revive that implementation by copying old helper code back into this repository.

The replacement should be deliberately small: one public copied dashboard repository, `data_mode: encrypted`, `publish_pages_dashboard: true`, and `publish_readme_dashboard: false`.

## Purpose

The staging smoke pass should prove the path an external maintainer is most likely to trust before beta onboarding:

- a real copied repository can run the generated workflows;
- a low-scope `COLLECTION_TOKEN` can collect real but non-sensitive public GitHub data;
- encrypted retained data can be restored across workflow runs;
- GitHub Pages can serve the encrypted dashboard shell;
- the dashboard unlocks in a browser and renders the expected views.

Synthetic data remains appropriate for demos, fixtures, and UI snapshots. Staging should use boring public repositories and real GitHub API responses so it exercises authentication, rate limits, artifacts, generated workflows, Pages, and browser behavior together.

## First Scenario

The first replacement scenario should be:

| Setting | Value |
| --- | --- |
| Repository visibility | Public |
| Data mode | `encrypted` |
| Pages dashboard | Enabled |
| README dashboard | Disabled |
| Data source | Real, non-sensitive public GitHub API data |
| Collection credential | Dedicated low-scope `COLLECTION_TOKEN` |

This document is only the design placeholder for the reset. A future implementation should add the smallest possible Make target, script, and test surface needed to run that one scenario and record evidence.
