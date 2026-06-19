"""Canonical generated-template workflow surface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowName(StrEnum):
    """Display names for generated dashboard workflows."""

    COLLECT_AND_PUBLISH = "Collect and Publish"
    DOCTOR = "Doctor"
    INCIDENT_RESET = "INCIDENT - Reset"
    KEEP_ALIVE = "Keep Alive"
    ROTATE_KEY = "Rotate Key"
    SETUP = "Setup"
    UPDATE_DOCS = "Update Docs"


@dataclass(frozen=True)
class TemplateWorkflow:
    source: str
    target: str
    name: str


TEMPLATE_WORKFLOWS = (
    TemplateWorkflow(
        "template/.github/workflows/collect-and-publish.yml",
        ".github/workflows/collect-and-publish.yml",
        WorkflowName.COLLECT_AND_PUBLISH,
    ),
    TemplateWorkflow(
        "template/.github/workflows/doctor.yml",
        ".github/workflows/doctor.yml",
        WorkflowName.DOCTOR,
    ),
    TemplateWorkflow(
        "template/.github/workflows/incident-reset.yml",
        ".github/workflows/incident-reset.yml",
        WorkflowName.INCIDENT_RESET,
    ),
    TemplateWorkflow(
        "template/.github/workflows/keepalive.yml",
        ".github/workflows/keepalive.yml",
        WorkflowName.KEEP_ALIVE,
    ),
    TemplateWorkflow(
        "template/.github/workflows/rotate-key.yml",
        ".github/workflows/rotate-key.yml",
        WorkflowName.ROTATE_KEY,
    ),
    TemplateWorkflow(
        "template/.github/workflows/setup.yml",
        ".github/workflows/setup.yml",
        WorkflowName.SETUP,
    ),
    TemplateWorkflow(
        "template/.github/workflows/update-docs.yml",
        ".github/workflows/update-docs.yml",
        WorkflowName.UPDATE_DOCS,
    ),
)

TEMPLATE_WORKFLOW_OUTPUTS = {
    workflow.source: workflow.target for workflow in TEMPLATE_WORKFLOWS
}
TEMPLATE_WORKFLOW_NAMES = {
    workflow.source: workflow.name for workflow in TEMPLATE_WORKFLOWS
}
