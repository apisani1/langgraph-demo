# LangGraph Demo

A hands-on educational project demonstrating the **evaluator-assistant loop** pattern — also known as *LLM-as-judge* — built with [LangGraph](https://github.com/langchain-ai/langgraph), OpenAI, and a Playwright-powered browser toolkit. The app runs as a Gradio web UI that supports multiple concurrent chat sessions.

## What This Demonstrates

- **LangGraph state graphs** — defining nodes, edges, and conditional routing in a directed graph
- **The evaluator-assistant loop** — an LLM agent that tries to satisfy a user-defined success criterion, with a separate evaluator LLM that scores each response and routes back to the assistant if the criterion is not met
- **Tool use** — the assistant has access to a headless Playwright browser (navigate, click, extract text, and more) to answer questions that require browsing the web
- **Multi-session async architecture** — each browser tab gets its own isolated session with a dedicated browser, LangGraph thread, and conversation history

## How It Works

### The Graph

Each user message triggers one run of the LangGraph. The graph keeps looping until the evaluator approves the response or decides that user input is needed.

```
START → assistant ──────────────────────────────→ evaluator
             ↑          (no tool calls)                ↓
             │                               criteria met or
             └──── tools ←── (tool calls)   user input needed?
                                                  ↓ yes → END
                                                  ↓ no  → assistant (retry)
```

**Nodes:**

| Node | Role |
|---|---|
| `assistant` | Calls `gpt-4o-mini` with Playwright browser tools bound. The system message includes the success criterion and any feedback from the previous evaluator pass. |
| `tools` | LangGraph's built-in `ToolNode` — executes all Playwright tool calls requested by the assistant. |
| `evaluator` | A separate `gpt-4o-mini` call with structured output (`EvaluatorOutput`). Reads the full conversation and scores the assistant's last response against the success criterion. |

**Routing:**

- After `assistant`: tool calls present → `tools`; otherwise → `evaluator`
- After `evaluator`: `success_criteria_met` or `user_input_needed` → `END`; otherwise → `assistant` (retry with evaluator feedback)

### State

The graph carries a `State` Pydantic model through every node:

| Field | Type | Purpose |
|---|---|---|
| `messages` | `list` | Full conversation history, accumulated with LangGraph's `add_messages` reducer |
| `success_criteria` | `str` | The user's criterion for a good answer, set from the UI each turn |
| `feedback_on_work` | `str \| None` | The evaluator's last feedback, injected into the assistant's system message on retry |
| `success_criteria_met` | `bool` | Whether the evaluator approved the last response |
| `user_input_needed` | `bool` | Whether the assistant asked a clarifying question or is stuck |

### Multi-Session Design

The app separates resources into two levels:

- **`AppContext`** (one per process) — Playwright instance and shared LLM clients. Created once on first request, closed when the app shuts down.
- **`ChatSession`** (one per browser tab) — a dedicated headless webkit browser, `BrowserContext`, compiled LangGraph with its own `MemorySaver`, and a UUID `thread_id`. Each session's browser is completely independent, so concurrent sessions can navigate different URLs without interfering.

## Project Structure

```
src/langgraph_demo/
├── agent.py   # Graph definition, AppContext, ChatSession, url_guard
├── app.py     # Gradio UI, session lifecycle, AppContext singleton
└── main.py    # Entry point, CLI arguments, logging setup
```

## Setup

### Prerequisites

- Python 3.10+
- [UV](https://github.com/astral-sh/uv)
- A `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...      # optional — search tool is defined but not wired in by default
```

### Install

```bash
uv sync
uv run playwright install webkit
```

## Running

```bash
langgraph-demo
```

This opens the Gradio UI in your default browser. Each browser tab is an independent chat session with its own conversation history.

**UI fields:**
- *Your request to the assistant* — the task you want the assistant to complete
- *What are your success criteria?* — the condition the evaluator will use to judge responses (e.g. "the answer should include a specific example and be under 200 words")

### CLI Options

| Option | Default | Description |
|---|---|---|
| `--log` | off | Enable debug logging to stderr |
| `--log-file FILE` | — | Log to a file (implies `--log`) |
| `--no-url-guard` | off | Disable URL guard, allow all browser navigation |

### URL Guard

By default, `url_guard` intercepts all browser requests from the assistant. Requests to pre-approved domains (`google.com`, `xe.com`, `wikipedia.org`, `dolarito.ar`) are allowed automatically. For any other domain, the app prompts you in the terminal:

```
The assistant is attempting to access the URL: https://example.com/page
Allow? (y/n):
```

Approving adds the hostname to the allow-list for the rest of the process. Denying adds it to the block-list so the assistant is not prompted again for the same domain. Use `--no-url-guard` to skip all interception.

## Key Concepts to Explore in the Code

| Concept | Where to look |
|---|---|
| Graph definition (nodes, edges, conditional routing) | `compile_graph()` in `agent.py` |
| Evaluator prompt engineering | `EVALUATOR_SYSTEM_MESSAGE` / `EVALUATOR_USER_MESSAGE` in `agent.py` |
| Structured LLM output (Pydantic + `.with_structured_output()`) | `EvaluatorOutput` in `agent.py` |
| LangGraph state and the `add_messages` reducer | `State` class in `agent.py` |
| Per-session browser isolation | `AppContext.create_session()` in `agent.py` |
| Async Gradio multi-session wiring | `app.py` |
