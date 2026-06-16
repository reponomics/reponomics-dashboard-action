.DEFAULT_GOAL := help

.PHONY: help install pre-commit-install pre-commit-run ci staging-smoke-instructions staging-smoke-live-order staging-smoke-provision-plan staging-smoke-provision staging-smoke-plan staging-smoke-preflight staging-smoke-reset-fresh-plan staging-smoke-reset-fresh staging-smoke-seed-plain-history-plan staging-smoke-seed-plain-history staging-smoke-browser-checklist staging-smoke-evidence staging-smoke-run
.PHONY: test coverage complexity security security-audit audit-runtime-lock lock-runtime validate-runtime-lock update-vendored-assets
.PHONY: lint type-check
.PHONY: validate validate-action validate-workflows validate-vendored-assets
.PHONY: build-template verify-template build-and-verify-generated verify-workflow-classification validate-template-action-ref template-smoke template-consumer-e2e template-action-boundary-e2e template-compat-e2e template-public-action-e2e package-template-release publish-template-dry-run publish-template publish-template-staging-dry-run publish-template-staging build-demo verify-demo publish-demo-dry-run publish-demo
.PHONY: fixtures fixture-collect fixture-publish fixture-rotate-key preview-collection-quality-dashboard dashboard-scenario-snapshots update-dashboard-scenario-snapshots clean

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
ANTIPASTA := $(VENV)/bin/antipasta
PIP_AUDIT := $(VENV)/bin/pip-audit
PIP_COMPILE := $(VENV)/bin/pip-compile
PRE_COMMIT := $(VENV)/bin/pre-commit
INSTALL_STAMP := $(VENV)/.install.stamp
COVERAGE_FAIL_UNDER ?= 70
RUNTIME_LOCK := requirements-runtime.txt
PIP_COMPILE_RUNTIME_FLAGS := --generate-hashes --strip-extras --resolver=backtracking --no-header --quiet
PIP_COMPILE_RUNTIME_UPGRADE_FLAGS := $(PIP_COMPILE_RUNTIME_FLAGS) --upgrade
COLLECTION_QUALITY_PREVIEW_FIXTURE := tests/fixtures/collection_quality_preview
COLLECTION_QUALITY_PREVIEW_OUTPUT := .tmp/collection_quality_preview
TEMPLATE_REMOTE ?= https://github.com/reponomics/reponomics-dashboard.git
TEMPLATE_EXPECTED_REPO ?= reponomics/reponomics-dashboard
TEMPLATE_PUBLISH_MESSAGE ?= chore: publish generated template
TEMPLATE_STAGING_REMOTE ?= https://github.com/reponomics/reponomics-dashboard-staging.git
TEMPLATE_STAGING_EXPECTED_REPO ?= reponomics/reponomics-dashboard-staging
TEMPLATE_STAGING_PUBLISH_MESSAGE ?= chore: publish generated template staging
TEMPLATE_RELEASE_ARTIFACTS_DIR ?= dist/template-release
DEMO_REMOTE ?= https://github.com/reponomics/reponomics-dashboard-demo.git
DEMO_EXPECTED_REPO ?= reponomics/reponomics-dashboard-demo
DEMO_PUBLISH_MESSAGE ?= chore: publish generated demo
ACTION_REPO ?= .
ACTION_PYTHON ?= $(PYTHON)
TEMPLATE_COMPAT_EXTRA_ARGS ?=
STAGING_SMOKE_SOURCE_REPO ?= reponomics/reponomics-dashboard-action
STAGING_SMOKE_SOURCE_REF ?= main
STAGING_SMOKE_TEMPLATE_REPO ?= reponomics/reponomics-dashboard-staging
STAGING_SMOKE_ENCRYPTED_REPO ?= reponomics/reponomics-dashboard-staging-private-encrypted-fresh
STAGING_SMOKE_PLAIN_REPO ?= reponomics/reponomics-dashboard-staging-private-plaintext-with-history
STAGING_SMOKE_COLLECTION_MODE ?= pat
STAGING_SMOKE_PHASE ?= recurring
STAGING_SMOKE_GH_DELAY_SECONDS ?= 1
STAGING_SMOKE_ALLOW_BOOTSTRAP ?= 0
STAGING_SMOKE_REPORT ?= .tmp/staging-smoke/report.md
STAGING_SMOKE_BROWSER_CHECKLIST ?= .tmp/staging-smoke/browser-checklist.md
STAGING_SMOKE_ENCRYPTED_PAGES_URL ?= <encrypted-pages-url>
STAGING_SMOKE_PLAIN_LOCAL_URL ?= http://localhost:8765

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

staging-smoke-instructions: ## Show the manual staging smoke runbook for local Codex runs
	@cat docs/STAGING_SMOKE.md

staging-smoke-live-order: install ## Show the concise live staging smoke command order
	$(PYTHON) scripts/staging_smoke/live_order.py

staging-smoke-provision-plan: install ## Print one-time staging repo provisioning commands without creating repos
	STAGING_SMOKE_GH_DELAY_SECONDS=$(STAGING_SMOKE_GH_DELAY_SECONDS) $(PYTHON) scripts/staging_smoke/provision.py \
		--source-repo $(STAGING_SMOKE_SOURCE_REPO) \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO)

staging-smoke-provision: install ## Create missing private staging repos; secrets remain manual
	STAGING_SMOKE_GH_DELAY_SECONDS=$(STAGING_SMOKE_GH_DELAY_SECONDS) $(PYTHON) scripts/staging_smoke/provision.py \
		--source-repo $(STAGING_SMOKE_SOURCE_REPO) \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO) \
		--execute

staging-smoke-plan: install ## Print the guarded staging smoke execution plan
	$(PYTHON) scripts/staging_smoke/run.py \
		--source-repo $(STAGING_SMOKE_SOURCE_REPO) \
		--source-ref $(STAGING_SMOKE_SOURCE_REF) \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO) \
		--collection-mode $(STAGING_SMOKE_COLLECTION_MODE) \
		--phase $(STAGING_SMOKE_PHASE) \
		--command-delay-seconds $(STAGING_SMOKE_GH_DELAY_SECONDS) \
		--write-report-template $(STAGING_SMOKE_REPORT)

staging-smoke-preflight: install ## Check local/GitHub prerequisites for staging smoke repos
	STAGING_SMOKE_GH_DELAY_SECONDS=$(STAGING_SMOKE_GH_DELAY_SECONDS) $(PYTHON) scripts/staging_smoke/preflight.py \
		--source-repo $(STAGING_SMOKE_SOURCE_REPO) \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO) \
		--collection-mode $(STAGING_SMOKE_COLLECTION_MODE)

staging-smoke-reset-fresh-plan: install ## Build fresh encrypted staging tree without force-pushing
	$(PYTHON) scripts/staging_smoke/reset_fresh.py \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO)

staging-smoke-reset-fresh: install ## Force-reset encrypted fresh repo; requires CONFIRM_TARGET exact repo
	$(PYTHON) scripts/staging_smoke/reset_fresh.py \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO) \
		--execute \
		--confirm-target "$(CONFIRM_TARGET)"

staging-smoke-seed-plain-history-plan: install ## Build seed tree for empty plain history repo without pushing
	$(PYTHON) scripts/staging_smoke/seed_plain_history.py \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO)

staging-smoke-seed-plain-history: install ## Seed empty plain history repo without force-push; requires CONFIRM_TARGET exact repo
	$(PYTHON) scripts/staging_smoke/seed_plain_history.py \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO) \
		--execute \
		--confirm-target "$(CONFIRM_TARGET)"

staging-smoke-evidence: install ## Read-only evidence checks for completed staging smoke repos
	STAGING_SMOKE_GH_DELAY_SECONDS=$(STAGING_SMOKE_GH_DELAY_SECONDS) $(PYTHON) scripts/staging_smoke/evidence.py \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO)

staging-smoke-browser-checklist: install ## Write the staging browser smoke checklist
	$(PYTHON) scripts/staging_smoke/browser_checklist.py \
		--encrypted-pages-url "$(STAGING_SMOKE_ENCRYPTED_PAGES_URL)" \
		--plain-local-url "$(STAGING_SMOKE_PLAIN_LOCAL_URL)" \
		--output $(STAGING_SMOKE_BROWSER_CHECKLIST)

staging-smoke-run: install ## Run local staging smoke gates; set DISPATCH_TEMPLATE_STAGING=1 to dispatch staging publication
	$(PYTHON) scripts/staging_smoke/run.py \
		--source-repo $(STAGING_SMOKE_SOURCE_REPO) \
		--source-ref $(STAGING_SMOKE_SOURCE_REF) \
		--template-staging-repo $(STAGING_SMOKE_TEMPLATE_REPO) \
		--encrypted-fresh-repo $(STAGING_SMOKE_ENCRYPTED_REPO) \
		--plain-history-repo $(STAGING_SMOKE_PLAIN_REPO) \
		--collection-mode $(STAGING_SMOKE_COLLECTION_MODE) \
		--phase $(STAGING_SMOKE_PHASE) \
		--execute \
		--command-delay-seconds $(STAGING_SMOKE_GH_DELAY_SECONDS) \
		--write-report-template $(STAGING_SMOKE_REPORT) \
		$(if $(filter 1 true yes,$(STAGING_SMOKE_ALLOW_BOOTSTRAP)),--allow-bootstrap-preflight-failures,) \
		$(if $(filter 1 true yes,$(DISPATCH_TEMPLATE_STAGING)),--dispatch-template-staging,)

install: $(INSTALL_STAMP) ## Create venv and install dependencies

$(INSTALL_STAMP): pyproject.toml
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PIP) install -e '.[dev]'
	touch $(INSTALL_STAMP)

pre-commit-install: install ## Install local pre-commit hooks
	GIT_CONFIG_GLOBAL=/dev/null $(PRE_COMMIT) install --install-hooks --hook-type pre-commit --hook-type pre-push

pre-commit-run: install ## Run pre-commit hooks against all files
	$(PRE_COMMIT) run --all-files

test: install ## Run tests
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests -v

coverage: install ## Run tests with coverage report
	$(PYTHON) -m pytest tests -v --cov=dashboard_action --cov-report=term-missing --cov-report=xml --cov-fail-under=$(COVERAGE_FAIL_UNDER)

complexity: install ## Run complexity metrics
	$(ANTIPASTA) metrics --directory dashboard_action

security-audit: install ## Audit Python dependencies for known vulnerabilities
	$(PIP_AUDIT) --local --skip-editable --progress-spinner off

audit-runtime-lock: install ## Audit hash-pinned runtime dependency lock
	$(PIP_AUDIT) --requirement $(RUNTIME_LOCK) --no-deps --progress-spinner off

security: security-audit audit-runtime-lock validate-runtime-lock validate-vendored-assets ## Run open-source security checks

lock-runtime: install ## Regenerate hash-pinned runtime dependency lock
	$(PIP_COMPILE) $(PIP_COMPILE_RUNTIME_UPGRADE_FLAGS) --output-file $(RUNTIME_LOCK) pyproject.toml

validate-runtime-lock: install ## Verify runtime lock matches constraints without upgrades and is hash-installable
	tmp_lock=$$(mktemp); \
	cp "$(RUNTIME_LOCK)" "$$tmp_lock"; \
	$(PIP_COMPILE) $(PIP_COMPILE_RUNTIME_FLAGS) --output-file "$$tmp_lock" pyproject.toml; \
	if ! cmp -s "$(RUNTIME_LOCK)" "$$tmp_lock"; then \
		echo "$(RUNTIME_LOCK) is stale; run make lock-runtime"; \
		diff -u "$(RUNTIME_LOCK)" "$$tmp_lock" || true; \
		rm -f "$$tmp_lock"; \
		exit 1; \
	fi; \
	rm -f "$$tmp_lock"
	tmp_site=$$(mktemp -d); \
	$(PYTHON) -m pip install --require-hashes --target "$$tmp_site" -r $(RUNTIME_LOCK); \
	rm -rf "$$tmp_site"

lint: install ## Run lint checks
	$(PYTHON) -m ruff check dashboard_action tests scripts

type-check: install ## Run static type checks
	$(PYTHON) -m mypy

validate: validate-action validate-workflows validate-runtime-lock validate-vendored-assets ## Run validation checks

validate-action: install ## Validate action.yml
	$(PYTHON) -c "import pathlib, yaml; data = yaml.safe_load(pathlib.Path('action.yml').read_text()); assert data['runs']['using'] == 'composite'"

validate-workflows: install ## Validate GitHub workflow YAML
	$(PYTHON) -c "import pathlib, yaml; [yaml.safe_load(path.read_text()) for path in pathlib.Path('.github/workflows').glob('*.yml')]"

validate-vendored-assets: install ## Validate vendored third-party assets
	$(PYTHON) scripts/validate_vendored_assets.py

update-vendored-assets: install ## Update vendored third-party assets from upstream package registries
	$(PYTHON) scripts/update_vendored_assets.py

build-template: install ## Build the clean generated template tree in dist/template/
	$(PYTHON) scripts/build_template.py

verify-template: build-template ## Build and verify dist/template/ against the template manifest

build-and-verify-generated: verify-template verify-demo ## Build and verify generated template and demo outputs

verify-workflow-classification: install ## Verify maintainer vs template workflow boundaries
	$(PYTHON) scripts/verify_workflow_classification.py

validate-template-action-ref: install ## Verify the public template action ref satisfies the template contract
	$(PYTHON) scripts/validate_template_action_ref.py

template-smoke: build-template ## Smoke-test ephemeral template publish and generated workflows
	$(PYTHON) scripts/smoke_template_release.py --output dist/template

template-consumer-e2e: build-template ## Run generated template consumers against the local action runtime
	$(PYTHON) scripts/template_consumer_e2e.py --template-dir dist/template --action-repo $(ACTION_REPO) --action-python $(ACTION_PYTHON)

template-action-boundary-e2e: build-template ## Run the generated-template composite action.yml boundary check
	$(PYTHON) scripts/template_consumer_e2e.py --composite-boundary --template-dir dist/template --action-repo $(ACTION_REPO) --action-python $(ACTION_PYTHON)

template-compat-e2e: build-template ## Run candidate action against current and minimum compatible templates
	$(PYTHON) scripts/template_compat_e2e.py --current-template-dir dist/template --action-repo $(ACTION_REPO) --action-python $(ACTION_PYTHON) $(TEMPLATE_COMPAT_EXTRA_ARGS)

template-public-action-e2e: build-template ## Run generated template against the resolved public action ref
	$(PYTHON) scripts/template_public_action_e2e.py --template-dir dist/template --action-python $(ACTION_PYTHON)

package-template-release: build-template ## Build deterministic generated-template release artifacts
	rm -rf $(TEMPLATE_RELEASE_ARTIFACTS_DIR)
	$(PYTHON) scripts/template_provenance.py package --root dist/template --output-dir $(TEMPLATE_RELEASE_ARTIFACTS_DIR)

publish-template-dry-run: build-template ## Show the generated template publish target without pushing
	$(PYTHON) scripts/publish_generated_repo.py --output dist/template --remote $(TEMPLATE_REMOTE) --branch main --expected-repo $(TEMPLATE_EXPECTED_REPO) --message "$(TEMPLATE_PUBLISH_MESSAGE)"

publish-template: build-template ## Publish dist/template/ to the template repository main branch
	$(PYTHON) scripts/publish_generated_repo.py --output dist/template --remote $(TEMPLATE_REMOTE) --branch main --expected-repo $(TEMPLATE_EXPECTED_REPO) --message "$(TEMPLATE_PUBLISH_MESSAGE)" --push

publish-template-staging-dry-run: build-template ## Show the generated template staging publish target without pushing
	$(PYTHON) scripts/publish_generated_repo.py --output dist/template --remote $(TEMPLATE_STAGING_REMOTE) --branch main --expected-repo $(TEMPLATE_STAGING_EXPECTED_REPO) --message "$(TEMPLATE_STAGING_PUBLISH_MESSAGE)"

publish-template-staging: build-template ## Publish dist/template/ to the private staging template repository
	$(PYTHON) scripts/publish_generated_repo.py --output dist/template --remote $(TEMPLATE_STAGING_REMOTE) --branch main --expected-repo $(TEMPLATE_STAGING_EXPECTED_REPO) --message "$(TEMPLATE_STAGING_PUBLISH_MESSAGE)" --push

build-demo: build-template ## Build the public demo repository tree in dist/demo/
	$(PYTHON) scripts/build_demo_repo.py --output dist/demo

verify-demo: build-demo ## Build and verify dist/demo/ public demo repository output

publish-demo-dry-run: build-demo ## Show the generated demo publish target without pushing
	$(PYTHON) scripts/publish_demo_repo.py --output dist/demo --remote $(DEMO_REMOTE) --branch main --expected-repo $(DEMO_EXPECTED_REPO) --message "$(DEMO_PUBLISH_MESSAGE)"

publish-demo: build-demo ## Publish dist/demo/ to the public demo repository main branch
	$(PYTHON) scripts/publish_demo_repo.py --output dist/demo --remote $(DEMO_REMOTE) --branch main --expected-repo $(DEMO_EXPECTED_REPO) --message "$(DEMO_PUBLISH_MESSAGE)" --push

ci: lint type-check validate test coverage ## Run CI checks

fixtures: fixture-collect fixture-publish fixture-rotate-key preview-collection-quality-dashboard ## Run fixture checks

fixture-collect: install ## Run collect fixture without live GitHub API calls
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_collect_fixture_updates_artifact_without_rendering_outputs -v

fixture-publish: install ## Run publish fixture without live GitHub API calls
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_publish_fixture_renders_outputs_without_live_api -v

fixture-rotate-key: install ## Run rotate-key fixture
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_rotate_key_fixture_reencrypts_with_next_secret -v

preview-collection-quality-dashboard: install ## Render dashboard from collection-quality fixture data
	rm -rf $(COLLECTION_QUALITY_PREVIEW_OUTPUT)
	mkdir -p $(COLLECTION_QUALITY_PREVIEW_OUTPUT)
	cp -R $(COLLECTION_QUALITY_PREVIEW_FIXTURE)/. $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/
	cd $(COLLECTION_QUALITY_PREVIEW_OUTPUT) && \
		REPONOMICS_MODE=publish \
		REPONOMICS_DATA_MODE=plaintext \
		GITHUB_EVENT_REPOSITORY_PRIVATE=true \
		REPONOMICS_GENERATE_README=false \
		$(abspath $(PYTHON)) -m dashboard_action.run
	@test -s $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html
	@test -s $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/assets/chart.umd.min.js
	@grep -q 'src="assets/chart.umd.min.js"' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html
	@grep -q 'id="calendarMonthLabel"' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html
	@grep -q '"message":"Collection gaps detected in the latest run: 1 skipped, 0 error(s), 1/2 repos collected."' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html
	@grep -q '"date":"2026-04-30","status":"gaps_detected"' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html
	@echo "Preview ready: $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html"

dashboard-scenario-snapshots: install ## Check production dashboard scenario snapshots
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_dashboard_scenario_snapshots.py -v

update-dashboard-scenario-snapshots: install ## Refresh production dashboard scenario snapshots
	UPDATE_DASHBOARD_SCENARIO_SNAPSHOTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_dashboard_scenario_snapshots.py -v

clean: ## Remove local generated state
	rm -rf $(VENV) .pytest_cache .ruff_cache .coverage coverage.xml data dist docs/assets docs/index.html .dashboard-data-artifact .tmp
