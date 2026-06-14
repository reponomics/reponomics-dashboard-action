"""Print the maintainer command order for a live staging smoke pass."""

from __future__ import annotations

import argparse


def live_order() -> str:
    return """# Reponomics Staging Smoke Live Run Order

Default mode is recurring. Staging repositories and consumer secrets are persistent; bootstrap is only for first initialization or intentional secret reconfiguration.

## One-time bootstrap

1. Inspect planned GitHub setup without writing:
   make staging-smoke-provision-plan

2. Create missing private staging repositories, if the dry-run output is correct:
   make staging-smoke-provision

3. Configure source-repository staging publication credentials:
   gh variable set TEMPLATE_STAGING_PUBLISH_APP_CLIENT_ID --repo reponomics/reponomics-dashboard-action --body '<app-client-id>'
   gh secret set TEMPLATE_STAGING_PUBLISH_APP_PRIVATE_KEY --repo reponomics/reponomics-dashboard-action

4. Check readiness. On the first bootstrap pass, treat failures as the bootstrap checklist:
   make staging-smoke-preflight

5. Review the bootstrap plan and generate the report template:
   make staging-smoke-plan STAGING_SMOKE_PHASE=bootstrap

6. Run local gates, and optionally dispatch staging template publication after they pass. On first bootstrap, use STAGING_SMOKE_ALLOW_BOOTSTRAP=1 only if the preflight failures are expected empty-repo bootstrap items:
   make staging-smoke-run STAGING_SMOKE_PHASE=bootstrap
   make staging-smoke-run STAGING_SMOKE_PHASE=bootstrap STAGING_SMOKE_ALLOW_BOOTSTRAP=1
   make staging-smoke-run STAGING_SMOKE_PHASE=bootstrap DISPATCH_TEMPLATE_STAGING=1
   make staging-smoke-run STAGING_SMOKE_PHASE=bootstrap STAGING_SMOKE_ALLOW_BOOTSTRAP=1 DISPATCH_TEMPLATE_STAGING=1

7. Execute the printed consumer-repository steps deliberately:
   reset encrypted fresh, configure secrets, run setup, collect/publish, rotate key, republish, seed plain history if empty, collect/publish plain history, and run doctor.

## Recurring smoke

8. Confirm readiness. A recurring run should pass preflight because repos and required secrets already exist:
   make staging-smoke-preflight

9. Review the recurring plan. This is the default phase:
   make staging-smoke-plan
   make staging-smoke-plan STAGING_SMOKE_PHASE=recurring

10. Run local gates, and optionally dispatch staging template publication after they pass:
   make staging-smoke-run
   make staging-smoke-run DISPATCH_TEMPLATE_STAGING=1

11. Execute the printed recurring consumer steps deliberately:
   reset encrypted fresh codebase, run encrypted setup, collect/publish, rotate key, republish, collect/publish plain history, and run doctor.

12. Record browser coverage:
   make staging-smoke-browser-checklist

13. Run read-only repository evidence checks:
   make staging-smoke-evidence

14. Fill in .tmp/staging-smoke/report.md and mark any skipped browser or evidence checks incomplete.
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args(argv)


def main() -> None:
    parse_args()
    print(live_order())


if __name__ == "__main__":
    main()
