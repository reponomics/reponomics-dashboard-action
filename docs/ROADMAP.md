---
name: ROADMAP.md
description: Document the repository's roadmap for future work and improvements.
created: 2026-05-20
modified: 2026-05-26
---

# Roadmap

Lightweight tracker for short-term and long-term goals, including pre-v1 readiness items.

## v1 Requirements

### CI and Security

- [ ] Add a proper complexity gate with `antipasta` and/or Actions Marketplace action after reducing large runtime modules and high-complexity functions. Initial targets include `load_data.py`, `collect.py`, `release_notice.py`, and the dashboard/rendering modules. Progress should be made on this before v1.

## Not v1-Blockers


### CI And Security

- [ ] If the OpenSSF Scorecard `Fuzzing` check becomes a release goal, add ClusterFuzzLite with Atheris harnesses only after identifying a stable parser boundary that is expected to remain in the product. Do not add placeholder fuzzers only for the badge.
- [ ] Continue to improve complexity reduction.
