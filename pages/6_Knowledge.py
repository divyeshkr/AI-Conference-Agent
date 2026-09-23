"""Manage the internal knowledge base: what the team knew before the conference."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import store
from core.auth import require_access
from core.knowledge import (
    ARCHIVE_EXT,
    chunks_from_file,
    chunks_from_folder,
    seed_demo_knowledge,
)
from core.schema import KnowledgeCategory

st.set_page_config(page_title="Knowledge", page_icon="📚", layout="wide")
require_access()
st.title("Internal knowledge base")
st.caption(
    "Prior debriefs, therapy-area reviews and reference tables. This is what the team "
    "already knew walking in — used to give today's observations context rather than "
    "reporting them in isolation."
)

st.warning(
    "Do not load real client-confidential or proprietary material into a publicly hosted "
    "instance of this app. For demonstrations, use representative or synthetic documents.",
    icon="⚠️",
)

existing = store.load_knowledge()
m1, m2, m3 = st.columns(3)
m1.metric("Knowledge passages", len(existing))
m2.metric("Source documents", len({c.source_file for c in existing}))
m3.metric("Prior conferences", len({c.conference for c in existing if c.conference}))

tab_upload, tab_folder, tab_demo, tab_manage = st.tabs(
    ["Upload documents", "Import a folder", "Demo knowledge", "Manage"]
)

CATEGORY_LABELS = {
    KnowledgeCategory.PRIOR_DEBRIEF: "Prior conference debrief",
    KnowledgeCategory.INTERNAL_REPORT: "Internal report / landscape review",
    KnowledgeCategory.REFERENCE_DATA: "Reference data (assets, competitors, trials)",
    KnowledgeCategory.EXTERNAL: "External publication / press release",
}

# --- upload ------------------------------------------------------------------
with tab_upload:
    st.caption(
        "Parsing only — no model calls, so loading an archive is free and fast. "
        "Images are not accepted here."
    )
    category = st.selectbox(
        "Category",
        list(CATEGORY_LABELS),
        format_func=lambda c: CATEGORY_LABELS[c],
    )
    conference = st.text_input(
        "Originating conference (optional)", placeholder="e.g. Obesity Week 2025"
    )
    uploads = st.file_uploader(
        f"Supported: {', '.join(sorted(e.lstrip('.') for e in ARCHIVE_EXT))}",
        accept_multiple_files=True,
        type=[e.lstrip(".") for e in ARCHIVE_EXT],
    )
    if uploads and st.button("Add to knowledge base", type="primary"):
        total, failures = 0, []
        progress = st.progress(0.0)
        for i, upload in enumerate(uploads, start=1):
            try:
                chunks = chunks_from_file(
                    upload.name, upload.getvalue(), category, conference.strip()
                )
                total += store.save_knowledge(chunks)
                st.write(f"✅ **{upload.name}** — {len(chunks)} passage(s)")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{upload.name}: {exc}")
            progress.progress(i / len(uploads))
        progress.empty()
        st.success(f"Indexed {total} passage(s).")
        for failure in failures:
            st.error(failure)

# --- folder ------------------------------------------------------------------
with tab_folder:
    st.caption(
        "Point at a local archive of prior debriefs and reports. Nothing is uploaded — "
        "the files are read from disk on the machine running the app, which is why this "
        "only works when running locally."
    )
    folder = st.text_input("Folder path", placeholder=r"C:\...\Conference archive")
    recursive = st.checkbox("Include subfolders", value=True)
    if folder and st.button("Import folder"):
        try:
            with st.spinner("Reading archive…"):
                chunks, errors = chunks_from_folder(folder, recursive=recursive)
            saved = store.save_knowledge(chunks)
            st.success(
                f"Indexed {saved} passage(s) from "
                f"{len({c.source_file for c in chunks})} document(s)."
            )
            if errors:
                with st.expander(f"{len(errors)} file(s) could not be read"):
                    for err in errors:
                        st.write(f"- {err}")
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

# --- demo --------------------------------------------------------------------
with tab_demo:
    st.caption(
        "Representative internal knowledge — prior debriefs, a landscape review, payer "
        "research and a competitor tracker — so the capability is demonstrable without "
        "touching real material."
    )
    stem = st.text_input("Conference series", value="Obesity Week")
    if st.button("Load demo knowledge", type="primary"):
        chunks = seed_demo_knowledge(stem.strip() or "Obesity Week")
        store.save_knowledge(chunks)
        st.success(f"Loaded {len(chunks)} knowledge passages.")
        st.rerun()

# --- manage ------------------------------------------------------------------
with tab_manage:
    sources = store.knowledge_sources()
    if not sources:
        st.info("Knowledge base is empty.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Document": s, "Category": CATEGORY_LABELS.get(KnowledgeCategory(c), c),
                     "Passages": n}
                    for s, c, n in sources
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        remove = st.selectbox("Remove a document", [s for s, _, _ in sources])
        c1, c2 = st.columns(2)
        if c1.button("Remove selected"):
            store.delete_knowledge(remove)
            st.rerun()
        if c2.button("Clear entire knowledge base"):
            store.delete_knowledge()
            st.rerun()

    st.divider()
    st.markdown("#### Test retrieval")
    probe = st.text_input("Search the knowledge base", placeholder="payer evidence requirements")
    if probe:
        hits = store.search_knowledge(probe, top_k=5)
        if not hits:
            st.info("No matching passages.")
        for chunk, score in hits:
            with st.container(border=True):
                st.markdown(f"**{chunk.title}**  ·  `{score:.2f}`")
                st.caption(chunk.citation())
                st.write(chunk.text[:600])
