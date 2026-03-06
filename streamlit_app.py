"""SpirulinaAI — Streamlit chat interface.

Run:
    .venv\\Scripts\\streamlit run streamlit_app.py
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="SpirulinaAI",
    page_icon="🌿",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Custom CSS — spirulina green theme
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* Header accent */
[data-testid="stAppViewContainer"] { background: #f4f7f5; }

/* Chat bubbles — user */
[data-testid="stChatMessageContent"] p { margin: 0; }

/* Intent badge */
.intent-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .5px;
    padding: 2px 8px;
    border-radius: 10px;
    margin-bottom: 6px;
    text-transform: uppercase;
}
.badge-KNOWLEDGE { background: #dbeafe; color: #1e40af; }
.badge-UPDATE    { background: #fef3c7; color: #92400e; }
.badge-HARVEST   { background: #d1fae5; color: #065f46; }
.badge-SYSTEM    { background: #fee2e2; color: #991b1b; }
.badge-UNKNOWN   { background: #f3f4f6; color: #6b7280; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Lazy-load the graph once per session
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading SpirulinaAI...")
def get_graph():
    from agent.graph import graph
    return graph

# ---------------------------------------------------------------------------
# Sidebar — config
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image("https://img.icons8.com/emoji/96/herb-emoji.png", width=64)
    st.title("SpirulinaAI")
    st.caption("Intelligent cultivation assistant")
    st.divider()

    container_id = st.text_input(
        "Container ID",
        placeholder="Leave empty for general Q&A",
        help="Link a container to enable sensor monitoring and ML predictions.",
    )

    st.divider()
    st.caption("**Quick questions:**")
    suggestions = [
        "What is the optimal pH?",
        "My culture is turning yellow",
        "When should I harvest?",
        "How to prevent contamination?",
    ]
    for s in suggestions:
        if st.button(s, use_container_width=True, key=s):
            st.session_state["pending_input"] = s

    st.divider()
    if st.button("Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []   # {role, content, intent, confidence}

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown("## 🌿 SpirulinaAI")
st.caption("Ask me anything about spirulina cultivation.")
st.divider()

# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    role = msg["role"]
    with st.chat_message(role, avatar="🌿" if role == "assistant" else "👤"):
        if role == "assistant" and msg.get("intent"):
            intent = msg["intent"]
            conf   = msg.get("confidence", 0)
            badge  = f'<span class="intent-badge badge-{intent}">{intent}</span>'
            conf_txt = f" &nbsp;·&nbsp; <small style='color:#6b7280'>{conf:.0%} confidence</small>" if conf else ""
            st.markdown(badge + conf_txt, unsafe_allow_html=True)
        st.markdown(msg["content"])

# ---------------------------------------------------------------------------
# Handle suggestion button input
# ---------------------------------------------------------------------------

if "pending_input" in st.session_state:
    pending = st.session_state.pop("pending_input")
    st.session_state["_submit"] = pending

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

user_input = st.chat_input("Ask about your spirulina...")

# Allow both direct input and sidebar suggestion
query = user_input or st.session_state.pop("_submit", None)

if query:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user", avatar="👤"):
        st.markdown(query)

    # Build history for the graph (exclude last user msg — graph adds it)
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
    ]
    history.append({"role": "user", "content": query})

    # Run the graph
    with st.chat_message("assistant", avatar="🌿"):
        with st.spinner(""):
            try:
                result = get_graph().invoke({
                    "user_id":      "streamlit-user",
                    "container_id": container_id,
                    "chat_history": history,
                })
                response   = result.get("response", "Sorry, something went wrong.")
                intent     = result.get("intent", "")
                confidence = result.get("confidence", 0.0)
            except Exception as e:
                response   = f"Error: {e}"
                intent     = ""
                confidence = 0.0

        if intent:
            badge    = f'<span class="intent-badge badge-{intent}">{intent}</span>'
            conf_txt = f" &nbsp;·&nbsp; <small style='color:#6b7280'>{confidence:.0%} confidence</small>" if confidence else ""
            st.markdown(badge + conf_txt, unsafe_allow_html=True)

        st.markdown(response)

    st.session_state.messages.append({
        "role":       "assistant",
        "content":    response,
        "intent":     intent,
        "confidence": confidence,
    })
