# Release Runbook

This is the short command-oriented runbook for action and template releases. It assumes `gh` is authenticated and the working tree is clean.

## Start From Current Main

```sh
git fetch origin --tags --prune
git switch main
git pull --ff-only origin main
git status --short --branch
```

Do not force-push `reponomics-dashboard-action/main`.

## Local Template Release Gates

Run these before creating a template release:

```sh
make verify-workflow-classification
make verify-template
make validate-template-action-ref
make template-smoke
make template-consumer-e2e
make template-compat-e2e
make publish-template-dry-run
make package-template-release
```

For broader release confidence, also run:

```sh
make lint
make type-check
make test
make validate-workflows
```

## Confirm Template Version

```sh
template_version="$(sed -n 's/^template_version: //p' template-contract.yml | tr -d '\"')"
template_tag="reponomics-dashboard-v${template_version}"
echo "$template_tag"
```

The tag must be shaped like `reponomics-dashboard-vX.Y.Z`. Do not use `dashboard-release-v*` and do not use bare `v*` tags for template releases.

## Create A Template Release

Write release notes to a temporary file:

```sh
cat > /tmp/reponomics-template-release-notes.md <<'EOF'
## Reponomics Dashboard Template vX.Y.Z

Short release summary.

### Changed

- Summarize generated workflow, setup, config, docs, or repository-surface changes.
- Note any user-visible behavior changes for newly copied repositories.

### Compatibility

This template requires `reponomics/reponomics-dashboard-action@v0` resolving to the action version declared by `template-contract.yml` `min_action_version` or newer.
EOF
```

Create the release:

```sh
gh release create "$template_tag" \
  --repo reponomics/reponomics-dashboard-action \
  --target main \
  --title "Reponomics Dashboard Template v${template_version}" \
  --notes-file /tmp/reponomics-template-release-notes.md
```

## Watch Template Publication

Find the run:

```sh
gh run list \
  --repo reponomics/reponomics-dashboard-action \
  --workflow publish-template.yml \
  --limit 5
```

Watch it:

```sh
gh run watch RUN_ID \
  --repo reponomics/reponomics-dashboard-action \
  --exit-status
```

If the run waits on `template-publication`, approve it in the GitHub UI, then continue watching.

## Post-Template Publication Checks

Confirm the source release exists:

```sh
gh release view "$template_tag" \
  --repo reponomics/reponomics-dashboard-action \
  --web
```

Confirm generated template publication:

```sh
gh repo view reponomics/reponomics-dashboard --web
```

Inspect the latest generated commit and provenance:

```sh
tmpdir="$(mktemp -d)"
git clone --depth 1 git@github.com:reponomics/reponomics-dashboard.git "$tmpdir/reponomics-dashboard"
cat "$tmpdir/reponomics-dashboard/.reponomics/template-provenance.json"
```

Compare the `source.commit`, `template.version`, `action.min_version`, and `payload.digest` values against the release workflow output.

## Action Release Notes

Action releases are managed by Release Please. Use the Release Please PR unless there is an explicit maintainer decision to bypass it.

After an action release, verify:

```sh
gh release view vX.Y.Z --repo reponomics/reponomics-dashboard-action --web
git ls-remote origin refs/tags/vX.Y.Z refs/tags/vX refs/tags/vX.Y
```

If a template release depends on the new action behavior, make sure `template-contract.yml` `min_action_version` is updated and `make validate-template-action-ref` passes before creating the template release.

## Coupled Action And Template Release

When the action and template intentionally move together, prefer one reviewed release commit rather than separate follow-up PRs. The Release Please PR should contain the action version bump, changelog, and any template contract or docs changes needed for the generated template release.

After that PR is merged, Release Please creates the exact action tag. Create the template release tag from the same source commit when the template should publish from that exact reviewed state:

```sh
action_version="$(sed -n 's/^version = \"\\(.*\\)\".*/\\1/p' pyproject.toml)"
action_tag="v${action_version}"
template_version="$(sed -n 's/^template_version: //p' template-contract.yml | tr -d '\"')"
template_tag="reponomics-dashboard-v${template_version}"
release_sha="$(git rev-list -n 1 "$action_tag")"

gh release create "$template_tag" \
  --repo reponomics/reponomics-dashboard-action \
  --target "$release_sha" \
  --title "Reponomics Dashboard Template v${template_version}" \
  --notes-file /tmp/reponomics-template-release-notes.md
```

Using the same source commit is optional for action-only or template-only releases, but it is the preferred path when the compatibility gate, action release, and template publication all describe the same product state.
