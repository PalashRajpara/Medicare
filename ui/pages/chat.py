"""Main MediCare Chat interface with real-time multi-agent execution streaming."""

import os
import time

import streamlit as st

from ui.client import MediCareClient
from ui.components.answer import render_assistant_answer
from ui.components.banners import (
    render_ai_offline_notice,
    render_backend_offline_banner,
)
from ui.components.stepper import StepperManager
from ui.components.suggestions import render_empty_state
from ui.config import get_app_config, get_messages_config
from ui.state import (
    append_message,
    clear_cancel_request,
    get_active_agent,
    get_active_model,
    get_document_scope,
    get_messages,
    get_selected_prompt,
    get_show_trace,
    get_stream_tokens,
    get_thread_id,
    get_user_id,
    is_cancel_requested,
    is_generating,
    request_cancel,
    set_generating,
    set_last_run_id,
    set_messages,
    set_selected_prompt,
)

# 1. Config & Client Setup
cfg = get_app_config()
messages_cfg = get_messages_config()
ui_cfg = cfg.get("ui", {})
backend_url = os.getenv("BACKEND_SERVICE_URL") or ui_cfg.get("backend_service_url", "")
secret_token = os.getenv("SERVICE_SECRET_KEY", None)
client = MediCareClient(base_url=backend_url, secret_token=secret_token)

# 2. Main Screen Brand Header
app_heading = (
    ui_cfg.get("app_heading")
    or messages_cfg.get("welcome_title")
    or cfg.get("app_name")
    or "MediCare"
)
app_tagline = messages_cfg.get("app_tagline") or ui_cfg.get("app_tagline") or cfg.get("tagline", "")
if app_heading and app_tagline:
    st.markdown(f"## 🏥 {app_heading} — *{app_tagline}*")
elif app_heading:
    st.markdown(f"## 🏥 {app_heading}")

# 3. Backend Reachability Probe
backend_alive = client.check_health()
if not backend_alive:
    render_backend_offline_banner(on_retry=lambda: None)

# Check if AI mode is mock or offline
try:
    if backend_alive:
        status_data = client.get_medicare_status()
        if status_data.get("mode") == "fallback":
            render_ai_offline_notice()
except Exception:
    pass


# Helper to handle prompt selection
def on_select_prompt(prompt_text: str) -> None:
    set_selected_prompt(prompt_text)
    st.rerun()


def regenerate_last() -> None:
    msgs = get_messages()
    if msgs and msgs[-1].get("type") in ("ai", "assistant"):
        msgs.pop()
        # Find previous human message
        last_human = ""
        for m in reversed(msgs):
            if m.get("type") in ("human", "user"):
                last_human = m.get("content", "")
                break
        if last_human:
            msgs.pop()  # remove human message too, as it will be re-submitted
            set_messages(msgs)
            set_selected_prompt(last_human)
            st.rerun()


# 4. Empty State or Message History
messages = get_messages()
active_prompt = get_selected_prompt()

if not messages and not active_prompt:
    dynamic_suggestions = []
    if backend_alive:
        try:
            dynamic_suggestions = client.get_medicare_suggestions(user_id=get_user_id())
        except Exception:
            dynamic_suggestions = []

    render_empty_state(on_select=on_select_prompt, suggestions=dynamic_suggestions)
else:
    # Render existing conversation messages
    for idx, msg in enumerate(messages):
        msg_type = msg.get("type") or msg.get("role")
        if msg_type in ("human", "user"):
            with st.chat_message("user"):
                st.markdown(msg.get("content", ""))
        else:
            with st.chat_message("assistant"):
                is_latest = idx == len(messages) - 1
                render_assistant_answer(
                    message=msg,
                    client=client,
                    show_trace=get_show_trace(),
                    is_latest=is_latest,
                    on_regenerate=regenerate_last,
                    on_followup_select=on_select_prompt,
                    key_prefix=f"m_{idx}",
                )

# 5. Stop Button when Run is Active
generating = is_generating()
if generating:
    stop_label = messages_cfg.get("stop_generation_label") or ui_cfg.get(
        "stop_generation_label", "Stop"
    )
    if st.button(f"⏹️ {stop_label}", key="stop_stream_btn", width="content"):
        request_cancel()

# 6. Chat Input
max_chars = ui_cfg.get("max_message_length", 2000)
placeholder = messages_cfg.get("input_placeholder") or ui_cfg.get(
    "input_placeholder", "Ask about costs, wait times, claims..."
)

user_input = st.chat_input(
    placeholder=placeholder,
    max_chars=max_chars,
    disabled=generating or not backend_alive,
    key="chat_user_input",
)

# Determine prompt to run
submitted_prompt = None
if active_prompt:
    submitted_prompt = active_prompt
    set_selected_prompt(None)
elif user_input and user_input.strip():
    submitted_prompt = user_input.strip()

# 7. Execution Run Streaming
if submitted_prompt:
    clear_cancel_request()
    set_generating(True)

    # Append and render user message
    user_msg = {"type": "human", "content": submitted_prompt}
    append_message(user_msg)
    with st.chat_message("user"):
        st.markdown(submitted_prompt)

    # Stream assistant response
    with st.chat_message("assistant"):
        analyzing_label = messages_cfg.get(
            "chat_analyzing_request", "Analyzing healthcare request..."
        )
        stepper_box = st.status(analyzing_label, expanded=True)
        stepper = StepperManager(stepper_box)
        token_placeholder = st.empty()

        accumulated_text = ""
        final_message_data: dict | None = None
        start_time = time.time()

        try:
            stream_gen = client.stream(
                agent_id=get_active_agent(),
                message=submitted_prompt,
                thread_id=get_thread_id(),
                user_id=get_user_id(),
                model=get_active_model(),
                stream_tokens=get_stream_tokens(),
                doc_scope=get_document_scope(),
                is_cancelled=is_cancel_requested,
            )

            for event in stream_gen:
                if is_cancel_requested():
                    break

                ev_type = event.get("type")
                if ev_type == "token":
                    token = event.get("content", "")
                    accumulated_text += token
                    token_placeholder.markdown(accumulated_text + "▌")
                elif ev_type == "agent_status":
                    status_content = event.get("content", {})
                    stepper.on_event(status_content)
                elif ev_type == "message":
                    final_message_data = event.get("content", {})
                elif ev_type == "error":
                    exec_err_msg = messages_cfg.get(
                        "chat_execution_error", "Execution encountered an error"
                    )
                    unknown_err_msg = messages_cfg.get("chat_unknown_error", "Unknown error")
                    stepper.error(exec_err_msg)
                    st.error(event.get("content", unknown_err_msg))
                    break

            # Handle cancellation or finish
            if is_cancel_requested():
                cancel_msg = messages_cfg.get(
                    "chat_execution_cancelled", "Execution cancelled by user"
                )
                stopped_suffix = messages_cfg.get(
                    "chat_generation_stopped", "\n\n*(Generation stopped by user)*"
                )
                stepper.error(cancel_msg)
                accumulated_text += stopped_suffix
                token_placeholder.markdown(accumulated_text)
                ai_record = {
                    "type": "ai",
                    "content": accumulated_text,
                    "response_metadata": {"medicare": {}},
                }
                append_message(ai_record)
            elif final_message_data:
                stepper.complete()
                content = final_message_data.get("content", accumulated_text)
                token_placeholder.markdown(content)
                append_message(final_message_data)
                set_last_run_id(final_message_data.get("run_id"))
            else:
                stepper.complete()
                token_placeholder.markdown(accumulated_text)
                ai_record = {
                    "type": "ai",
                    "content": accumulated_text,
                    "response_metadata": {"medicare": {}},
                }
                append_message(ai_record)

        except Exception as e:
            err_prefix = messages_cfg.get("error_prefix", "Error")
            stepper.error(f"{err_prefix}: {e}")
            if accumulated_text:
                interrupted_tmpl = messages_cfg.get(
                    "chat_response_interrupted", "\n\n*(Response was interrupted: {error})*"
                )
                accumulated_text += interrupted_tmpl.format(error=e)
                token_placeholder.markdown(accumulated_text)
                append_message(
                    {
                        "type": "ai",
                        "content": accumulated_text,
                        "response_metadata": {"medicare": {}},
                    }
                )
            else:
                gen_err_tmpl = messages_cfg.get(
                    "chat_generation_error",
                    "⚠️ **Could not generate response:** {error}\n\nPlease verify that the MediCare backend service is running and model configuration is valid.",
                )
                err_text = gen_err_tmpl.format(error=e)
                token_placeholder.markdown(err_text)
                append_message(
                    {
                        "type": "ai",
                        "content": err_text,
                        "response_metadata": {"medicare": {}},
                    }
                )

        finally:
            set_generating(False)
            clear_cancel_request()
            st.rerun()
