---
name: ROADMAP.md
description: Document the repository's roadmap for future work and improvements.
created: 2026-05-20
modified: 2026-05-26
---

# Roadmap

Lightweight tracker for short-term and long-term goals, including pre-v1 readiness items.

## V1 Requirements

### CI and Security

- [ ] Add a proper complexity gate with `antipasta` and/or Actions Marketplace action after reducing large runtime modules and high-complexity functions. Initial targets include `load_data.py`, `collect.py`, `release_notice.py`, and the dashboard/rendering modules. Progress should be made on this before v1.

## Not V1 Blockers

### CI And Security

- [ ] If the OpenSSF Scorecard `Fuzzing` check becomes a release goal, add ClusterFuzzLite with Atheris harnesses only after identifying a stable parser boundary that is expected to remain in the product. Do not add placeholder fuzzers only for the badge.
- [ ] Continue to improve complexity reduction.

### Enhanced Metrics

- [ ] Competitive analysis - obviously, the user can only collect traffic data from repos to which they have admin permission. But there may be enough publicly available data about repos that compete with the user's projects that running collection on selected third-party repos is worthwhile for providing "competitive analysis".

### Logistics

- [ ] Enable usage with a GitHub app - offering a "Reponomics App" seems to go against the current product angle, but users should be able to run collection using a GitHub app installation token that they create for themselves. This is probably the optimal path, actually, but it would require changes to the `collect` workflow steps in order to use an installation token instead of a PAT.
