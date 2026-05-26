# Roadmap

Lightweight tracker for work we are not trying to finish in the current hardening pass.

## CI And Security

- [ ] Add a proper complexity gate with `antipasta` and `complexipy` after reducing large runtime modules and high-complexity functions. Initial targets include `load_data.py`, `collect.py`, `release_notice.py`, and the dashboard/rendering modules.
- [ ] If the OpenSSF Scorecard `Fuzzing` check becomes a release goal, add ClusterFuzzLite with Atheris harnesses only after identifying a stable parser boundary that is expected to remain in the product. Do not add placeholder fuzzers only for the badge.
