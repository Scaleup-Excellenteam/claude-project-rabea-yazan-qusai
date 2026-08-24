"""
Owner: Person 3

Purpose:
Streamlit Hebrew/RTL chat UI entry point.
"""

import streamlit as st

from agent.ui import REFUSAL_TEXT, run_agent_for_ui


def _configure_page():
    st.set_page_config(
        page_title="יועץ לימודים - מדעי המחשב",
        layout="centered",
    )
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            direction: rtl;
        }
        .stChatMessage {
            direction: rtl;
            text-align: right;
        }
        [data-testid="stChatInput"] textarea {
            direction: rtl;
            text-align: right;
        }
        .source-list {
            margin-top: 0.75rem;
            padding: 0.65rem 0.85rem;
            border-right: 3px solid #2b6cb0;
            background: #f7fafc;
            border-radius: 6px;
        }
        .status-note {
            padding: 0.65rem 0.85rem;
            border-right: 3px solid #718096;
            background: #f7fafc;
            border-radius: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _initial_messages():
    return [
        {
            "role": "assistant",
            "display": {
                "kind": "intro",
                "body": (
                    "שלום. אפשר לשאול בעברית על דרישות התואר במדעי המחשב "
                    "ותקנון התואר הראשון. התשובות יוצגו רק כאשר יש להן מקור במסמכים."
                ),
                "citations": [],
                "options": [],
                "debug": {},
            },
        }
    ]


def _render_citations(citations):
    if not citations:
        return
    st.markdown('<div class="source-list"><strong>מקורות:</strong></div>', unsafe_allow_html=True)
    for citation in citations:
        st.markdown(f"- {citation}")


def _render_debug(debug):
    if not debug:
        return
    with st.expander("פרטים טכניים", expanded=False):
        metrics = debug.get("metrics") or {}
        if metrics:
            cols = st.columns(3)
            cols[0].metric("קריאות כלים", metrics.get("tool_call_count", 0))
            cols[1].metric("איטרציות", metrics.get("iterations", 0))
            cols[2].metric("סטטוס", metrics.get("outcome", debug.get("status", "")))
        st.json(
            {
                "status": debug.get("status"),
                "metrics": metrics,
                "tool_trace": debug.get("tool_trace", []),
            },
            expanded=False,
        )


def _render_display(display):
    kind = display.get("kind")
    body = display.get("body") or ""

    if kind == "technical_error":
        st.error(f"{display.get('title', 'שגיאה טכנית')}: {body}")
    elif kind in {"max_iterations", "no_grounded_answer"}:
        st.warning(body)
    elif kind == "missing_information":
        st.markdown(f"**{REFUSAL_TEXT}**")
    elif kind == "clarification":
        st.info(body)
        options = display.get("options") or []
        if options:
            st.markdown("אפשרויות:")
            for option in options:
                st.markdown(f"- `{option}`")
    else:
        st.markdown(body)

    _render_citations(display.get("citations") or [])
    _render_debug(display.get("debug") or {})


def main():
    _configure_page()

    st.title("יועץ לימודים - מדעי המחשב")
    st.caption("ממשק מקומי בלבד. אין שימוש במידע מחוץ למסמכי המקור.")

    if "messages" not in st.session_state:
        st.session_state.messages = _initial_messages()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "content" in message:
                st.markdown(message["content"])
            else:
                _render_display(message["display"])

    question = st.chat_input("כתבו שאלה על תוכנית הלימודים או התקנון")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("בודק במסמכים..."):
            display = run_agent_for_ui(question)
        _render_display(display)

    st.session_state.messages.append({"role": "assistant", "display": display})


if __name__ == "__main__":
    main()
