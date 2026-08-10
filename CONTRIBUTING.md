# Contributing

Reponomics Dashboard Action is in a public pre-release hardening period. The repository is visible so its security posture, workflows, dependency handling, and release process can be reviewed in the open, but it is not yet being promoted for general use.

Security reports are welcome. For security issues, follow `SECURITY.md` instead of opening a public issue with exploit details.

## Current Contribution Policy <>

Issues and pull requests that are most likely to be useful during pre-release:

- security vulnerability reports submitted through the private reporting path;
- small corrections to inaccurate documentation;
- reproducible CI, packaging, or release-process failures;
- narrowly scoped fixes for behavior that is already documented.

Please do not submit speculative integrations, large rewrites, new product features, formatting-only changes, or dependency churn unless a maintainer has asked for them.

## Windows

The current development workflow assumes a POSIX shell and Python virtual environments whose executables are stored under `venv/bin`. Native PowerShell, Command Prompt, and MSYS2 development environments are not currently validated.

On Windows, use WSL 2 with Ubuntu 24.04. From an elevated PowerShell session, install WSL and Ubuntu:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart Windows if prompted, then launch Ubuntu and complete its initial setup. See Microsoft's [WSL installation guide](https://learn.microsoft.com/windows/wsl/install) for additional guidance.

Within Ubuntu, install the required system tools:

```bash
sudo apt update
sudo apt install --yes git make python3 python3-venv python-is-python3
```

Install Node.js 24 using [nvm](https://github.com/nvm-sh/nvm#installing-and-updating). After installing nvm, run:

```bash
nvm install 24
nvm alias default 24
```

Verify the development toolchain:

```bash
python3 --version
node --version
make --version
```

Python must be version 3.11, 3.12, or 3.13, and Node.js must be version 24.

Clone the repository into the WSL filesystem—for example, somewhere under `~/src`—and run all Make commands from the Ubuntu shell. Do not run the documented Make workflow from PowerShell, Command Prompt, or an MSYS2 shell.

## Development Setup

Use the project Makefile for local development. The repository expects a local `venv` virtual environment.

```bash
make install
make pre-commit-install
make ci
```

Individual checks are named after what they do:

```bash
make lint
make type-check
make validate
make test
make coverage
make complexity
```

Complexity tooling is optional because it is not formally incorporated into CI/CD and is not supported in every environment.

Focused fixture checks are also available:

```bash
make fixture-collect
make fixture-publish
make fixture-rotate-key
```

Do not commit generated local state such as `venv`, coverage reports, caches, rendered dashboard output, or local dashboard data artifacts.

## Markdown Formatting

Do not hard-wrap Markdown prose. Keep paragraphs as single logical lines so future edits produce smaller diffs. The `LICENSE` file is the exception and may keep conventional license-text wrapping.
