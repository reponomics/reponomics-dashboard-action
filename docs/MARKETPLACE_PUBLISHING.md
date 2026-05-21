# GitHub Marketplace Packaging

GitHub Actions does not provide a native Python action runtime. Marketplace actions are packaged as Docker container, JavaScript, or composite actions.

This repository currently uses a composite action wrapper around the Python runtime. That keeps the action usable on standard GitHub-hosted runners, allows the wrapper to call other actions such as `actions/upload-artifact`, and keeps the implementation close to the existing Python source tree.

A Docker action is the stronger packaging boundary when the action must ship a fixed operating system image, Python version, and dependency set. It is also Linux-only, slower to start, and cannot run nested `uses:` steps internally, so the artifact upload behavior would need to move into Python or into a caller workflow/wrapper.

For this project, keep the root Marketplace action as a composite wrapper unless dependency reproducibility becomes more important than cross-platform runner behavior and nested action steps. If that changes, prefer a two-layer design: a Dockerized Python runtime plus a thin composite wrapper that preserves the current public inputs and outputs.

Marketplace publication checklist:

- Keep a single root `action.yml` metadata file.
- Keep the repository public before publishing.
- Keep `action.yml` metadata complete: `name`, `description`, `author`, `inputs`, `outputs`, `runs`, and `branding`.
- Release immutable exact SemVer tags such as `v1.2.3`; maintain plain floating compatibility tags such as `v1` and `v1.2`.
- Publish from a GitHub release with the Marketplace option enabled.
- Review the current GitHub Marketplace repository constraints before publication; GitHub's [current docs](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace#prerequisites) say Marketplace action repositories should not contain workflow files, which conflicts with in-repository CI/CD. This appears stale or overbroad: many prominent Marketplace actions, including GitHub-maintained `actions/*` repositories such as [`actions/setup-node`](https://github.com/actions/setup-node), keep maintenance workflows in the action repository. GitHub's own action maintenance documentation is also [inconsistent](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/release-and-maintain-actions) with a literal reading of that Marketplace prerequisite. Until GitHub clarifies the requirement, keep workflows that are necessary to test, audit, release, and maintain this action, and avoid unrelated workflow templates or generated artifacts in this repository.
