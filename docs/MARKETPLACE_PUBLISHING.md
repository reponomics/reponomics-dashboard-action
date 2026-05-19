# GitHub Marketplace Packaging

GitHub Actions does not provide a native Python action runtime. Marketplace actions are packaged as Docker container, JavaScript, or composite actions.

This repository currently uses a composite action wrapper around the Python runtime. That keeps the action usable on standard GitHub-hosted runners, allows the wrapper to call other actions such as `actions/upload-artifact`, and keeps the implementation close to the existing Python source tree.

A Docker action is the stronger packaging boundary when the action must ship a fixed operating system image, Python version, and dependency set. It is also Linux-only, slower to start, and cannot run nested `uses:` steps internally, so the artifact upload behavior would need to move into Python or into a caller workflow/wrapper.

For this project, keep the root Marketplace action as a composite wrapper unless dependency reproducibility becomes more important than cross-platform runner behavior and nested action steps. If that changes, prefer a two-layer design: a Dockerized Python runtime plus a thin composite wrapper that preserves the current public inputs and outputs.

Marketplace publication checklist:

- Keep a single root `action.yml` metadata file.
- Keep the repository public before publishing.
- Keep `action.yml` metadata complete: `name`, `description`, `author`, `inputs`, `outputs`, `runs`, and `branding`.
- Release immutable SemVer tags and maintain major-line tags such as `v1`.
- Publish from a GitHub release with the Marketplace option enabled.
- Review the current GitHub Marketplace repository constraints before publication; GitHub's current docs say Marketplace action repositories should not contain workflow files, which conflicts with in-repository CI/CD.
