"""Upload conference materials and turn them into Insight Cards."""

from __future__ import annotations

import time
from datetime import date

import streamlit as st

from core import store
from core.auth import require_access
from core.config import get_settings
from core.extract import extract_cards
from core.ingest import SUPPORTED_EXTENSIONS, ingest, save_upload
from core.ui import status_banner

st.set_page_config(page_title="Capture", page_icon="📸", layout="wide")
require_access()
st.title("Capture")
st.caption(
    "Poster photos, slide decks, session PDFs and your notes. Decks are split per "
    "slide and PDFs per page, so every extracted claim traces back to an exact source."
)

settings = get_settings()
status_banner()

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    conference = st.text_input(
        "Conference", value=st.session_state.get("conference", "Obesity Week 2026")
    )
    st.session_state["conference"] = conference
with col2:
    day = st.date_input("Conference day", value=date.today())
with col3:
    as_historical = st.toggle("Prior conference", value=False)

if as_historical:
    st.info(
        "This material will be stored as **historical intelligence**. It stays out of today's "
        "debrief and is used as the baseline the current conference is compared against.",
        icon="🗄️",
    )

tab_files, tab_camera, tab_notes = st.tabs(["Files", "Camera", "Type notes"])

pending: list[tuple[str, bytes]] = []

with tab_files:
    uploads = st.file_uploader(
        f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        accept_multiple_files=True,
        type=SUPPORTED_EXTENSIONS,
    )
    if uploads:
        pending += [(u.name, u.getvalue()) for u in uploads]
        st.success(f"{len(uploads)} file(s) staged.")

with tab_camera:
    st.caption("Shoot a poster or booth panel directly from the floor.")
    shot = st.camera_input("Capture")
    if shot:
        pending.append((f"floor_capture_{int(time.time())}.jpg", shot.getvalue()))

with tab_notes:
    note_title = st.text_input("Note title", value="1:1 discussion notes")
    note_body = st.text_area("Notes", height=220, placeholder="Who you spoke to, what they said…")
    if note_body.strip():
        pending.append((f"{note_title.strip() or 'note'}.txt", note_body.encode()))

st.divider()

if pending:
    st.write(f"**{len(pending)} item(s) ready to process**")
    if st.button("Process and extract", type="primary", use_container_width=True):
        progress = st.progress(0.0, text="Starting…")
        log = st.container()
        started = time.time()
        total_cards = 0
        mock_cards = 0
        failures: list[str] = []

        for i, (name, data) in enumerate(pending, start=1):
            progress.progress((i - 0.5) / len(pending), text=f"Reading {name}…")
            try:
                save_upload(name, data)
                artifacts = ingest(name, data)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{name}: {exc}")
                continue

            made, mocked = 0, 0
            for artifact in artifacts:
                try:
                    cards = extract_cards(artifact, conference, day)
                    store.save_cards(cards, is_historical=as_historical)
                    made += len(cards)
                    for card in cards:
                        if card.is_mock:
                            mocked += 1
                        if card.extraction_error:
                            failures.append(f"{artifact.label()}: {card.extraction_error}")
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{artifact.label()}: {exc}")
            total_cards += made
            mock_cards += mocked
            flag = "  🧪 *placeholder content*" if mocked else ""
            log.write(
                f"{'⚠️' if mocked else '✅'} **{name}** — {len(artifacts)} unit(s) → "
                f"{made} insight card(s){flag}"
            )
            progress.progress(i / len(pending), text=f"{i}/{len(pending)} processed")

        elapsed = time.time() - started
        store.log_event("extraction", f"{len(pending)} files", elapsed)
        progress.empty()

        st.session_state["_live_failures"] = mock_cards if get_settings().is_live else 0

        if mock_cards and get_settings().is_live:
            st.error(
                f"**{mock_cards} of {total_cards} cards are placeholder content.** The "
                f"model call failed for those items, so nothing was actually read from "
                f"your files. See the errors below.",
                icon="🧪",
            )
        elif mock_cards:
            st.warning(
                f"Created {total_cards} **placeholder** cards from {len(pending)} item(s) "
                f"in {elapsed:.1f}s. Your files were not read — this is mock mode.",
                icon="🧪",
            )
        else:
            st.success(
                f"Extracted **{total_cards} insight cards** from {len(pending)} item(s) "
                f"in {elapsed:.1f}s.",
                icon="✅",
            )
        if failures:
            with st.expander(f"{len(failures)} item(s) had issues"):
                for f in failures:
                    st.write(f"- {f}")
        st.page_link("pages/3_Insights.py", label="Review the insight cards →", icon="🗂️")
else:
    st.info("Add files, take a photo, or type notes above to get started.", icon="⬆️")

existing = store.load_cards()
if existing:
    st.divider()
    st.metric("Total insight cards in this workspace", len(existing))
