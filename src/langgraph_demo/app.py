import asyncio
import uuid

import gradio as gr
from langgraph_demo.agent import (
    AppContext,
    ChatSession,
)

_APP_CTX: AppContext | None = None
_APP_CTX_LOCK = asyncio.Lock()
_URL_GUARD_ENABLED: bool = True


def configure(url_guard_enabled: bool = True) -> None:
    global _URL_GUARD_ENABLED
    _URL_GUARD_ENABLED = url_guard_enabled


async def get_app_ctx() -> AppContext:
    global _APP_CTX
    async with _APP_CTX_LOCK:
        if _APP_CTX is None:
            _APP_CTX = await AppContext.create(url_guard_enabled=_URL_GUARD_ENABLED)
    return _APP_CTX


async def setup_session() -> ChatSession:
    ctx = await get_app_ctx()
    return await ctx.create_session(str(uuid.uuid4()))


async def reset_session(session_state: ChatSession) -> tuple[str, str, list, ChatSession]:
    if session_state:
        await session_state.close()
    ctx = await get_app_ctx()
    new_session = await ctx.create_session(str(uuid.uuid4()))
    return "", "", [], new_session


def free_session_resources(session_state: ChatSession) -> None:
    if session_state:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(session_state.close())
        except RuntimeError:
            asyncio.run(session_state.close())


def shutdown() -> None:
    global _APP_CTX
    if _APP_CTX:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_APP_CTX.close())
        except RuntimeError:
            asyncio.run(_APP_CTX.close())
        _APP_CTX = None


async def process_message(
    session_state: ChatSession, user_message: str, user_criteria: str, history: list
) -> tuple[list, ChatSession]:
    session_state.success_criteria = user_criteria or "The answer should be clear and accurate"
    assistant_response, evaluator_feedback = await session_state.run_turn(user_message)
    return (
        history
        + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_response},
            {"role": "assistant", "content": evaluator_feedback},
        ],
        session_state,
    )


with gr.Blocks(title="LangGraph Demo", theme=gr.themes.Default(primary_hue="emerald")) as ui:
    gr.Markdown("## LangGraph Demo")
    session = gr.State(delete_callback=free_session_resources)

    with gr.Row():
        chatbot = gr.Chatbot(label="Assistant", height=300, type="messages")
    with gr.Group():
        with gr.Row():
            message = gr.Textbox(show_label=False, placeholder="Your request to the assistant")
        with gr.Row():
            success_criteria = gr.Textbox(show_label=False, placeholder="What are your success criteria?")
    with gr.Row():
        reset_button = gr.Button("Reset", variant="stop")
        go_button = gr.Button("Go!", variant="primary")

    # pylint: disable=no-member
    ui.load(setup_session, [], [session])
    message.submit(
        process_message, [session, message, success_criteria, chatbot], [chatbot, session], concurrency_limit=None
    )
    success_criteria.submit(
        process_message, [session, message, success_criteria, chatbot], [chatbot, session], concurrency_limit=None
    )
    go_button.click(
        process_message, [session, message, success_criteria, chatbot], [chatbot, session], concurrency_limit=None
    )
    reset_button.click(reset_session, [session], [message, success_criteria, chatbot, session])
    ui.unload(shutdown)
