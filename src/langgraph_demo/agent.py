import logging
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
)

from pydantic import (
    BaseModel,
    Field,
)

from dotenv import (
    find_dotenv,
    load_dotenv,
)
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import (
    END,
    START,
    StateGraph,
)
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from playwright.async_api import (
    Browser,
    BrowserContext,
    Request,
    Route,
    async_playwright,
)

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    playwright: Any
    assistant_llm: ChatOpenAI
    evaluator_llm_with_output: Any
    url_guard_enabled: bool = True

    @classmethod
    async def create(cls, url_guard_enabled: bool = True) -> "AppContext":
        playwright = await async_playwright().start()
        return cls(
            playwright=playwright,
            assistant_llm=ChatOpenAI(model="gpt-4o-mini"),
            evaluator_llm_with_output=ChatOpenAI(model="gpt-4o-mini").with_structured_output(EvaluatorOutput),
            url_guard_enabled=url_guard_enabled,
        )

    async def close(self) -> None:
        await self.playwright.stop()

    async def create_session(self, thread_id: str) -> "ChatSession":
        browser = await self.playwright.webkit.launch(headless=True)
        browser_context = await browser.new_context()
        if self.url_guard_enabled:
            await browser_context.route("**/*", url_guard)
        await browser_context.new_page()
        toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=browser)
        tools = toolkit.get_tools()
        compiled_graph = compile_graph(tools, self, MemorySaver())
        return ChatSession(
            thread_id=thread_id,
            success_criteria="",
            browser=browser,
            browser_context=browser_context,
            compiled_graph=compiled_graph,
        )


@dataclass
class ChatSession:
    thread_id: str
    success_criteria: str
    browser: Browser
    browser_context: BrowserContext
    compiled_graph: CompiledStateGraph

    async def close(self) -> None:
        await self.browser_context.close()
        await self.browser.close()

    async def run_turn(self, user_message: str) -> tuple[str, str]:
        config = {"configurable": {"thread_id": self.thread_id}}
        state = State(
            messages=[{"role": "user", "content": user_message}],
            success_criteria=self.success_criteria,
            feedback_on_work=None,
            success_criteria_met=False,
            user_input_needed=False,
        )
        result = await self.compiled_graph.ainvoke(state, config=config)  # type: ignore
        return result["messages"][-2].content, result["messages"][-1].content


class EvaluatorOutput(BaseModel):
    feedback: str = Field(description="Feedback on the assistant's response")
    success_criteria_met: bool = Field(description="Whether the success criteria have been met")
    user_input_needed: bool = Field(
        description="True if more input or clarifications are needed from the user or "
        "if the assistant seems to be stuck and unable to meet the success criteria "
        "without more information"
    )


class State(BaseModel):
    messages: Annotated[list, add_messages]
    success_criteria: str
    feedback_on_work: str | None
    success_criteria_met: bool
    user_input_needed: bool


ASSISTANT_SYSTEM_MESSAGE = """
You are a helpful assistant that can use tools to complete tasks.
You keep working on a task until either you have a question or need clarification from the user,
or the success criteria is met. This is the success criteria:

{success_criteria}

You should reply either with a question for the user about this assignment, or with your final response.
If you have a question for the user, you need to reply by clearly stating your question. An example might be:

Question: please clarify whether you want a summary or a detailed answer

If you've finished, reply with the final answer, and don't ask a question; simply reply with the answer.
"""

ASSISTANT_SYSTEM_MESSAGE_EPILOG_ON_FEEDBACK = """
Previously you thought you completed the assignment, but your reply was rejected because
the success criteria was not met. Here is the feedback on why this was rejected:

{feedback_on_work}

With this feedback, please continue the assignment, ensuring that you meet the success criteria or
have a question for the user.
"""

EVALUATOR_SYSTEM_MESSAGE = """
You are an evaluator that determines if a task has been completed successfully by an Assistant.
Assess the Assistant's last response based on the given criteria.
Respond with your feedback, and with your decision on whether the success criteria has been met,
and whether more input is needed from the user.
If the Assistant's response contains a question for the user (it will typically start with "Question:"),
you must set user_input_needed to True, regardless of whether the success criteria has been met.
"""

EVALUATOR_USER_MESSAGE = """
You are evaluating a conversation between the User and Assistant.
You decide what action to take based on the last response from the Assistant.
The entire conversation with the assistant, with the user's original request and all replies, is:

Conversation History:
{conversation_history}

The success criteria for this assignment is:

{success_criteria}

And the final response from the Assistant that you are evaluating is:

{last_response}

Respond with your feedback, and decide if the success criteria is met by this response.
Set user_input_needed to True if ANY of the following apply:
- The Assistant's response contains a question for the user (look for responses starting with "Question:")
- The Assistant needs clarification before it can proceed
- The Assistant appears stuck and unable to make progress without more information
"""

EVALUATOR_USER_MESSAGE_EPILOG_ON_FEEDBACK = """
Also, note that in a prior attempt from the Assistant, you provided this feedback:

{feedback_on_work}

If you're seeing the Assistant repeating the same mistakes, then consider responding that user input is required.
"""


load_dotenv(find_dotenv(), override=True)


def _make_search_tool() -> Tool:
    serper = GoogleSerperAPIWrapper()
    return Tool(
        name="search", func=serper.run, description="Useful for when you need more information from an online search"
    )


allowed_domains: set[str] = {"google.com", "xe.com", "dolarito.ar", "wikipedia.org"}
blocked_domains: set[str] = set()


async def url_guard(route: Route, request: Request) -> None:
    if any(domain in request.url for domain in allowed_domains):
        await route.continue_()
    elif any(domain in request.url for domain in blocked_domains):
        await route.abort()
    else:
        allowed = (
            input(f"\nThe assistant is attempting to access the URL: {request.url}\nAllow? (y/n): ").strip().lower()
        )
        if allowed == "y":
            allowed_domains.add(request.url.split("/")[2])
            await route.continue_()
            return
        blocked_domains.add(request.url.split("/")[2])
        logger.debug("BLOCKED: %s", request.url)
        await route.abort()


def compile_graph(tools: list, ctx: AppContext, checkpointer: Any) -> CompiledStateGraph:
    assistant_llm_with_tools = ctx.assistant_llm.bind_tools(tools)

    async def assistant(state: State) -> dict[str, Any]:
        if logger.isEnabledFor(logging.DEBUG):
            tool_results = []
            for m in reversed(state.messages):
                if isinstance(m, ToolMessage):
                    tool_results.append(m)
                else:
                    break
            for m in reversed(tool_results):
                logger.debug("Tool Result (%s): %s", m.name, m.content)
        system_message = ASSISTANT_SYSTEM_MESSAGE.format(success_criteria=state.success_criteria)
        if state.feedback_on_work:
            system_message += ASSISTANT_SYSTEM_MESSAGE_EPILOG_ON_FEEDBACK.format(
                feedback_on_work=state.feedback_on_work
            )

        messages = [m for m in state.messages if not isinstance(m, SystemMessage)]
        messages = [SystemMessage(content=system_message)] + messages

        response = await assistant_llm_with_tools.ainvoke(messages)
        if response.tool_calls:  # type: ignore
            for tc in response.tool_calls:  # type: ignore
                logger.debug("Tool Call: %s(%s)", tc["name"], tc["args"])
        return {"messages": [response]}

    def assistant_router(state: State) -> str:
        last_message = state.messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "evaluator"

    async def evaluator(state: State) -> State:
        system_message = EVALUATOR_SYSTEM_MESSAGE
        user_message = EVALUATOR_USER_MESSAGE.format(
            conversation_history="\n".join(
                [
                    f"{m.__class__.__name__}: {m.content or 'Tool Use'}"
                    for m in state.messages
                    if not isinstance(m, SystemMessage)
                ]
            ),
            success_criteria=state.success_criteria,
            last_response=state.messages[-1].content,
        )
        if state.feedback_on_work:
            user_message += EVALUATOR_USER_MESSAGE_EPILOG_ON_FEEDBACK.format(feedback_on_work=state.feedback_on_work)

        evaluator_messages = [SystemMessage(content=system_message), HumanMessage(content=user_message)]
        eval_result: EvaluatorOutput = await ctx.evaluator_llm_with_output.ainvoke(evaluator_messages)  # type: ignore

        new_state = State(
            messages=[{"role": "assistant", "content": f"Evaluator Feedback on this answer: {eval_result.feedback}"}],
            success_criteria=state.success_criteria,
            feedback_on_work=eval_result.feedback,
            success_criteria_met=eval_result.success_criteria_met,
            user_input_needed=eval_result.user_input_needed,
        )
        logger.debug("Evaluator Output: %s", new_state)
        return new_state

    def evaluator_router(state: State) -> str:
        if state.success_criteria_met or state.user_input_needed:
            return "END"
        logger.debug("Evaluator: criteria not met, routing back to assistant for another attempt.")
        return "assistant"

    graph_builder = StateGraph(State)
    graph_builder.add_node("assistant", assistant)
    graph_builder.add_node("tools", ToolNode(tools=tools))
    graph_builder.add_node("evaluator", evaluator)
    graph_builder.add_edge(START, "assistant")
    graph_builder.add_conditional_edges("assistant", assistant_router, {"tools": "tools", "evaluator": "evaluator"})
    graph_builder.add_edge("tools", "assistant")
    graph_builder.add_conditional_edges("evaluator", evaluator_router, {"assistant": "assistant", "END": END})
    return graph_builder.compile(checkpointer=checkpointer)
