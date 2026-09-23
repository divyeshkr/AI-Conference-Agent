"""Ask questions of everything captured at the conference, with sources shown."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import store
from core.auth import require_access
from core.synth import answer_question

st.set_page_config(page_title="Ask", page_icon="💬", layout="wide")
require_access()
st.title("Ask the conference")
st.caption(
    "Every answer is grounded in captured material and shows the exact poster, slide "
    "or note it came from."
)

all_cards = store.load_cards()
historical = store.historical_cards()
if not all_cards:
    st.info("Nothing captured yet. Upload material on **Capture** or load the demo dataset on **Setup**.")
    st.stop()

col_scope, col_kb = st.columns([2, 1])
with col_scope:
    scope = st.radio(
        "Scope",
        ["This conference", "Include historical intelligence"],
        horizontal=True,
    )
with col_kb:
    use_knowledge = st.toggle("Use internal knowledge base", value=True)

cards = all_cards + historical if scope.startswith("Include") else all_cards
kb_size = len(store.load_knowledge()) if use_knowledge else 0

st.caption(
    f"Searching {len(cards)} insight cards"
    + (f" and {kb_size} internal knowledge passages." if use_knowledge else ".")
)

SUGGESTIONS = [
    "What did Lilly present on retatrutide and how does it compare to CagriSema?",
    "What are payers signalling about obesity reimbursement?",
    "Which companies are shifting away from weight-loss magnitude as their message?",
    "What unpublished intelligence did we pick up today?",
]

cols = st.columns(len(SUGGESTIONS))
asked = None
for col, suggestion in zip(cols, SUGGESTIONS):
    if col.button(suggestion, use_container_width=True):
        asked = suggestion

st.session_state.setdefault("chat", [])

typed = st.chat_input("Ask about anything captured at this conference…")
question = typed or asked

for turn in st.session_state["chat"]:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        for card in turn.get("sources", []):
            with st.expander(f"📎 {card.citation()} — {card.title}"):
                s1, s2 = st.columns([2, 1])
                with s1:
                    st.write(card.key_message)
                    for dp in card.data_points:
                        st.markdown(f"- {dp}")
                    st.caption(f"id {card.id} · confidence {card.confidence:.0%}")
                with s2:
                    thumb = card.evidence.thumbnail_path
                    if thumb and Path(thumb).exists():
                        st.image(thumb, use_container_width=True)

if question:
    st.session_state["chat"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Searching captured intelligence…"):
            answer, sources, knowledge = answer_question(
                question, cards, use_knowledge=use_knowledge
            )
        st.markdown(answer)
        for chunk in knowledge:
            with st.expander(f"📚 {chunk.title} — {chunk.citation()}"):
                st.caption(f"Existing internal knowledge · {chunk.category.value}")
                st.write(chunk.text[:900])
        for card in sources:
            with st.expander(f"📎 {card.citation()} — {card.title}"):
                s1, s2 = st.columns([2, 1])
                with s1:
                    st.write(card.key_message)
                    for dp in card.data_points:
                        st.markdown(f"- {dp}")
                    st.caption(f"id {card.id} · confidence {card.confidence:.0%}")
                with s2:
                    thumb = card.evidence.thumbnail_path
                    if thumb and Path(thumb).exists():
                        st.image(thumb, use_container_width=True)
    st.session_state["chat"].append(
        {"role": "assistant", "content": answer, "sources": sources}
    )

if st.session_state["chat"] and st.button("Clear conversation"):
    st.session_state["chat"] = []
    st.rerun()
