.DEFAULT_GOAL := help

.PHONY: help install pre-commit-install pre-commit-run test coverage complexity lint lint-python lint-types lint-action lint-workflows lint-action-pins lint-vendored-assets verify release-notice-verify fixture-collect fixture-publish fixture-rotate-key clean

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
ANTIPASTA := $(VENV)/bin/antipasta
PRE_COMMIT := $(VENV)/bin/pre-commit
COVERAGE_FAIL_UNDER ?= 70

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: $(VENV)/bin/activate ## Create venv and install dependencies
	$(PYTHON) -c "import antipasta, complexipy, cryptography, mypy, pre_commit, pytest, pytest_cov, requests, yaml" && $(PYTHON) -m ruff --version >/dev/null || $(PIP) install -e '.[dev]'

$(VENV)/bin/activate: pyproject.toml
	python3 -m venv $(VENV)
	$(PIP) install -e '.[dev]'
	touch $(VENV)/bin/activate

pre-commit-install: install ## Install local pre-commit hooks
	GIT_CONFIG_GLOBAL=/dev/null $(PRE_COMMIT) install --install-hooks

pre-commit-run: install ## Run pre-commit hooks against all files
	$(PRE_COMMIT) run --all-files

test: install ## Run action-local tests
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests -v

coverage: install ## Run tests with coverage report
	$(PYTHON) -m pytest tests -v --cov=traffic_report_action --cov-report=term-missing --cov-report=xml --cov-fail-under=$(COVERAGE_FAIL_UNDER)

complexity: install ## Run complexity metrics
	$(ANTIPASTA) metrics --directory traffic_report_action

lint: lint-python lint-types lint-action lint-workflows lint-action-pins lint-vendored-assets ## Run all lint checks

lint-python: install ## Run Python lint checks
	$(PYTHON) -m ruff check traffic_report_action tests scripts

lint-types: install ## Run static type checks
	$(PYTHON) -m mypy

lint-action: install ## Parse action.yml
	$(PYTHON) -c "import pathlib, yaml; data = yaml.safe_load(pathlib.Path('action.yml').read_text()); assert data['runs']['using'] == 'composite'"

lint-workflows: install ## Parse GitHub workflow YAML
	$(PYTHON) -c "import pathlib, yaml; [yaml.safe_load(path.read_text()) for path in pathlib.Path('.github/workflows').glob('*.yml')]"

lint-action-pins: install ## Require imported GitHub Actions to use full SHAs
	$(PYTHON) scripts/validate_action_pins.py action.yml .github

lint-vendored-assets: install ## Verify vendored third-party assets
	$(PYTHON) scripts/validate_vendored_assets.py

verify: lint coverage ## Run all local verification

release-notice-verify: install ## Validate release notice tooling
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_release_notice_validation_cli_accepts_valid_block tests/test_runner.py::test_release_notice_validation_cli_rejects_malformed_block -v

fixture-collect: install ## Run collect fixture without live GitHub API calls
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_collect_fixture_updates_artifact_without_rendering_outputs -v

fixture-publish: install ## Run publish fixture without live GitHub API calls
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_publish_fixture_renders_outputs_without_live_api -v

fixture-rotate-key: install ## Run rotate-key fixture
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest tests/test_runner.py::test_rotate_key_fixture_reencrypts_with_next_secret -v

clean: ## Remove local generated state
	rm -rf $(VENV) .pytest_cache .ruff_cache .coverage coverage.xml data dist docs/assets docs/index.html .traffic-artifact
