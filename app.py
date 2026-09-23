"""Conference Intelligence Assistant — Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from core import store
from core.auth import require_access
from core.config import get_settings
from core.llm import health_check

st.set_page_config(
    page_title="Conference Intelligence Assistant",
    page_icon="🎤",
    layout="wide",
    initial_sidebar_state="expanded",
)

STYLE = """
<style>
  .block-container {padding-top: 2.2rem; max-width: 1280px;}
  .ci-hero {background: linear-gradient(120deg, #003087 0%, #0b5fd0 100%);
            color: #fff; padding: 1.6rem 1.9rem; border-radius: 12px; margin-bottom: 1.4rem;}
  .ci-hero h1 {margin: 0; font-size: 1.85rem; font-weight: 700;}
  .ci-hero p {margin: .45rem 0 0; opacity: .92; font-size: .97rem;}
  .ci-card {border: 1px solid #e3e6ec; border-left: 4px solid #003087;
            border-radius: 8px; padding: .9rem 1.1rem; margin-bottom: .75rem; background: #fff;}
  .ci-chip {display: inline-block; background: #eef2fa; color: #003087;
            border-radius: 20px; padding: .12rem .62rem; font-size: .74rem;
            margin-right: .32rem; font-weight: 600;}
  .ci-chip-warn {background: #fdf1e0; color: #a35b00;}
  .ci-src {color: #6b7280; font-size: .76rem; font-style: italic;}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)
require_access()


def sidebar_status() -> None:
    s = get_settings()
    with st.sidebar:
        st.markdown("### Status")
        if s.provider == "mock":
            st.warning("Mock mode — no API calls", icon="🧪")
        else:
            st.success(f"{s.provider} · {s.vision_model}", icon="🔌")
        cards = store.load_cards()
        st.metric("Insight cards captured", len(cards))
        st.metric("Client profiles", len(store.load_clients()))
        if st.button("Test connection", use_container_width=True):
            ok, msg = health_check()
            (st.success if ok else st.error)(msg)
        st.caption("Pages are in the sidebar above. Start at Setup.")


st.markdown(
    """
<div class="ci-hero">
  <h1>Conference Intelligence Assistant</h1>
  <p>Capture on the floor. Debrief in minutes, not at midnight.</p>
</div>
""",
    unsafe_allow_html=True,
)

sidebar_status()

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("#### 1 · Capture")
    st.write(
        "Upload poster photos, slide decks, session PDFs and your 1:1 notes. "
        "A vision model reads the images directly, so dense poster layouts and "
        "chart labels survive intact."
    )
with col2:
    st.markdown("#### 2 · Structure")
    st.write(
        "Everything becomes an **Insight Card** — company, asset, indication, trial, "
        "data points, key message, source. You review and approve before anything "
        "reaches a client."
    )
with col3:
    st.markdown("#### 3 · Deliver")
    st.write(
        "Generate a client-tailored Word debrief, an email draft, and answers to "
        "the client's standing questions. Same conference, different clients, "
        "different documents."
    )

st.divider()

cards = store.load_cards()
clients = store.load_clients()

if not clients:
    st.info(
        "No client profiles yet. Open **Setup** in the sidebar to create one and to "
        "load the demo dataset — the app works fully without an API key.",
        icon="👋",
    )
elif not cards:
    st.info("Client profiles are ready. Go to **Capture** to upload conference materials.", icon="📸")
else:
    approved = sum(1 for c in cards if c.status.value == "approved")
    a, b, c_, d = st.columns(4)
    a.metric("Insight cards", len(cards))
    b.metric("Approved", approved)
    c_.metric("Companies tracked", len({x.company for x in cards if x.company}))
    d.metric("Unpublished flags", sum(1 for x in cards if x.is_unpublished))
    st.success("Ready to generate a debrief — open **Debrief** in the sidebar.", icon="✅")
