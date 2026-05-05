# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses UV for dependency management and a custom `run.sh` script for development tasks. All commands can be executed via either the Makefile (which delegates to `run.sh`) or directly via `run.sh`.

### Environment Setup
```bash
make venv                 # Create and activate local virtual environment
make install              # Install core dependencies
make install-lint         # Install linting dependencies
make install-test         # Install testing dependencies
make install-docs         # Install documentation dependencies
make install-dev          # Install all development dependencies (dev, test, lint, typing and docs dependency groups)
./run.sh install:all      # CI alternative: install all dependencies without interaction
```

### Code Quality
```bash
make format               # Format code with black and isort
make format-diff          # Run formatters on changed files
make lint                 # Run mypy, flake8, and pylint
make lint-diff            # Run all linters on changed files
make check                # Run format + lint + tests on all files(local development)
make pre-commit           # Format and lint only on changed files
./run.sh check:ci         # CI version (format only checks, no file modifications)

```

### Testing
```bash
make test                 # Run all tests
make test-cov             # Run tests with coverage
make coverage             # Generate coverage report
make test-verbose         # Run tests with verbose output
./run.sh tests:pattern "test_name"  # Run only tests matching pattern
```

### Documentation
```bash
make docs-api             # Generate API documentation automatically
make docs                 # Build Sphinx documentation
make docs-live            # Start live documentation server with auto-reload
make docs-clean           # Clean and rebuild documentation
```

### Package Building
```bash
make build                # Build package with UV
make validate-build       # Validate package builds correctly
make clean                # Clean build artifacts
```

## Development Workflow

The project uses UV for dependency management with multiple dependency groups:
- `test`: pytest and testing utilities
- `lint`: black, isort, flake8, pylint, mypy
- `docs`: Sphinx and documentation tools
- `typing`: mypy type checking

Use `uv add <pkg>` to add dependencies and `uv sync --all-groups` to install from lockfile. Avoid using `pip install` directly. Use `uv sync` (not plain `uv sync`) after pinning dependencies to avoid dropping dev groups.

## Code Style

- Formatter: Black with 119 character line length
- Import sorting: isort (configured to be Black-compatible)
- Linting: flake8 + pylint + mypy (all configured in `pyproject.toml`)
- Do not add inline `# noqa` without a specific reason

## Project Overview

A LangGraph demo implementing an **evaluator-assistant loop** pattern (LLM-as-judge). An assistant LLM tries to fulfill user requests using browser tools; a separate evaluator LLM scores each response and routes back to the assistant if the success criteria aren't met. The UI is a Gradio web app supporting multiple concurrent chat sessions.

### Key Files

- [src/langgraph_demo/agent.py](src/langgraph_demo/agent.py) — All graph logic: state, nodes, routers, `AppContext` and `ChatSession` classes.
- [src/langgraph_demo/app.py](src/langgraph_demo/app.py) — Gradio UI and session lifecycle management.
- [src/langgraph_demo/main.py](src/langgraph_demo/main.py) — Entry point (`langgraph-demo` CLI); launches the Gradio app.

### Architecture

#### Multi-session design

- **`AppContext`** — shared per process: playwright instance, browser, assistant LLM, evaluator LLM. Created once via `await AppContext.create()`, closed via `await ctx.close()`.
- **`ChatSession`** — one per browser tab: a dedicated `BrowserContext`, a compiled LangGraph with its own `MemorySaver`, a `thread_id` UUID, and a mutable `success_criteria` string. Created via `await ctx.create_session(thread_id)`, closed via `await session.close()`.
- `app.py` holds the `AppContext` as a lazy singleton (`_APP_CTX`) protected by `asyncio.Lock()`. Each Gradio session holds its `ChatSession` in a `gr.State`.

#### Graph

```
START → assistant → tools (ToolNode) → assistant  (tool-call loop)
              ↓
          evaluator
              ↓
    success/user_input? → END
    else → assistant (retry)
```

- **`State`** (`agent.py`): Pydantic model with `messages`, `success_criteria`, `feedback_on_work`, `success_criteria_met`, `user_input_needed`.
- **assistant node**: Calls `gpt-4o-mini` with Playwright tools bound. Prepends a fresh system message each invocation (includes success criteria and any evaluator feedback).
- **evaluator node**: Calls `gpt-4o-mini` with structured output (`EvaluatorOutput`) to score the assistant's last response.
- **Memory**: `MemorySaver` per session (in-memory, lost on reset or tab close). No SQLite persistence.

#### Tools

- Playwright browser toolkit (webkit, headless) — browser actions scoped to a per-session `BrowserContext`.
- `url_guard` — intercepts all browser requests. Allows `allowed_domains`, silently blocks `blocked_domains`, prompts the user via `input()` for unknown domains. Both sets are module-level and shared across sessions.
- Google Serper search tool (`tool_search`) — defined but not wired into the graph by default.

### Running the App

```bash
langgraph-demo            # launches Gradio on localhost, opens browser
uv run src/langgraph_demo/main.py  # alternative
```

### Required Environment Variables

- `OPENAI_API_KEY` — used by both assistant and evaluator (`gpt-4o-mini`)
- `SERPER_API_KEY` — for Google Serper search (tool defined but not active by default)

`.env` is loaded automatically via `python-dotenv` at module import time.

## Gotchas

- The `assistant` node strips all existing `SystemMessage` objects from history and prepends a fresh one each invocation, so success criteria and feedback changes take effect immediately without clearing the thread.
- `url_guard` uses `input()` — this blocks the async event loop. It works for a local demo but would deadlock a production async server.
- `allowed_domains` and `blocked_domains` in `agent.py` are module-level globals shared across all sessions. Allowing/blocking a domain in one session affects all sessions.
- `compile_graph` must be called per session because `ToolNode` closes over the tool list, which is bound to a specific `BrowserContext`.
- After pinning or changing dependencies, run `uv sync --all-groups` (not plain `uv sync`) to avoid silently dropping dev/lint/test groups.

See @./notes for additional private information
