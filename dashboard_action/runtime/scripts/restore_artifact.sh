#!/usr/bin/env bash
# Restore the dashboard-data artifact from a previous workflow run.
#
# Uses the GitHub CLI (pre-installed on Actions runners) to find and download
# either the requested run's artifact or the most recent unexpired artifact
# named "$ARTIFACT_NAME".
#
# Exit codes:
#   0 — artifact restored successfully, OR no prior artifact exists (first run)
#   1 — unexpected error during download/extraction
#
# Environment:
#   GITHUB_REPOSITORY — owner/repo (set automatically by Actions)
#   ARTIFACT_NAME     — artifact name to restore (default: dashboard-data)
#   ARTIFACT_RUN_ID   — optional workflow run ID to restore from
#   GH_TOKEN          — GitHub token for API access (set automatically by Actions)

set -euo pipefail

ARTIFACT_NAME="${ARTIFACT_NAME:-dashboard-data}"
DATA_DIR="${DATA_DIR:-data}"
ARTIFACT_RUN_ID="${ARTIFACT_RUN_ID:-}"

if [ -n "$ARTIFACT_RUN_ID" ]; then
  echo "Looking for artifact: ${ARTIFACT_NAME} from workflow run ${ARTIFACT_RUN_ID}..."
else
  echo "Looking for previous artifact: ${ARTIFACT_NAME}..."
fi

# Find the requested artifact. Without ARTIFACT_RUN_ID, the API returns
# artifacts sorted by most recent first, preserving the historical fallback.
if [ -n "$ARTIFACT_RUN_ID" ]; then
  ARTIFACT_ID=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${ARTIFACT_RUN_ID}/artifacts?per_page=100" \
    --jq ".artifacts[] | select(.name == \"${ARTIFACT_NAME}\") | .id" 2>/dev/null | head -n 1 || true)
else
  ARTIFACT_ID=$(gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts?name=${ARTIFACT_NAME}&per_page=1" \
    --jq '.artifacts[0].id // empty' 2>/dev/null || true)
fi

if [ -z "$ARTIFACT_ID" ]; then
  if [ -n "$ARTIFACT_RUN_ID" ]; then
    echo "No ${ARTIFACT_NAME} artifact found for workflow run ${ARTIFACT_RUN_ID}."
    exit 1
  else
    echo "No previous artifact found — this appears to be a first run."
    exit 0
  fi
fi

echo "Found artifact ID: ${ARTIFACT_ID}"

# Download the artifact zip
TMPZIP=$(mktemp /tmp/artifact-XXXXXX.zip)
trap 'rm -f "$TMPZIP"' EXIT

echo "Downloading artifact..."
if ! gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/${ARTIFACT_ID}/zip" > "$TMPZIP" 2>/dev/null; then
  if [ -n "$ARTIFACT_RUN_ID" ]; then
    echo "Error: failed to download artifact ${ARTIFACT_ID} from workflow run ${ARTIFACT_RUN_ID}."
    exit 1
  fi
  echo "Warning: failed to download artifact ${ARTIFACT_ID} — treating as first run."
  exit 0
fi

# Verify we got a non-empty file
if [ ! -s "$TMPZIP" ]; then
  if [ -n "$ARTIFACT_RUN_ID" ]; then
    echo "Error: downloaded artifact ${ARTIFACT_ID} from workflow run ${ARTIFACT_RUN_ID} is empty."
    exit 1
  fi
  echo "Warning: downloaded artifact is empty — treating as first run."
  exit 0
fi

# Extract into the data directory
mkdir -p "$DATA_DIR"
echo "Extracting artifact to ${DATA_DIR}/..."
if ! unzip -o "$TMPZIP" -d "$DATA_DIR" > /dev/null 2>&1; then
  echo "Error: failed to extract artifact zip."
  exit 1
fi

echo "Artifact restored successfully."
# List restored files for the workflow log
ls -la "$DATA_DIR"/
