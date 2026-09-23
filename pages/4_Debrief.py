"""Generate the daily client debrief — the actual deliverable."""

from __future__ import annotations

import time
from datetime import date

import streamlit as st

from core import store
from core.auth import require_access
from core.docx_out import build_docx, build_email
from core.schema import CardStatus
from core.synth import build_debrief, rank_for_client

st.set_page_config(page_title="Debrief", page_icon="📄", layout="wide")
require_access()
st.title("Daily client debrief")
st.caption(
    "Same conference, different clients, different documents. Relevance ranking and "
    "section ordering are driven by the client profile."
)

clients = store.load_clients()
if not clients:
    st.warning("Create a client profile on the **Setup** page first.")
    st.stop()

all_cards = store.load_cards()
if not all_cards:
    st.warning("No insight cards captured yet.")
    st.stop()

conferences = store.conferences() or [""]

c1, c2, c3, c4 = st.columns(4)
with c1:
    client_name = st.selectbox("Client", [c.name for c in clients])
with c2:
    conference = st.selectbox("Conference", conferences)
with c3:
    available_days = store.days(conference) or [date.today()]
    day = st.selectbox("Day", available_days, format_func=lambda d: d.strftime("%a %d %b %Y"))
with c4:
    approved_only = st.toggle("Approved cards only", value=False)

client = next(c for c in clients if c.name == client_name)

statuses = [CardStatus.APPROVED] if approved_only else [CardStatus.DRAFT, CardStatus.APPROVED]
cards = store.load_cards(conference=conference, day=day, statuses=statuses)
historical = store.historical_cards()

st.info(
    f"**{len(cards)}** cards in scope for {client.name} · **{len(historical)}** historical "
    f"cards available for comparison",
    icon="📊",
)

with st.expander("What this client cares about"):
    st.write(client.as_prompt_context())

o1, o2, o3 = st.columns(3)
include_citations = o1.toggle("Include source citations", value=True)
include_appendix = o2.toggle("Include evidence appendix", value=True)
compare_mode = o3.toggle("Compare two clients side by side", value=False)

if st.button("Generate debrief", type="primary", use_container_width=True):
    if not cards:
        st.error("No cards match the selected conference, day and status filter.")
    else:
        started = time.time()
        with st.spinner("Synthesising…"):
            debrief = build_debrief(cards, client, conference, day, historical)
        elapsed = time.time() - started
        store.log_event("debrief", client.name, elapsed)
        st.session_state["debrief"] = debrief
        st.session_state["debrief_cards"] = cards
        st.session_state["debrief_seconds"] = elapsed

        if compare_mode:
            others = [c for c in clients if c.name != client.name]
            if others:
                other = others[0]
                with st.spinner(f"Also generating for {other.name}…"):
                    st.session_state["debrief_b"] = build_debrief(
                        cards, other, conference, day, historical
                    )

debrief = st.session_state.get("debrief")
if not debrief:
    st.stop()

elapsed = st.session_state.get("debrief_seconds", 0.0)
m1, m2, m3 = st.columns(3)
m1.metric("Generated in", f"{elapsed:.1f}s")
m2.metric("Cards synthesised", len(debrief.card_ids))
m3.metric("Manual baseline", "~3–4 hrs", delta="eliminated", delta_color="normal")

st.divider()


def render(d) -> None:
    st.markdown(f"### {d.conference} — {d.day:%A %d %B %Y}")
    st.markdown(f"**Prepared for {d.client}**")
    st.markdown("#### Executive summary")
    st.write(d.executive_summary)
    for section in d.sections:
        st.markdown(f"#### {section.heading}")
        if section.body:
            st.write(section.body)
        for bullet in section.bullets:
            st.markdown(f"- {bullet}")
        if section.citations:
            st.caption("Sources: " + "; ".join(dict.fromkeys(section.citations)))
    if d.question_answers:
        st.markdown("#### Responses to standing questions")
        for item in d.question_answers:
            st.markdown(f"**{item['question']}**")
            st.write(item["answer"])
            if item.get("citations"):
                st.caption("Sources: " + "; ".join(dict.fromkeys(item["citations"])))
    if d.watchlist:
        st.markdown("#### Watchlist for tomorrow")
        for item in d.watchlist:
            st.markdown(f"- {item}")


debrief_b = st.session_state.get("debrief_b") if compare_mode else None
if debrief_b:
    st.caption(
        "Identical source material, two clients. This is the repackaging problem the "
        "brief calls out, solved."
    )
    left, right = st.columns(2)
    with left:
        render(debrief)
    with right:
        render(debrief_b)
else:
    tab_doc, tab_email, tab_relevance = st.tabs(["Debrief", "Email draft", "Relevance ranking"])
    with tab_doc:
        render(debrief)
    with tab_email:
        st.code(build_email(debrief), language=None)
    with tab_relevance:
        st.caption("Why each card surfaced where it did for this client.")
        for card, score in rank_for_client(st.session_state["debrief_cards"], client)[:15]:
            st.markdown(
                f"`{score:>5.2f}` · **{card.company or '—'}** — {card.title} "
                f"<span class='ci-src'>{card.citation()}</span>",
                unsafe_allow_html=True,
            )

st.divider()
d1, d2 = st.columns(2)
with d1:
    if st.button("Build Word document", use_container_width=True, type="primary"):
        path = build_docx(
            debrief,
            st.session_state["debrief_cards"],
            include_citations=include_citations,
            include_appendix=include_appendix,
        )
        st.session_state["docx_path"] = str(path)
    if st.session_state.get("docx_path"):
        path = st.session_state["docx_path"]
        with open(path, "rb") as fh:
            st.download_button(
                "Download .docx",
                fh.read(),
                file_name=path.split("\\")[-1].split("/")[-1],
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
with d2:
    st.download_button(
        "Download email draft (.txt)",
        build_email(debrief),
        file_name=f"{debrief.client}_{debrief.day:%Y%m%d}_email.txt",
        use_container_width=True,
    )
