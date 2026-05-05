"""Functional tests for agent.py — AppContext and ChatSession public API."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from playwright.async_api import async_playwright

from langgraph_demo.agent import AppContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evaluator_result(feedback: str = "Looks good", met: bool = True, user_input: bool = False) -> MagicMock:
    return MagicMock(feedback=feedback, success_criteria_met=met, user_input_needed=user_input)


def _assistant_reply(content: str = "Test response") -> AIMessage:
    return AIMessage(content=content)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bound() -> AsyncMock:
    bound = AsyncMock()
    bound.ainvoke.return_value = _assistant_reply()
    return bound


@pytest.fixture
def mock_assistant(mock_bound: AsyncMock) -> MagicMock:
    assistant = MagicMock()
    assistant.bind_tools.return_value = mock_bound
    return assistant


@pytest.fixture
def mock_evaluator() -> AsyncMock:
    evaluator = AsyncMock()
    evaluator.ainvoke.return_value = _evaluator_result()
    return evaluator


@pytest.fixture
async def ctx(mock_assistant: MagicMock, mock_evaluator: AsyncMock):
    playwright = await async_playwright().start()
    context = AppContext(
        playwright=playwright,
        assistant_llm=mock_assistant,
        evaluator_llm_with_output=mock_evaluator,
    )
    yield context
    await context.close()


@pytest.fixture
async def session(ctx: AppContext):
    s = await ctx.create_session(str(uuid.uuid4()))
    yield s
    await s.close()


# ---------------------------------------------------------------------------
# 1. Lifecycle
# ---------------------------------------------------------------------------


async def test_app_context_create_and_close() -> None:
    """AppContext.create() returns a valid context and can be closed cleanly."""
    with patch("langgraph_demo.agent.ChatOpenAI"):
        context = await AppContext.create()
    assert context is not None
    await context.close()


async def test_create_session_returns_a_session(ctx: AppContext) -> None:
    """create_session() returns a ChatSession that can be closed."""
    s = await ctx.create_session(str(uuid.uuid4()))
    assert s is not None
    await s.close()


async def test_two_sessions_have_different_thread_ids(ctx: AppContext) -> None:
    """Each session gets a unique thread ID."""
    s1 = await ctx.create_session(str(uuid.uuid4()))
    s2 = await ctx.create_session(str(uuid.uuid4()))
    try:
        assert s1.thread_id != s2.thread_id
    finally:
        await s1.close()
        await s2.close()


# ---------------------------------------------------------------------------
# 2. Basic conversation turn
# ---------------------------------------------------------------------------


async def test_run_turn_returns_two_strings(session) -> None:
    """run_turn returns a 2-tuple of non-empty strings."""
    result = await session.run_turn("Hello")
    assert isinstance(result, tuple) and len(result) == 2
    response, feedback = result
    assert isinstance(response, str) and response
    assert isinstance(feedback, str) and feedback


async def test_run_turn_first_element_is_assistant_response(session, mock_bound: AsyncMock) -> None:
    """First element of the run_turn tuple is the assistant's answer."""
    mock_bound.ainvoke.return_value = _assistant_reply("Here is my answer")
    response, _ = await session.run_turn("A question")
    assert response == "Here is my answer"


async def test_run_turn_second_element_contains_evaluator_feedback(session, mock_evaluator: AsyncMock) -> None:
    """Second element of the run_turn tuple contains evaluator feedback."""
    mock_evaluator.ainvoke.return_value = _evaluator_result(feedback="Well answered")
    _, feedback = await session.run_turn("A question")
    assert "Well answered" in feedback


# ---------------------------------------------------------------------------
# 3. Evaluator loop routing
# ---------------------------------------------------------------------------


async def test_assistant_called_once_when_criteria_met(session, mock_bound: AsyncMock) -> None:
    """When the evaluator signals success, the assistant is called exactly once."""
    await session.run_turn("A question")
    assert mock_bound.ainvoke.call_count == 1


async def test_assistant_called_twice_when_criteria_not_met_then_met(
    session, mock_bound: AsyncMock, mock_evaluator: AsyncMock
) -> None:
    """When the evaluator signals failure then success, the assistant is called twice."""
    mock_evaluator.ainvoke.side_effect = [
        _evaluator_result(feedback="Not specific enough", met=False),
        _evaluator_result(feedback="Better now", met=True),
    ]
    await session.run_turn("A question")
    assert mock_bound.ainvoke.call_count == 2


async def test_response_after_retry_is_from_second_assistant_call(
    session, mock_bound: AsyncMock, mock_evaluator: AsyncMock
) -> None:
    """After a retry, the returned response is from the second assistant call."""
    mock_bound.ainvoke.side_effect = [
        _assistant_reply("First attempt"),
        _assistant_reply("Improved answer"),
    ]
    mock_evaluator.ainvoke.side_effect = [
        _evaluator_result(feedback="Try again", met=False),
        _evaluator_result(feedback="Good", met=True),
    ]
    response, feedback = await session.run_turn("A question")
    assert response == "Improved answer"
    assert "Good" in feedback


async def test_graph_ends_immediately_when_user_input_needed(
    session, mock_bound: AsyncMock, mock_evaluator: AsyncMock
) -> None:
    """When the evaluator sets user_input_needed, the graph ends without retrying."""
    mock_evaluator.ainvoke.return_value = _evaluator_result(feedback="Please clarify", met=False, user_input=True)
    await session.run_turn("An ambiguous question")
    assert mock_bound.ainvoke.call_count == 1


# ---------------------------------------------------------------------------
# 4. Success criteria
# ---------------------------------------------------------------------------


async def test_run_turn_works_with_default_empty_criteria(session) -> None:
    """run_turn succeeds when success_criteria is the default empty string."""
    assert session.success_criteria == ""
    response, feedback = await session.run_turn("Hello")
    assert response and feedback


async def test_success_criteria_is_passed_to_evaluator(session, mock_evaluator: AsyncMock) -> None:
    """The evaluator receives the session's success_criteria in its prompt."""
    criteria_received: list[bool] = []

    async def capture(messages):
        text = " ".join(str(getattr(m, "content", "")) for m in messages)
        criteria_received.append("answer in one sentence" in text)
        return _evaluator_result()

    mock_evaluator.ainvoke.side_effect = capture
    session.success_criteria = "answer in one sentence"
    await session.run_turn("What is Python?")
    assert any(criteria_received), "Success criteria was not passed to the evaluator"


async def test_updated_criteria_takes_effect_on_next_turn(session, mock_evaluator: AsyncMock) -> None:
    """Changing success_criteria between turns is reflected in the evaluator's prompt."""
    criteria_seen: list[bool] = []

    async def capture(messages):
        text = " ".join(str(getattr(m, "content", "")) for m in messages)
        criteria_seen.append("new_criterion_xyz" in text)
        return _evaluator_result()

    mock_evaluator.ainvoke.side_effect = capture

    session.success_criteria = "old criterion"
    await session.run_turn("Turn one")

    session.success_criteria = "new_criterion_xyz"
    await session.run_turn("Turn two")

    assert not criteria_seen[0], "Old criterion should not contain 'new_criterion_xyz'"
    assert criteria_seen[1], "Updated criterion should appear in turn 2"


# ---------------------------------------------------------------------------
# 5. Multi-turn memory
# ---------------------------------------------------------------------------


async def test_second_turn_receives_first_turn_context(session, mock_bound: AsyncMock) -> None:
    """The assistant receives prior conversation history on subsequent turns."""
    context_seen: list[bool] = []

    async def memory_aware(messages):
        text = " ".join(str(getattr(m, "content", "")) for m in messages)
        context_seen.append("secret_token_abc" in text)
        return _assistant_reply("ok")

    mock_bound.ainvoke.side_effect = memory_aware

    await session.run_turn("Remember: secret_token_abc")
    await session.run_turn("What should you remember?")

    assert len(context_seen) >= 2 and context_seen[-1], "Second turn did not receive first turn's context"


async def test_three_consecutive_turns_all_succeed(session) -> None:
    """Three consecutive run_turn calls all return valid (response, feedback) pairs."""
    for _ in range(3):
        response, feedback = await session.run_turn("Hello")
        assert isinstance(response, str) and response
        assert isinstance(feedback, str) and feedback


# ---------------------------------------------------------------------------
# 6. Session isolation
# ---------------------------------------------------------------------------


async def test_sessions_produce_independent_responses(ctx: AppContext, mock_bound: AsyncMock) -> None:
    """Two sessions with different questions return independent responses."""

    async def question_aware(messages):
        text = " ".join(str(getattr(m, "content", "")) for m in messages)
        if "capital of France" in text:
            return _assistant_reply("Paris")
        if "capital of Germany" in text:
            return _assistant_reply("Berlin")
        return _assistant_reply("Unknown")

    mock_bound.ainvoke.side_effect = question_aware

    s1 = await ctx.create_session(str(uuid.uuid4()))
    s2 = await ctx.create_session(str(uuid.uuid4()))
    try:
        response_a, _ = await s1.run_turn("What is the capital of France?")
        response_b, _ = await s2.run_turn("What is the capital of Germany?")
        assert response_a == "Paris"
        assert response_b == "Berlin"
    finally:
        await s1.close()
        await s2.close()


async def test_session_b_does_not_see_session_a_history(ctx: AppContext, mock_bound: AsyncMock) -> None:
    """Session B's assistant calls do not include Session A's conversation history."""
    s1 = await ctx.create_session(str(uuid.uuid4()))
    s2 = await ctx.create_session(str(uuid.uuid4()))
    try:
        await s1.run_turn("My secret code is 99999")
        s1_call_count = mock_bound.ainvoke.call_count

        await s2.run_turn("What do you know?")

        b_calls = mock_bound.ainvoke.call_args_list[s1_call_count:]
        all_b_content = " ".join(
            str(getattr(m, "content", "")) for call in b_calls for m in call.args[0]
        )
        assert "99999" not in all_b_content, "Session B incorrectly received Session A's history"
    finally:
        await s1.close()
        await s2.close()


# ---------------------------------------------------------------------------
# 7. URL guard
# ---------------------------------------------------------------------------


async def test_url_guard_allows_known_domain() -> None:
    """url_guard allows requests to pre-approved domains without prompting."""
    from langgraph_demo.agent import url_guard

    mock_route = AsyncMock()
    mock_request = MagicMock()
    mock_request.url = "https://google.com/search?q=test"

    await url_guard(mock_route, mock_request)

    mock_route.continue_.assert_awaited_once()
    mock_route.abort.assert_not_awaited()


async def test_url_guard_blocks_previously_blocked_domain() -> None:
    """url_guard aborts requests to domains that have been blocked before."""
    from langgraph_demo.agent import blocked_domains, url_guard

    blocked_domains.add("blocked-test-domain.example")
    try:
        mock_route = AsyncMock()
        mock_request = MagicMock()
        mock_request.url = "https://blocked-test-domain.example/page"

        await url_guard(mock_route, mock_request)

        mock_route.abort.assert_awaited_once()
        mock_route.continue_.assert_not_awaited()
    finally:
        blocked_domains.discard("blocked-test-domain.example")


async def test_url_guard_disabled_does_not_intercept_navigation(
    mock_assistant: MagicMock, mock_evaluator: AsyncMock
) -> None:
    """When url_guard_enabled=False, navigation is not intercepted and run_turn succeeds."""
    playwright = await async_playwright().start()
    ctx_no_guard = AppContext(
        playwright=playwright,
        assistant_llm=mock_assistant,
        evaluator_llm_with_output=mock_evaluator,
        url_guard_enabled=False,
    )
    try:
        s = await ctx_no_guard.create_session(str(uuid.uuid4()))
        response, feedback = await s.run_turn("Hello")
        assert response and feedback
        await s.close()
    finally:
        await ctx_no_guard.close()
