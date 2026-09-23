"""End-to-end check of the core engine with no UI and no API key.

Run: .venv\\Scripts\\python.exe smoke_test.py
"""

from __future__ import annotations

from datetime import date

from core import store
from core.config import get_settings
from core.docx_out import build_docx, build_email

get_settings().provider = "mock"
get_settings().api_key = ""
from core.extract import extract_cards
from core.ingest import ingest
from core.schema import CardStatus, ClientProfile
from core.synth import answer_question, build_debrief, historical_delta

CONF = "Smoke Test Congress 2026"
NOTE = """Booth conversation, Hall 3.
Spoke with the medical affairs lead about their Phase 3 obesity readout.
They reported a 22.4% mean weight reduction at week 72 versus 2.9% for placebo.
Discontinuation due to adverse events was 7.2%. They were noticeably cautious
about the cardiovascular outcomes timeline and said the filing is now 2027.
"""


def main() -> None:
    store.delete_all(include_historical=True)

    artifacts = ingest("booth_notes.txt", NOTE.encode())
    assert artifacts, "ingest produced no artifacts"
    print(f"ingest        : {len(artifacts)} artifact(s)")

    cards = []
    for art in artifacts:
        cards += extract_cards(art, CONF, date.today())
    assert cards, "extraction produced no cards"
    store.save_cards(cards)
    print(f"extract       : {len(cards)} card(s) -> {cards[0].title[:60]}")

    for card in cards:
        store.set_status(card.id, CardStatus.APPROVED)

    client = ClientProfile(
        name="Test Client",
        therapeutic_areas=["Obesity"],
        own_assets=["CagriSema"],
        competitors=["Eli Lilly", "Amgen"],
        standing_questions=["What is the competitive efficacy benchmark in obesity?"],
    )
    store.save_client(client)
    assert store.load_clients(), "client did not persist"
    print(f"store         : {len(store.load_cards())} card(s), {len(store.load_clients())} client(s)")

    loaded = store.load_cards(conference=CONF, day=date.today())
    assert loaded, "cards did not round-trip through sqlite"

    answer, sources, knowledge = answer_question("What weight reduction was reported?", loaded)
    assert answer, "empty answer"
    print(f"qa            : {len(sources)} card(s), {len(knowledge)} knowledge "
          f"-> {answer[:60].strip()}...")

    debrief = build_debrief(loaded, client, CONF, date.today(), [])
    assert debrief.executive_summary, "empty executive summary"
    assert debrief.sections, "no debrief sections"
    print(f"debrief       : {len(debrief.sections)} section(s), "
          f"{len(debrief.question_answers)} answered question(s)")

    delta = historical_delta(loaded, loaded)
    print(f"delta         : {len(delta)} comparison(s)")

    path = build_docx(debrief, loaded)
    assert path.exists() and path.stat().st_size > 5000, "docx looks empty"
    print(f"docx          : {path.name} ({path.stat().st_size // 1024} KB)")

    email = build_email(debrief)
    assert "Subject:" in email, "email draft malformed"
    print(f"email         : {len(email)} chars")

    store.delete_all(include_historical=True)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
