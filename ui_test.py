"""Headless render check for every page, using Streamlit's own test harness.

Catches exceptions in page code without needing a browser.
Run: .venv\\Scripts\\python.exe ui_test.py
"""

from __future__ import annotations

import sys
from datetime import date

from streamlit.testing.v1 import AppTest

from core import store
from core.knowledge import seed_demo_knowledge
from core.mockdata import _CARDS, historical_cards
from core.schema import CardStatus, ClientProfile, Evidence, InsightCard, SourceType

PAGES = [
    "app.py",
    "pages/1_Setup.py",
    "pages/2_Capture.py",
    "pages/3_Insights.py",
    "pages/4_Debrief.py",
    "pages/5_Ask.py",
    "pages/6_Knowledge.py",
]


def seed() -> None:
    """Populate the store so pages render their populated state, not just empty states."""
    store.delete_all(include_historical=True)
    store.save_client(
        ClientProfile(
            name="Nordisk Commercial Strategy",
            therapeutic_areas=["Obesity"],
            own_assets=["CagriSema"],
            competitors=["Eli Lilly", "Amgen"],
            standing_questions=["How is Lilly positioning retatrutide?"],
        )
    )

    def to_card(raw: dict, conf: str, day: date, src: str) -> InsightCard:
        return InsightCard(
            conference=conf, day=day, title=raw["title"], company=raw["company"],
            asset=raw["asset"], indication=raw["indication"], trial_name=raw["trial_name"],
            phase=raw["phase"], key_message=raw["key_message"],
            data_points=list(raw["data_points"]),
            competitor_mentions=list(raw["competitor_mentions"]),
            kol_quote=raw["kol_quote"], session_name=raw["session_name"],
            themes=list(raw["themes"]), confidence=raw["confidence"],
            is_unpublished=raw["is_unpublished"], status=CardStatus.APPROVED,
            evidence=Evidence(source_file=src, source_type=SourceType.PHOTO, source_ref="demo"),
        )

    store.save_cards(
        [to_card(r, "Obesity Week 2026", date.today(), f"p{i}.jpg") for i, r in enumerate(_CARDS)]
    )
    store.save_cards(
        [to_card(r, "Obesity Week 2025", date(2025, 11, 3), f"a{i}.pdf")
         for i, r in enumerate(historical_cards())],
        is_historical=True,
    )
    store.delete_knowledge()
    store.save_knowledge(seed_demo_knowledge())


def main() -> int:
    seed()
    failures = 0
    for page in PAGES:
        try:
            at = AppTest.from_file(page, default_timeout=90).run()
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {page:<22} harness error: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        if at.exception:
            for exc in at.exception:
                print(f"FAIL  {page:<22} {exc.type}: {exc.message}")
            failures += 1
        else:
            widgets = (
                len(at.button) + len(at.text_input) + len(at.selectbox)
                + len(at.multiselect) + len(at.text_area)
            )
            print(
                f"OK    {page:<22} {len(at.markdown)} markdown, {len(at.metric)} metric, "
                f"{widgets} widgets"
            )

    store.delete_all(include_historical=True)
    store.delete_knowledge()
    print("\n" + ("ALL PAGES RENDER" if not failures else f"{failures} PAGE(S) FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
