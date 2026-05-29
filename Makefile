.DEFAULT_GOAL := help

.PHONY: help install pre-commit-install pre-commit-run ci
.PHONY: test coverage complexity security security-audit lock-runtime validate-runtime-lock update-vendored-assets
.PHONY: lint type-check
.PHONY: validate validate-action validate-workflows validate-action-pins validate-vendored-assets validate-release-notice
.PHONY: fixtures fixture-collect fixture-publish fixture-rotate-key preview-collection-quality-dashboard update-dashboard-scenario-snapshots clean

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
COLLECTION_QUALITY_PREVIEW_FIXTURE := tests/fixtures/collection_quality_preview
COLLECTION_QUALITY_PREVIEW_OUTPUT := .tmp/collection_quality_preview

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: $(INSTALL_STAMP) ## Create venv and install dependencies

$(INSTALL_STAMP): pyproject.toml
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PIP) install -e '.[dev]'
	touch $(INSTALL_STAMP)

pre-commit-install: install ## Install local pre-commit hooks
	GIT_CONFIG_GLOBAL=/dev/null $(PRE_COMMIT) install --install-hooks

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

security: security-audit validate-runtime-lock validate-vendored-assets ## Run open-source security checks

lock-runtime: install ## Regenerate hash-pinned runtime dependency lock
	$(PIP_COMPILE) $(PIP_COMPILE_RUNTIME_FLAGS) --output-file $(RUNTIME_LOCK) pyproject.toml

validate-runtime-lock: install ## Verify runtime dependency lock is current and hash-installable
	tmp_lock=$$(mktemp); \
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

validate: validate-action validate-workflows validate-action-pins validate-runtime-lock validate-vendored-assets validate-release-notice ## Run validation checks

validate-action: install ## Validate action.yml
	$(PYTHON) -c "import pathlib, yaml; data = yaml.safe_load(pathlib.Path('action.yml').read_text()); assert data['runs']['using'] == 'composite'"

validate-workflows: install ## Validate GitHub workflow YAML
	$(PYTHON) -c "import pathlib, yaml; [yaml.safe_load(path.read_text()) for path in pathlib.Path('.github/workflows').glob('*.yml')]"

validate-action-pins: install ## Validate imported GitHub Action SHA pins
	$(PYTHON) scripts/validate_action_pins.py action.yml .github

validate-vendored-assets: install ## Validate vendored third-party assets
	$(PYTHON) scripts/validate_vendored_assets.py

update-vendored-assets: install ## Update vendored third-party assets from upstream package registries
	$(PYTHON) scripts/update_vendored_assets.py

validate-release-notice: install ## Validate release notice tooling
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_release_notice_validation_cli_accepts_valid_block tests/test_runner.py::test_release_notice_validation_cli_rejects_malformed_block -v

ci: lint type-check validate-action validate-workflows test coverage validate-action-pins validate-release-notice validate-runtime-lock validate-vendored-assets ## Run CI checks

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
		REPONOMICS_PRIVACY_MODE=plain \
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

update-dashboard-scenario-snapshots: install ## Refresh production dashboard scenario snapshots
	UPDATE_DASHBOARD_SCENARIO_SNAPSHOTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_dashboard_scenario_snapshots.py -v

clean: ## Remove local generated state
	rm -rf $(VENV) .pytest_cache .ruff_cache .coverage coverage.xml data dist docs/assets docs/index.html .dashboard-data-artifact .tmp
