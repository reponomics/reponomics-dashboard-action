from pathlib import Path

import yaml


PAGES_DEPLOYMENT_IF = (
    "${{ (inputs.mode == 'publish' || inputs.mode == 'rotate-key') && " +
    "steps.runtime.outputs.publish-pages == 'true' }}"
)
PLAIN_DASHBOARD_ARTIFACT_IF = (
    "${{ inputs.mode == 'publish' && steps.runtime.outputs.publish-pages == " +
    "'false' && steps.runtime.outputs.artifact-mode == 'plain' }}"
)


def _action() -> dict:
    return yaml.safe_load(Path("action.yml").read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _action()["runs"]["steps"]


def _step_by_uses(prefix: str) -> dict:
    for step in _steps():
        if str(step.get("uses", "")).startswith(prefix):
            return step
    raise AssertionError(f"missing action step using {prefix}")


def _step_by_name(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing action step named {name}")


def test_configure_pages_verifies_existing_pages_setup_without_enablement() -> None:
    step = _step_by_uses("actions/configure-pages@")

    assert step["name"] == "Verify GitHub Pages configuration"
    assert step["if"] == PAGES_DEPLOYMENT_IF
    assert step["with"]["enablement"] == "false"
    assert "token" not in step.get("with", {})

    serialized = yaml.safe_dump(step)
    assert "traffic-token" not in serialized
    assert "TRAFFIC_TOKEN" not in serialized


def test_pages_deployment_steps_follow_publish_pages_contract() -> None:
    upload_pages = _step_by_uses("actions/upload-pages-artifact@")
    deploy_pages = _step_by_uses("actions/deploy-pages@")
    plain_dashboard = _step_by_name("Upload plain dashboard artifact")

    assert upload_pages["if"] == PAGES_DEPLOYMENT_IF
    assert deploy_pages["if"] == PAGES_DEPLOYMENT_IF
    assert plain_dashboard["if"] == PLAIN_DASHBOARD_ARTIFACT_IF
    assert plain_dashboard["with"]["name"] == "traffic-dashboard-plain"


def test_publish_pages_replaces_dashboard_mode_output() -> None:
    outputs = _action()["outputs"]
    description = outputs["publish-pages"]["description"]

    assert "dashboard-mode" not in outputs
    assert "publishes" in description
    assert "GitHub Pages" in description
