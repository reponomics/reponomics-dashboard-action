# Guide Tooling Lock

`requirements-guide-tooling.in` and `requirements-guide-tooling.txt` exist for the manual promotional dashboard guide workflow.

They are separate from `requirements-runtime.txt` because the guide dependencies are CI tooling for `.github/workflows/promotional-dashboard-guide.yml`, not runtime dependencies for the published GitHub Action. Keeping them separate prevents the action runtime lock from accumulating guide-only packages such as `Pillow` and `reportlab`.

Use these Make targets when the guide tooling changes:

```bash
make lock-guide-tooling
make validate-guide-tooling-lock
```

The workflow installs the guide tooling with `pip --require-hashes`, so update the lock file instead of adding ad hoc `pip install` commands to the workflow.
