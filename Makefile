.DEFAULT_GOAL := help

.PHONY: help install pre-commit-install pre-commit-run ci
.PHONY: test coverage complexity
.PHONY: lint type-check
.PHONY: validate validate-action validate-workflows validate-action-pins validate-vendored-assets validate-release-notice
.PHONY: fixture-collect fixture-publish fixture-rotate-key preview-collection-quality-dashboard clean

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
ANTIPASTA := $(VENV)/bin/antipasta
PRE_COMMIT := $(VENV)/bin/pre-commit
INSTALL_STAMP := $(VENV)/.install.stamp
COVERAGE_FAIL_UNDER ?= 70
COLLECTION_QUALITY_PREVIEW_FIXTURE := tests/fixtures/collection_quality_preview
COLLECTION_QUALITY_PREVIEW_OUTPUT := .tmp/collection_quality_preview

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: $(INSTALL_STAMP) ## Create venv and install dependencies

$(INSTALL_STAMP): pyproject.toml
	python3 -m venv $(VENV)
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

lint: install ## Run lint checks
	$(PYTHON) -m ruff check dashboard_action tests scripts

type-check: install ## Run static type checks
	$(PYTHON) -m mypy

validate: validate-action validate-workflows validate-action-pins validate-vendored-assets validate-release-notice ## Run validation checks

validate-action: install ## Validate action.yml
	$(PYTHON) -c "import pathlib, yaml; data = yaml.safe_load(pathlib.Path('action.yml').read_text()); assert data['runs']['using'] == 'composite'"

validate-workflows: install ## Validate GitHub workflow YAML
	$(PYTHON) -c "import pathlib, yaml; [yaml.safe_load(path.read_text()) for path in pathlib.Path('.github/workflows').glob('*.yml')]"

validate-action-pins: install ## Validate imported GitHub Action SHA pins
	$(PYTHON) scripts/validate_action_pins.py action.yml .github

validate-vendored-assets: install ## Validate vendored third-party assets
	$(PYTHON) scripts/validate_vendored_assets.py

validate-release-notice: install ## Validate release notice tooling
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_release_notice_validation_cli_accepts_valid_block tests/test_runner.py::test_release_notice_validation_cli_rejects_malformed_block -v

ci: lint type-check validate-action validate-workflows test coverage validate-action-pins validate-release-notice validate-vendored-assets ## Run CI checks

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
	@echo "Preview ready: $(COLLECTION_QUALITY_PREVIEW_OUTPUT)/docs/index.html"

clean: ## Remove local generated state
	rm -rf $(VENV) .pytest_cache .ruff_cache .coverage coverage.xml data dist docs/assets docs/index.html .traffic-artifact .tmp
