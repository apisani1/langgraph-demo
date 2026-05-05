.PHONY: all format format-diff format-tests lint lint-mypy lint-flake8 lint-pylint lint-diff lint-tests check pre-commit test tests test-cov test-verbose test-manual test-pattern test-file coverage help-test clean build venv venv-clean help

######################
# This automation tasks were inspired by automation patterns from
# phitoduck/python-course-cookiecutter-v2, but are an independent implementation.
######################

# Default target executed when no arguments are given to make.
all: help

######################
# ENVIRONMENT
######################

# Install core dependencies
install:
	@./run.sh install

# Install all development dependencies
install-dev:
	@./run.sh install:dev

# Install specific dependency groups
install-test:
	@./run.sh install:test

install-lint:
	@./run.sh install:lint

install-all:
	@./run.sh install:all

# Update all dependencies
update:
	@./run.sh update

# Create a new virtual environment
venv:
	@./run.sh venv

venv-clean:
	@./run.sh venv:clean

# Lock dependencies without installing them
lock:
	@./run.sh lock

# Create a new Jupyter kernel for the current project
kernel:
	@./run.sh kernel

# Remove the Jupyter kernel for the current project
remove-kernel:
	@./run.sh remove:kernel

# Export requirements.txt files
requirements:
	@./run.sh requirements

######################
# LINTING AND FORMATTING
######################

# Linting
lint:
	@./run.sh lint

lint-mypy:
	@./run.sh lint:mypy

lint-flake8:
	@./run.sh lint:flake8

lint-pylint:
	@./run.sh lint:pylint

# Run all linters on changed files
lint-diff:
	@./run.sh lint:diff

# Run all linters on test files
lint-tests:
	@./run.sh lint:tests

# Formatting
format:
	@./run.sh format

# Run formatters on changed files
format-diff:
	@./run.sh format:diff

# Run formatters on test files
format-tests:
	@./run.sh format:tests

# Combined check (useful for CI)
check:
	@./run.sh check

# Pre-commit check
pre-commit:
	@./run.sh pre:commit

######################
# TESTING
######################

# Run tests (maintains backward compatibility with Makefile interface)
test:
	@./run.sh tests $(TEST_FILE) $(PYTEST_ARGS)

# Alias for consistency with run.sh
tests:
	@./run.sh tests $(TEST_FILE) $(PYTEST_ARGS)

# Run tests with coverage
test-cov:
	@./run.sh tests:cov

# Run tests in verbose mode
test-verbose:
	@./run.sh tests:verbose

# Run tests marked as manual
test-manual:
	@uv run pytest -m manual

# Run tests that match a specific pattern
test-pattern:
	@if [ -z "$(p)" ]; then \
		echo "Usage: make test-pattern p=<pattern>"; \
		exit 1; \
	fi
	@./run.sh tests:pattern "$(p)"

# Run a specific test file
test-file:
	@if [ -z "$(f)" ]; then \
		echo "Usage: make test-file f=<file>"; \
		exit 1; \
	fi
	@./run.sh tests:file "$(f)" $(PYTEST_ARGS)

# Generate coverage report
coverage:
	@./run.sh coverage

# Help for pytest options
help-test:
	@echo '====== Pytest Options ======'
	@echo ''
	@echo 'Usage: make test [TEST_FILE=<file>] [PYTEST_ARGS="<args>"]'
	@echo ''
	@echo 'Common pytest options (pass via PYTEST_ARGS):'
	@echo '  -v, --verbose           Show more detailed output'
	@echo '  -x, --exitfirst         Stop on first failure'
	@echo '  --pdb                   Start the Python debugger on errors'
	@echo '  -m MARK                 Only run tests with specific markers'
	@echo '  -k EXPRESSION           Only run test files that match expression'
	@echo '  --log-cli-level=INFO    Show log messages in the console'
	@echo '  --cov=PACKAGE           Measure code coverage for a package'
	@echo '  --cov-report=html       Generate HTML coverage report'
	@echo ''
	@echo 'Examples:'
	@echo '  make test PYTEST_ARGS="-v"'
	@echo '  make test-pattern p="test_async"'
	@echo '  make test-file f=tests/test_example.py PYTEST_ARGS="-v"'
	@echo '  make test-cov'
	@echo ''
	@echo 'Test targets:'
	@echo '  make test-verbose         - Run tests with verbose output'
	@echo '  make test-cov             - Run tests with coverage report'
	@echo '  make test-manual          - Run tests marked as manual'
	@echo '  make test-pattern p=<pat> - Run tests matching pattern'
	@echo '  make test-file f=<file>   - Run tests in specific file'

######################
# BUILDING
######################

# Clean build artifacts
clean:
	@./run.sh clean

# Build package
build:
	@./run.sh build

######################
# HELP
######################

help:
	@echo '====== langgraph-demo Development Tool ======'
	@echo ''
	@echo 'Environment:'
	@echo '  make install              - Install core dependencies'
	@echo '  make install-dev          - Install all development dependencies'
	@echo '  make update               - Update dependencies'
	@echo '  make venv                 - Create and activate virtual environment'
	@echo ''
	@echo 'Linting & Formatting:'
	@echo '  make format               - Run all formatters'
	@echo '  make format-diff          - Run all formatters on changed files'
	@echo '  make format-tests         - Run all formatters on test files'
	@echo '  make lint                 - Run all linters'
	@echo '  make lint-diff            - Run all linters on changed files'
	@echo '  make lint-tests           - Run all linters on test files'
	@echo '  make check                - Run format, lint, and test'
	@echo '  make pre-commit           - Run format and lint on changed files'
	@echo ''
	@echo 'Testing:'
	@echo '  make test                 - Run tests'
	@echo '  make test-cov             - Run tests with coverage'
	@echo '  make test-verbose         - Run tests in verbose mode'
	@echo '  make test-manual          - Run tests marked as manual'
	@echo '  make test-pattern p=<pat> - Run tests matching pattern'
	@echo '  make coverage             - Generate coverage report'
	@echo '  make help-test            - Show help for pytest options'
	@echo ''
	@echo 'Building:'
	@echo '  make clean                - Clean build artifacts'
	@echo '  make build                - Build package'
