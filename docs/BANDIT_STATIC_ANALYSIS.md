# Bandit static analysis

The Bandit workflow uses the repository-local composite action in `.github/actions/bandit/action.yml` instead of depending on a third-party wrapper at runtime. The local action is adapted from `shundor/python-bandit-scan` at commit `9955228c1cbdc5aeb5e511e0fa232154e2ed2b67`; its ISC license is retained beside the action.

The upstream action's useful behavior is small: install Bandit, produce a SARIF report, upload the report as an artifact, and send it to GitHub code scanning. Keeping that pattern locally makes the implementation easy to inspect while allowing the repository to enforce its existing supply-chain policy:

- `requirements-analysis.in` pins the intended Bandit release and SARIF support.
- `requirements-analysis.txt` pins and hashes Bandit and every transitive dependency, including `setuptools`.
- The artifact and SARIF upload actions use verified full commit SHAs.
- Bandit exits successfully long enough for both uploads to complete; the final action step then rejects missing or unsuccessful invocations, error-level scanner notifications, and SARIF reports containing findings.

The scan roots are deliberately fixed to `dashboard_action` and `scripts`. These contain the first-party production action and repository-maintenance Python code. Tests, generated output, distribution output, and vendored browser code such as Chart.js are outside those roots and are covered by their own purpose-built checks.

To update the scanner dependency, edit `requirements-analysis.in`, then regenerate and verify the lock:

```console
make lock-analysis
make validate-analysis-lock
```

The validation target recompiles the lock without upgrades, compares the result with the committed file, and performs a hash-only installation into a temporary directory. The hosted Bandit workflow additionally proves that the locked installation can generate and upload the repository's SARIF report.
