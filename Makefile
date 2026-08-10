.DEFAULT_GOAL := help

.PHONY: help install pre-commit-install pre-commit-run ci prebeta-check
.PHONY: test js-test js-coverage js-smoke coverage complexity security security-audit audit-runtime-lock lock-runtime validate-runtime-lock lock-guide-tooling validate-guide-tooling-lock lock-analysis validate-analysis-lock update-vendored-assets
.PHONY: lint type-check markdown-format
.PHONY: validate validate-action validate-workflows validate-vendored-assets
.PHONY: build-template verify-template build-and-verify-generated verify-workflow-classification validate-template-action-ref validate-template-accepted-action template-smoke template-consumer-e2e template-action-boundary-e2e template-compat-e2e template-public-action-e2e template-accepted-action-e2e template-release-gates package-template-release publish-template-dry-run publish-template staging-smoke build-demo verify-demo render-demo-preview preview-demo preview-demo-site publish-demo-dry-run publish-demo
.PHONY: fixtures fixture-collect fixture-publish fixture-rotate-key preview-collection-quality-dashboard dashboard-scenario-snapshots update-dashboard-scenario-snapshots dashboard-guide-assets dashboard-guide dashboard-guide-refresh clean

VENV := venv
BOOTSTRAP_PYTHON ?= python3
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PIP_VERSION ?= 26.1.2
NODE ?= node
NPX ?= npx
PIPX ?= pipx
JS_SMOKE_PYTHON ?= python3
GUIDE_PYTHON ?= $(PIPX) run --with Pillow --with reportlab python
GUIDE_NODE ?= $(NPX) --yes --package playwright -- node
GUIDE_NODE_PATH ?=
GUIDE_ASSET_CAPTURE_ARGS ?=
ANTIPASTA := $(VENV)/bin/antipasta
PIP_AUDIT := $(VENV)/bin/pip-audit
PIP_COMPILE := $(VENV)/bin/pip-compile
PRE_COMMIT := $(VENV)/bin/pre-commit
INSTALL_STAMP := $(VENV)/.install.stamp
COMPLEXITY_INSTALL_STAMP := $(VENV)/.complexity-install.stamp
COVERAGE_FAIL_UNDER ?= 70
RUNTIME_LOCK := requirements-runtime.txt
GUIDE_TOOLING_IN := requirements-guide-tooling.in
GUIDE_TOOLING_LOCK := requirements-guide-tooling.txt
ANALYSIS_IN := requirements-analysis.in
ANALYSIS_LOCK := requirements-analysis.txt
PIP_INSTALL_FLAGS := --upgrade --upgrade-strategy eager
PIP_COMPILE_RUNTIME_FLAGS := --generate-hashes --strip-extras --resolver=backtracking --no-header --quiet
PIP_COMPILE_RUNTIME_UPGRADE_FLAGS := $(PIP_COMPILE_RUNTIME_FLAGS) --upgrade
PIP_COMPILE_ANALYSIS_FLAGS := $(PIP_COMPILE_RUNTIME_FLAGS) --allow-unsafe
PIP_COMPILE_ANALYSIS_UPGRADE_FLAGS := $(PIP_COMPILE_ANALYSIS_FLAGS) --upgrade
MDFORMAT_VERSION ?= 1.0.0
MDFORMAT_GFM_VERSION ?= 1.0.0
MDFORMAT_SPEC ?= mdformat==$(MDFORMAT_VERSION)
MDFORMAT_WITH ?= mdformat-gfm==$(MDFORMAT_GFM_VERSION)
MDFORMAT_ARGS ?= --wrap no --number --extensions gfm
MARKDOWN_FILES ?= $(shell git ls-files 'docs/**/*.md')
COLLECTION_QUALITY_PREVIEW_FIXTURE := tests/fixtures/collection_quality_preview
COLLECTION_QUALITY_PREVIEW_OUTPUT := .tmp/collection_quality_preview
TEMPLATE_REMOTE ?= https://github.com/reponomics/reponomics-dashboard.git
TEMPLATE_EXPECTED_REPO ?= reponomics/reponomics-dashboard
TEMPLATE_PUBLISH_MESSAGE ?= chore: publish generated template
TEMPLATE_RELEASE_ARTIFACTS_DIR ?= dist/template-release
STAGING_SMOKE_REMOTE ?= https://github.com/reponomics/reponomics-dashboard-staging.git
STAGING_SMOKE_EXPECTED_REPO ?= reponomics/reponomics-dashboard-staging
STAGING_SMOKE_BRANCH ?= main
STAGING_SMOKE_OUTPUT ?= dist/staging-smoke
STAGING_SMOKE_EVIDENCE ?= dist/staging-smoke-evidence.md
STAGING_SMOKE_MESSAGE ?= chore: publish staging smoke dashboard
STAGING_SMOKE_REPOSITORIES ?= reponomics/reponomics-dashboard-action
STAGING_SMOKE_PUBLISH_REPOSITORIES ?=
STAGING_SMOKE_PUSH ?=
DEMO_REMOTE ?= https://github.com/reponomics/reponomics-dashboard-demo.git
DEMO_EXPECTED_REPO ?= reponomics/reponomics-dashboard-demo
DEMO_PUBLISH_MESSAGE ?= chore: publish generated demo
DEMO_PREVIEW_DIR ?= dist/demo/docs
DEMO_PREVIEW_HOST ?= 127.0.0.1
DEMO_PREVIEW_PORT ?= 8765
DEMO_PREVIEW_KEY ?= reponomics-demo-public-key-2026-keep-this-visible-do-not-reuse
ACTION_REPO ?= .
ACTION_PYTHON ?= $(PYTHON)
TEMPLATE_COMPAT_EXTRA_ARGS ?=

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: $(INSTALL_STAMP) ## Create venv and install dependencies

$(INSTALL_STAMP): pyproject.toml $(RUNTIME_LOCK) Makefile
	$(BOOTSTRAP_PYTHON) -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade "pip==$(PIP_VERSION)"
	$(PIP) install $(PIP_INSTALL_FLAGS) -e '.[dev]'
	$(PYTHON) -m pip install --upgrade "pip==$(PIP_VERSION)"
	touch $(INSTALL_STAMP)

$(COMPLEXITY_INSTALL_STAMP): $(INSTALL_STAMP) pyproject.toml Makefile
	$(PIP) install $(PIP_INSTALL_FLAGS) -e '.[complexity]'
	touch $(COMPLEXITY_INSTALL_STAMP)

pre-commit-install: install ## Install local pre-commit hooks
	GIT_CONFIG_GLOBAL=/dev/null $(PRE_COMMIT) install --install-hooks --hook-type pre-commit --hook-type pre-push

pre-commit-run: install ## Run pre-commit hooks against all files
	$(PRE_COMMIT) run --all-files

test: install js-test ## Run tests
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests -v

js-test: ## Run JavaScript module tests
	$(NODE) --test tests/js/*.test.mjs

js-coverage: ## Run JavaScript module tests with Node coverage reporting
	$(NODE) --test --experimental-test-coverage tests/js/*.test.mjs

js-smoke: ## Check dashboard JavaScript syntax and flattened secure runtime assembly
	NODE=$(NODE) $(JS_SMOKE_PYTHON) scripts/check_dashboard_js_smoke.py

dashboard-guide-assets: render-demo-preview ## Capture dashboard guide screenshot assets from the rendered demo preview
	NODE_PATH="$(GUIDE_NODE_PATH)" $(GUIDE_NODE) scripts/capture_dashboard_guide_assets.mjs \
		--dashboard-dir $(DEMO_PREVIEW_DIR) \
		--out-dir docs/promotional/dashboard-guide/assets \
		$(GUIDE_ASSET_CAPTURE_ARGS)

dashboard-guide: ## Build editable HTML and PDF dashboard guide artifacts
	$(GUIDE_PYTHON) scripts/build_dashboard_guide.py

dashboard-guide-refresh: dashboard-guide-assets dashboard-guide ## Refresh dashboard guide screenshots, HTML, and PDF

coverage: install ## Run tests with coverage report
	$(PYTHON) -m pytest tests -v --cov=dashboard_action --cov-report=term-missing --cov-report=xml --cov-fail-under=$(COVERAGE_FAIL_UNDER)

complexity: $(COMPLEXITY_INSTALL_STAMP) ## Install optional complexity tooling and run metrics
	$(ANTIPASTA) metrics --directory dashboard_action

security-audit: install ## Audit Python dependencies for known vulnerabilities
	$(PIP_AUDIT) --local --skip-editable --progress-spinner off

audit-runtime-lock: install ## Audit hash-pinned runtime dependency lock
	$(PIP_AUDIT) --requirement $(RUNTIME_LOCK) --no-deps --progress-spinner off

security: security-audit audit-runtime-lock validate-runtime-lock validate-guide-tooling-lock validate-analysis-lock validate-vendored-assets ## Run open-source security checks

lock-runtime: install ## Regenerate hash-pinned runtime dependency lock
	$(PIP_COMPILE) $(PIP_COMPILE_RUNTIME_UPGRADE_FLAGS) --output-file $(RUNTIME_LOCK) pyproject.toml

validate-runtime-lock: install ## Verify runtime lock matches constraints without upgrades and is hash-installable
	set -e; \
	tmp_lock=$$(mktemp); \
	trap 'rm -f "$$tmp_lock"' EXIT; \
	cp "$(RUNTIME_LOCK)" "$$tmp_lock"; \
	$(PIP_COMPILE) $(PIP_COMPILE_RUNTIME_FLAGS) --output-file "$$tmp_lock" pyproject.toml; \
	if ! cmp -s "$(RUNTIME_LOCK)" "$$tmp_lock"; then \
		echo "$(RUNTIME_LOCK) is stale; run make lock-runtime"; \
		diff -u "$(RUNTIME_LOCK)" "$$tmp_lock" || true; \
		exit 1; \
	fi
	set -e; \
	tmp_site=$$(mktemp -d); \
	trap 'rm -rf "$$tmp_site"' EXIT; \
	$(PYTHON) -m pip install --require-hashes --target "$$tmp_site" -r $(RUNTIME_LOCK)

lock-guide-tooling: install ## Regenerate hash-pinned promotional guide workflow tooling lock
	$(PIP_COMPILE) $(PIP_COMPILE_RUNTIME_UPGRADE_FLAGS) --output-file $(GUIDE_TOOLING_LOCK) $(GUIDE_TOOLING_IN)

validate-guide-tooling-lock: install ## Verify promotional guide workflow tooling lock is hash-installable
	set -e; \
	tmp_lock=$$(mktemp); \
	trap 'rm -f "$$tmp_lock"' EXIT; \
	cp "$(GUIDE_TOOLING_LOCK)" "$$tmp_lock"; \
	$(PIP_COMPILE) $(PIP_COMPILE_RUNTIME_FLAGS) --output-file "$$tmp_lock" $(GUIDE_TOOLING_IN); \
	if ! cmp -s "$(GUIDE_TOOLING_LOCK)" "$$tmp_lock"; then \
		echo "$(GUIDE_TOOLING_LOCK) is stale; run make lock-guide-tooling"; \
		diff -u "$(GUIDE_TOOLING_LOCK)" "$$tmp_lock" || true; \
		exit 1; \
	fi
	set -e; \
	tmp_site=$$(mktemp -d); \
	trap 'rm -rf "$$tmp_site"' EXIT; \
	$(PYTHON) -m pip install --require-hashes --target "$$tmp_site" -r $(GUIDE_TOOLING_LOCK)

lock-analysis: install ## Regenerate hash-pinned static-analysis dependency lock
	$(PIP_COMPILE) $(PIP_COMPILE_ANALYSIS_UPGRADE_FLAGS) --output-file $(ANALYSIS_LOCK) $(ANALYSIS_IN)

validate-analysis-lock: install ## Verify static-analysis dependency lock is current and hash-installable
	set -e; \
	tmp_lock=$$(mktemp); \
	trap 'rm -f "$$tmp_lock"' EXIT; \
	cp "$(ANALYSIS_LOCK)" "$$tmp_lock"; \
	$(PIP_COMPILE) $(PIP_COMPILE_ANALYSIS_FLAGS) --output-file "$$tmp_lock" $(ANALYSIS_IN); \
	if ! cmp -s "$(ANALYSIS_LOCK)" "$$tmp_lock"; then \
		echo "$(ANALYSIS_LOCK) is stale; run make lock-analysis"; \
		diff -u "$(ANALYSIS_LOCK)" "$$tmp_lock" || true; \
		exit 1; \
	fi
	set -e; \
	tmp_site=$$(mktemp -d); \
	trap 'rm -rf "$$tmp_site"' EXIT; \
	$(PYTHON) -m pip install --require-hashes --target "$$tmp_site" -r $(ANALYSIS_LOCK)

lint: install ## Run lint checks
	$(PYTHON) -m ruff check dashboard_action tests scripts

type-check: install ## Run static type checks
	$(PYTHON) -m mypy

markdown-format: ## Format tracked Markdown with mdformat via pipx
	$(PIPX) run --spec '$(MDFORMAT_SPEC)' --with '$(MDFORMAT_WITH)' mdformat $(MDFORMAT_ARGS) $(MARKDOWN_FILES)

validate: validate-action validate-workflows validate-runtime-lock validate-vendored-assets ## Run validation checks

validate-action: install ## Validate action.yml
	$(PYTHON) -c "import pathlib, yaml; paths = [pathlib.Path('action.yml'), pathlib.Path('.github/actions/bandit/action.yml')]; assert all(yaml.safe_load(path.read_text())['runs']['using'] == 'composite' for path in paths)"

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

validate-template-accepted-action: install ## Verify accepted action release metadata resolves publicly
	$(PYTHON) scripts/validate_template_action_ref.py --require-accepted-action-release

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

template-accepted-action-e2e: build-template ## Run generated template against accepted action release metadata
	$(PYTHON) scripts/template_public_action_e2e.py --template-dir dist/template --action-python $(ACTION_PYTHON) --accepted-action

template-release-gates: verify-workflow-classification verify-template validate-template-action-ref validate-template-accepted-action template-smoke template-accepted-action-e2e publish-template-dry-run package-template-release ## Run release gates for generated template publication

package-template-release: build-template ## Build deterministic generated-template release artifacts
	rm -rf $(TEMPLATE_RELEASE_ARTIFACTS_DIR)
	$(PYTHON) scripts/template_provenance.py package --root dist/template --output-dir $(TEMPLATE_RELEASE_ARTIFACTS_DIR)

publish-template-dry-run: build-template ## Show the generated template publish target without pushing
	$(PYTHON) scripts/publish_generated_repo.py --output dist/template --remote $(TEMPLATE_REMOTE) --branch main --expected-repo $(TEMPLATE_EXPECTED_REPO) --message "$(TEMPLATE_PUBLISH_MESSAGE)"

publish-template: build-template ## Publish dist/template/ to the template repository main branch
	$(PYTHON) scripts/publish_generated_repo.py --output dist/template --remote $(TEMPLATE_REMOTE) --branch main --expected-repo $(TEMPLATE_EXPECTED_REPO) --message "$(TEMPLATE_PUBLISH_MESSAGE)" --push

staging-smoke: install ## Prepare or publish the copied staging dashboard smoke tree
	$(PYTHON) scripts/staging_smoke.py \
		--output $(STAGING_SMOKE_OUTPUT) \
		--remote $(STAGING_SMOKE_REMOTE) \
		--expected-repo $(STAGING_SMOKE_EXPECTED_REPO) \
		--branch $(STAGING_SMOKE_BRANCH) \
		--message "$(STAGING_SMOKE_MESSAGE)" \
		--evidence $(STAGING_SMOKE_EVIDENCE) \
		$(foreach repository,$(STAGING_SMOKE_REPOSITORIES),--repository $(repository)) \
		$(foreach repository,$(STAGING_SMOKE_PUBLISH_REPOSITORIES),--publish-repository $(repository)) \
		$(STAGING_SMOKE_PUSH)

build-demo: build-template ## Build the public demo repository tree in dist/demo/
	$(PYTHON) scripts/build_demo_repo.py --output dist/demo

verify-demo: build-demo ## Build and verify dist/demo/ public demo repository output

render-demo-preview: build-demo ## Render the demo Pages dashboard locally in dist/demo/docs/
	mkdir -p dist/demo/data
	cp dist/demo-seed/dashboard-data.enc dist/demo/data/dashboard-data.enc
	cd dist/demo && \
		REPONOMICS_MODE=publish \
		REPONOMICS_CONFIG_PATH=config.yaml \
		REPONOMICS_DATA_MODE=encrypted \
		REPONOMICS_DASHBOARD_SECRET="$(DEMO_PREVIEW_KEY)" \
		REPONOMICS_DEMO_UNLOCK_KEY="$(DEMO_PREVIEW_KEY)" \
		REPONOMICS_PUBLISH_PAGES=true \
		REPONOMICS_GENERATE_README=false \
		GITHUB_EVENT_REPOSITORY_PRIVATE=false \
		$(abspath $(PYTHON)) -m dashboard_action.run
	@test -s $(DEMO_PREVIEW_DIR)/index.html
	@test -s $(DEMO_PREVIEW_DIR)/assets/encrypted-dashboard-data.json
	@test -s $(DEMO_PREVIEW_DIR)/assets/demo-unlock.css
	@echo "Demo Pages preview rendered: $(DEMO_PREVIEW_DIR)/index.html"

preview-demo: preview-demo-site ## Render and serve the local demo dashboard preview

preview-demo-site: render-demo-preview ## Serve the local demo Pages dashboard preview
	@echo "Serving demo preview at http://$(DEMO_PREVIEW_HOST):$(DEMO_PREVIEW_PORT)/"
	$(PYTHON) -m http.server $(DEMO_PREVIEW_PORT) --bind $(DEMO_PREVIEW_HOST) --directory $(DEMO_PREVIEW_DIR)

publish-demo-dry-run: build-demo ## Show the generated demo publish target without pushing
	$(PYTHON) scripts/publish_demo_repo.py --output dist/demo --remote $(DEMO_REMOTE) --branch main --expected-repo $(DEMO_EXPECTED_REPO) --message "$(DEMO_PUBLISH_MESSAGE)"

publish-demo: build-demo ## Publish dist/demo/ to the public demo repository main branch
	$(PYTHON) scripts/publish_demo_repo.py --output dist/demo --remote $(DEMO_REMOTE) --branch main --expected-repo $(DEMO_EXPECTED_REPO) --message "$(DEMO_PUBLISH_MESSAGE)" --push

ci: lint type-check validate test coverage ## Run CI checks

prebeta-check: ci security template-release-gates template-compat-e2e js-coverage js-smoke verify-demo publish-demo-dry-run ## Run external beta readiness checks

fixtures: fixture-collect fixture-publish fixture-rotate-key preview-collection-quality-dashboard ## Run fixture checks

fixture-collect: install ## Run collect fixture without live GitHub API calls
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/runner/test_runner_artifact_lineage.py::test_collect_fixture_updates_artifact_without_rendering_outputs -v

fixture-publish: install ## Run publish fixture without live GitHub API calls
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/runner/test_runner_doctor_diagnostics.py::test_publish_fixture_renders_outputs_without_live_api -v

fixture-rotate-key: install ## Run rotate-key fixture
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/runner/test_runner_key_rotation_incident.py::test_rotate_key_fixture_reencrypts_with_next_secret -v

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
	@test -s $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/assets/dashboard-data.json
	@grep -q 'src="assets/chart.umd.min.js"' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html
	@grep -q 'id="calendarMonthLabel"' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html
	@grep -q '"message":"Collection gaps detected in the latest run: 1 skipped, 0 error(s), 1/2 repos collected."' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/assets/dashboard-data.json
	@grep -q '"date":"2026-04-30","status":"gaps_detected"' $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/assets/dashboard-data.json
	@echo "Preview ready: $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html"

dashboard-scenario-snapshots: install ## Check production dashboard scenario snapshots
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_dashboard_scenario_snapshots.py -v

update-dashboard-scenario-snapshots: install ## Refresh production dashboard scenario snapshots
	UPDATE_DASHBOARD_SCENARIO_SNAPSHOTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_dashboard_scenario_snapshots.py -v

clean: ## Remove local generated state
	rm -rf $(VENV) .pytest_cache .ruff_cache .coverage coverage.xml data dist docs/assets docs/index.html .dashboard-data-artifact .tmp
