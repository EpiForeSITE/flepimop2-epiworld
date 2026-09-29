# Recipe names mirror flepimop2's justfile so habits transfer between the repos.

# Run all default tasks for local development
default: dev lint

# Run all default dev tasks
dev: ruff mypy test

# Run all default lint tasks
lint: yamllint

# Run all default CI tasks
ci: quality ci-pytest

# Format code using `ruff`
[group('dev')]
ruff:
    uv run ruff format
    uv run ruff check --fix

# Run coverage tests
[group('dev')]
cov:
    uv run pytest -m "not integration" --cov=src --cov-report=term-missing

# Run integration tests
[group('dev')]
integration:
    uv run pytest -m "integration"

# Run coverage and integration tests
[group('dev')]
test: cov integration

# Type check using `mypy`
[group('dev')]
mypy:
    uv run mypy

# Clean up venvs, caches, and build artifacts
[group('dev')]
[unix]
clean:
    rm -rf .*cache
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    rm -rf .venv
    rm -rf dist

# Run CI `ruff` formatting/linting checks
[group('ci')]
ci-ruff:
    uv run --locked ruff format --check
    uv run --locked ruff check --no-fix

# Run CI mypy type checking
[group('ci')]
ci-mypy:
    uv run --locked mypy

# Run CI pytest checks against the committed lockfile
[group('ci')]
ci-pytest:
    uv run --locked --isolated --group dev pytest -m "not integration"

# Run CI minimum-version pytest checks without the committed lockfile
[unix]
[group('ci')]
ci-pytest-lowest-direct:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f uv.lock ]; then
        trap 'if [ -f uv.lock.bak ]; then mv uv.lock.bak uv.lock; fi' EXIT
        mv uv.lock uv.lock.bak
    fi
    env -u UV_LOCKED -u UV_FROZEN UV_RESOLUTION=lowest-direct \
        uv run --isolated --group dev pytest -m "not integration"

# Run CI quality checks (format/lint/type check)
[group('ci')]
quality: ci-ruff ci-mypy

# Build sdist and wheel, then validate package metadata
[unix]
[group('build')]
build-check:
    rm -rf dist/
    uv run python -m build
    uv run python -m twine check --strict dist/*

# Verify the wheel carries both modules and keeps the namespace package intact
[unix]
[group('build')]
check-wheel-contents:
    #!/usr/bin/env bash
    set -euo pipefail
    WHEEL="$(ls dist/*.whl | head -1)"
    echo "checking ${WHEEL}"
    unzip -l "${WHEEL}" | grep -q 'flepimop2_epiworld/_bridge.py'
    unzip -l "${WHEEL}" | grep -q 'flepimop2/system/epiworld/__init__.py'
    unzip -l "${WHEEL}" | grep -q 'flepimop2/engine/epiworld/__init__.py'
    # A top-level flepimop2/__init__.py would break the PEP 420 namespace and
    # shadow the real flepimop2 package.
    if unzip -l "${WHEEL}" | grep -qE ' flepimop2/__init__\.py$'; then
        echo "ERROR: wheel contains flepimop2/__init__.py; namespace package is broken" >&2
        exit 1
    fi
    echo "wheel contents OK"

# Build the dev container image locally
[group('build')]
container:
    docker build -f .devcontainer/Containerfile -t ghcr.io/epiforesite/flepimop2-epiworld:latest .

# Run the replicate example end to end
[unix]
[group('example')]
example:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ "${EXAMPLE_VERBOSE:-false}" == "true" ]]; then
        set -x
    fi
    cd examples/seirconn-replicates
    rm -f model_output/*.csv
    uv run --group example flepimop2 simulate config.yaml
    uv run --group example flepimop2 process config.yaml

# Lint YAML files using `yamllint`
[group('lint')]
yamllint:
    uv run yamllint --strict --config-file .yamllint.yaml .
