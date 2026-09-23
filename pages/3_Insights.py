"""Review, filter, edit and approve extracted intelligence before it reaches a client."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core import store
from core.auth import require_access
from core.schema import CardStatus

st.set_page_config(page_title="Insights", page_icon="🗂️", layout="wide")
require_access()
st.title("Insight feed")
st.caption(
    "Nothing reaches a client deliverable without a human pass. Edit any field, then "
    "approve or reject."
)

cards = store.load_cards()
if not cards:
    st.info("No cards yet. Go to **Capture** to upload material, or load the demo dataset on **Setup**.")
    st.stop()

# --- filters -----------------------------------------------------------------
f1, f2, f3, f4 = st.columns(4)
companies = sorted({c.company for c in cards if c.company})
indications = sorted({c.indication for c in cards if c.indication})

with f1:
    pick_company = st.multiselect("Company", companies)
with f2:
    pick_indication = st.multiselect("Indication", indications)
with f3:
    pick_status = st.multiselect(
        "Status", [s.value for s in CardStatus], default=["draft", "approved"]
    )
with f4:
    query = st.text_input("Search", placeholder="asset, trial, keyword…")

filtered = [
    c
    for c in cards
    if (not pick_company or c.company in pick_company)
    and (not pick_indication or c.indication in pick_indication)
    and (not pick_status or c.status.value in pick_status)
    and (not query or query.lower() in c.search_text().lower())
]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Showing", f"{len(filtered)} / {len(cards)}")
m2.metric("Approved", sum(1 for c in filtered if c.status == CardStatus.APPROVED))
m3.metric("Unpublished", sum(1 for c in filtered if c.is_unpublished))
m4.metric("Avg confidence", f"{(sum(c.confidence for c in filtered) / len(filtered)):.0%}" if filtered else "—")

bulk1, bulk2, _ = st.columns([1, 1, 3])
if bulk1.button("Approve all shown", use_container_width=True):
    for c in filtered:
        store.set_status(c.id, CardStatus.APPROVED)
    st.rerun()
if bulk2.button("Reset all to draft", use_container_width=True):
    for c in filtered:
        store.set_status(c.id, CardStatus.DRAFT)
    st.rerun()

view = st.radio("View", ["Cards", "Table"], horizontal=True, label_visibility="collapsed")

if view == "Table":
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Company": c.company,
                    "Asset": c.asset,
                    "Indication": c.indication,
                    "Trial": c.trial_name,
                    "Phase": c.phase,
                    "Key message": c.key_message,
                    "Data points": len(c.data_points),
                    "Confidence": c.confidence,
                    "Unpublished": c.is_unpublished,
                    "Status": c.status.value,
                    "Source": c.citation(),
                }
                for c in filtered
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.stop()

st.divider()

for card in filtered:
    chips = "".join(
        f'<span class="ci-chip">{x}</span>'
        for x in [card.company, card.asset, card.indication, card.phase]
        if x
    )
    if card.is_unpublished:
        chips += '<span class="ci-chip ci-chip-warn">UNPUBLISHED</span>'
    if card.status == CardStatus.APPROVED:
        chips += '<span class="ci-chip">✓ APPROVED</span>'

    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            st.markdown(f"**{card.title or '(untitled)'}**")
            st.markdown(chips, unsafe_allow_html=True)
            if card.key_message:
                st.write(card.key_message)
            for dp in card.data_points:
                st.markdown(f"- {dp}")
            if card.kol_quote:
                st.markdown(f"> _{card.kol_quote}_")
            st.markdown(
                f'<span class="ci-src">{card.citation()} · confidence {card.confidence:.0%}'
                f' · id {card.id}</span>',
                unsafe_allow_html=True,
            )
        with right:
            thumb = card.evidence.thumbnail_path
            if thumb and Path(thumb).exists():
                st.image(thumb, use_container_width=True)
            b1, b2 = st.columns(2)
            if b1.button("Approve", key=f"ok_{card.id}", use_container_width=True):
                store.set_status(card.id, CardStatus.APPROVED)
                st.rerun()
            if b2.button("Reject", key=f"no_{card.id}", use_container_width=True):
                store.set_status(card.id, CardStatus.REJECTED)
                st.rerun()

        with st.expander("Edit / view source"):
            with st.form(f"edit_{card.id}"):
                e1, e2, e3 = st.columns(3)
                company = e1.text_input("Company", card.company, key=f"co_{card.id}")
                asset = e2.text_input("Asset", card.asset, key=f"as_{card.id}")
                indication = e3.text_input("Indication", card.indication, key=f"in_{card.id}")
                title = st.text_input("Title", card.title, key=f"ti_{card.id}")
                message = st.text_area("Key message", card.key_message, key=f"km_{card.id}")
                data_points = st.text_area(
                    "Data points (one per line)",
                    "\n".join(card.data_points),
                    key=f"dp_{card.id}",
                )
                unpublished = st.checkbox(
                    "Unpublished / not in public domain", card.is_unpublished, key=f"up_{card.id}"
                )
                if st.form_submit_button("Save changes"):
                    card.company = company
                    card.asset = asset
                    card.indication = indication
                    card.title = title
                    card.key_message = message
                    card.data_points = [d.strip() for d in data_points.splitlines() if d.strip()]
                    card.is_unpublished = unpublished
                    store.update_card(card)
                    st.rerun()
            if card.evidence.verbatim:
                st.markdown("**Source text**")
                st.code(card.evidence.verbatim, language=None)
