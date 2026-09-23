"""Provider configuration, client profiles, and the demo dataset loader."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from core import store
from core.auth import require_access
from core.config import PROVIDER_DEFAULTS, PROVIDERS, get_settings, update_settings
from core.llm import health_check
from core.mockdata import _CARDS, historical_cards
from core.schema import CardStatus, ClientProfile, Evidence, InsightCard, SourceType

st.set_page_config(page_title="Setup", page_icon="⚙️", layout="wide")
require_access()
st.title("Setup")

settings = get_settings()

tab_model, tab_clients, tab_demo = st.tabs(
    ["Model provider", "Client profiles", "Demo data"]
)

# --- provider ----------------------------------------------------------------
with tab_model:
    st.caption(
        "The app is fully functional on **mock** with no credentials. Switch to a real "
        "provider when a key is available — nothing else in the app changes."
    )
    if settings.invalid_provider:
        st.error(
            f"`CI_PROVIDER` is set to **{settings.invalid_provider}**, which this build "
            f"does not support. Falling back to mock. Supported: "
            f"{', '.join(PROVIDERS)}. If you expected this provider to work, the deployed "
            f"code is older than your configuration — re-upload `core/config.py`.",
            icon="⚠️",
        )

    c1, c2 = st.columns(2)
    with c1:
        # index() would raise on an unknown value; never let config crash the page.
        try:
            provider_index = PROVIDERS.index(settings.provider)
        except ValueError:
            provider_index = 0
        provider = st.selectbox("Provider", PROVIDERS, index=provider_index)
        api_key = st.text_input("API key", value=settings.api_key, type="password")
        endpoint = st.text_input(
            "Azure endpoint",
            value=settings.endpoint,
            placeholder="https://<resource>.openai.azure.com",
            disabled=provider != "azure",
        )
        base_url = st.text_input(
            "Base URL (OpenAI-compatible hosts)",
            value=settings.base_url,
            placeholder=PROVIDER_DEFAULTS.get(provider, {}).get("base_url", ""),
            disabled=provider in ("azure", "gemini", "mock"),
            help="Leave blank to use the provider default. Set this for Groq, "
            "OpenRouter, Together, a local Ollama, or any other OpenAI-compatible host.",
        )
    with c2:
        text_model = st.text_input(
            "Text model / deployment",
            value=settings.text_model,
            placeholder=PROVIDER_DEFAULTS.get(provider, {}).get("text_model", ""),
        )
        vision_model = st.text_input(
            "Vision model / deployment",
            value=settings.vision_model,
            placeholder=PROVIDER_DEFAULTS.get(provider, {}).get("vision_model", ""),
            help="Must accept image input. On Groq use a Llama 4 Scout or Maverick model.",
        )
        api_version = st.text_input(
            "Azure API version", value=settings.api_version, disabled=provider != "azure"
        )

    col_save, col_defaults = st.columns([1, 1])
    if col_save.button("Save and test", type="primary", use_container_width=True):
        update_settings(
            provider=provider,
            api_key=api_key.strip(),
            endpoint=endpoint.strip(),
            base_url=base_url.strip(),
            text_model=text_model.strip(),
            vision_model=vision_model.strip(),
            api_version=api_version.strip(),
        )
        get_settings().apply_provider_defaults()
        ok, msg = health_check()
        (st.success if ok else st.error)(msg)

    if col_defaults.button(f"Reset models to {provider} defaults", use_container_width=True):
        update_settings(provider=provider, base_url="", text_model="", vision_model="")
        get_settings().apply_provider_defaults()
        st.rerun()

    with st.expander("Persist these settings"):
        st.caption("Locally, put these in `.env`. On Streamlit Cloud use Settings → Secrets.")
        st.code(
            "# Groq — free tier, fast, vision via Llama 4\n"
            "CI_PROVIDER=groq\n"
            "GROQ_API_KEY=gsk_...\n"
            "\n"
            "# IQVIA Azure OpenAI — the production option\n"
            "# CI_PROVIDER=azure\n"
            "# AZURE_OPENAI_API_KEY=...\n"
            "# AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com\n"
            "\n"
            "# Models are optional; provider defaults are used when blank.\n"
            "# CI_TEXT_MODEL=\n"
            "# CI_VISION_MODEL=\n"
            "# CI_BASE_URL=",
            language="bash",
        )

# --- clients -----------------------------------------------------------------
with tab_clients:
    st.caption(
        "The client profile is what makes the same conference produce different "
        "deliverables. It drives relevance ranking, section ordering and the "
        "standing-question section of the debrief."
    )
    existing = store.load_clients()
    names = ["+ New client"] + [c.name for c in existing]
    choice = st.selectbox("Client", names)
    profile = next((c for c in existing if c.name == choice), ClientProfile())

    with st.form("client_form"):
        name = st.text_input("Client name", value=profile.name)
        col1, col2 = st.columns(2)
        with col1:
            areas = st.text_area(
                "Therapeutic areas (one per line)",
                value="\n".join(profile.therapeutic_areas),
                height=110,
            )
            assets = st.text_area(
                "Client's own assets (one per line)",
                value="\n".join(profile.own_assets),
                height=110,
            )
        with col2:
            competitors = st.text_area(
                "Competitors to watch (one per line)",
                value="\n".join(profile.competitors),
                height=110,
            )
            tone = st.text_area("Preferred tone", value=profile.tone, height=110)
        questions = st.text_area(
            "Standing strategic questions (one per line) — answered in every debrief",
            value="\n".join(profile.standing_questions),
            height=140,
        )
        saved = st.form_submit_button("Save client", type="primary")

    if saved:
        if not name.strip():
            st.error("Client name is required.")
        else:
            def _lines(text: str) -> list[str]:
                return [x.strip() for x in text.splitlines() if x.strip()]

            store.save_client(
                ClientProfile(
                    name=name.strip(),
                    therapeutic_areas=_lines(areas),
                    own_assets=_lines(assets),
                    competitors=_lines(competitors),
                    standing_questions=_lines(questions),
                    tone=tone.strip(),
                )
            )
            st.success(f"Saved {name.strip()}.")
            st.rerun()

    if choice != "+ New client" and st.button("Delete this client"):
        store.delete_client(choice)
        st.rerun()

# --- demo data ---------------------------------------------------------------
with tab_demo:
    st.caption(
        "Seeds two contrasting client profiles, a set of current-conference cards and a "
        "prior-year historical set so the 'what changed since last year' view has "
        "something to compare against."
    )

    conference = st.text_input("Conference name", value="Obesity Week 2026")
    day = st.date_input("Conference day", value=date.today())

    if st.button("Load demo dataset", type="primary"):
        store.save_client(
            ClientProfile(
                name="Nordisk Commercial Strategy",
                therapeutic_areas=["Obesity", "Cardiometabolic"],
                own_assets=["CagriSema", "Semaglutide"],
                competitors=["Eli Lilly", "Amgen", "Boehringer Ingelheim"],
                standing_questions=[
                    "How is Lilly positioning retatrutide against our portfolio?",
                    "What is the emerging evidence bar for reimbursement?",
                    "Which competitors are signalling a shift away from weight-loss magnitude?",
                ],
            )
        )
        store.save_client(
            ClientProfile(
                name="Emerging Biotech — Oral GLP-1",
                therapeutic_areas=["Obesity", "Type 2 diabetes"],
                own_assets=["Oral GLP-1 candidate"],
                competitors=["Eli Lilly", "Pfizer", "Structure Therapeutics", "Novo Nordisk"],
                standing_questions=[
                    "What efficacy level do oral GLP-1 competitors now claim?",
                    "Is tolerability still the main barrier for oral agents?",
                    "What are payers signalling about access for new entrants?",
                ],
                tone="Direct and commercially blunt, for a small leadership team.",
            )
        )

        def _to_card(raw: dict, conf: str, d: date, src: str) -> InsightCard:
            return InsightCard(
                conference=conf,
                day=d,
                title=raw["title"],
                company=raw["company"],
                asset=raw["asset"],
                indication=raw["indication"],
                trial_name=raw["trial_name"],
                phase=raw["phase"],
                key_message=raw["key_message"],
                data_points=list(raw["data_points"]),
                competitor_mentions=list(raw["competitor_mentions"]),
                kol_quote=raw["kol_quote"],
                session_name=raw["session_name"],
                themes=list(raw["themes"]),
                confidence=raw["confidence"],
                is_unpublished=raw["is_unpublished"],
                status=CardStatus.APPROVED,
                evidence=Evidence(
                    source_file=src,
                    source_type=SourceType.PHOTO,
                    source_ref="demo",
                    verbatim=raw["key_message"],
                ),
            )

        current = [
            _to_card(raw, conference, day, f"demo_poster_{i+1:02d}.jpg")
            for i, raw in enumerate(_CARDS)
        ]
        store.save_cards(current)

        prior_year = day - timedelta(days=365)
        hist = [
            _to_card(raw, f"{conference.rsplit(' ', 1)[0]} {prior_year.year}", prior_year,
                     f"archive_{i+1:02d}.pdf")
            for i, raw in enumerate(historical_cards())
        ]
        store.save_cards(hist, is_historical=True)

        st.success(
            f"Loaded {len(current)} current cards, {len(hist)} historical cards "
            "and 2 client profiles."
        )

    st.divider()
    col1, col2 = st.columns(2)
    if col1.button("Clear current-conference cards"):
        store.delete_all(include_historical=False)
        st.success("Cleared.")
    if col2.button("Clear everything including history"):
        store.delete_all(include_historical=True)
        st.success("Cleared.")
