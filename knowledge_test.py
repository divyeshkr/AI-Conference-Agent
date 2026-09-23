"""Verify the internal knowledge base is indexed, retrieved and used in synthesis."""

from __future__ import annotations

import io
from datetime import date

from core import store
from core.config import get_settings
from core.knowledge import chunks_from_file, seed_demo_knowledge

get_settings().provider = "mock"
get_settings().api_key = ""
from core.schema import ClientProfile, InsightCard, KnowledgeCategory
from core.synth import answer_question, build_debrief

CURRENT = [
    InsightCard(
        conference="Obesity Week 2026", asset="CagriSema", company="Novo Nordisk",
        indication="Obesity", key_message="Repositioned onto cardiometabolic risk reduction.",
        data_points=["-13.7% weight reduction", "SBP -7.4 mmHg"],
    ),
    InsightCard(
        conference="Obesity Week 2026", asset="Retatrutide", company="Eli Lilly",
        indication="Obesity", phase="Phase 3",
        key_message="Triple agonism now the efficacy leader.",
        data_points=["-24.2% weight reduction at week 48"],
    ),
]


def make_docx(paragraphs: list[str]) -> bytes:
    from docx import Document

    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def main() -> None:
    store.delete_knowledge()
    store.delete_all(include_historical=True)

    # 1. seeded demo knowledge indexes
    seeded = seed_demo_knowledge()
    store.save_knowledge(seeded)
    print(f"seeded        : {len(seeded)} passage(s)")
    assert len(store.load_knowledge()) == len(seeded)

    # 2. a real document parses into passages, category inferred from filename
    doc = make_docx([
        "ASCO 2025 Day 1 debrief for the client.",
        "Competitor messaging centred on progression-free survival rather than overall "
        "survival, a notable shift from the prior year.",
        "Our recommendation was to prepare an OS-based counter-narrative.",
    ])
    chunks = chunks_from_file("ASCO_2025_daily_debrief.docx", doc)
    store.save_knowledge(chunks)
    assert chunks, "document produced no passages"
    assert chunks[0].category == KnowledgeCategory.PRIOR_DEBRIEF, \
        f"category inference failed: {chunks[0].category}"
    assert chunks[0].conference == "ASCO 2025", \
        f"conference inference failed: {chunks[0].conference!r}"
    print(f"parsed doc    : {len(chunks)} passage(s), "
          f"category={chunks[0].category.value}, conference={chunks[0].conference!r}")

    # 3. retrieval finds the right passage
    hits = store.search_knowledge("what evidence do payers require for reimbursement?")
    assert hits, "knowledge retrieval returned nothing"
    print(f"retrieval     : top hit -> {hits[0][0].title} ({hits[0][1]:.2f})")
    assert "payer" in hits[0][0].title.lower(), "retrieved the wrong passage"

    # 4. Q&A surfaces knowledge alongside conference cards
    answer, cards, knowledge = answer_question(
        "What do payers require for obesity reimbursement?", CURRENT
    )
    assert knowledge, "Q&A did not consult the knowledge base"
    print(f"qa            : {len(cards)} card(s) + {len(knowledge)} knowledge passage(s)")

    # 5. the debrief includes a context section drawn from internal knowledge
    client = ClientProfile(name="Test Client", therapeutic_areas=["Obesity"],
                           competitors=["Eli Lilly"])
    debrief = build_debrief(CURRENT, client, "Obesity Week 2026", date.today(), [])
    headings = [s.heading for s in debrief.sections]
    print(f"debrief       : {headings}")
    assert "Context from existing intelligence" in headings, \
        "knowledge context missing from debrief"

    store.delete_knowledge()
    store.delete_all(include_historical=True)
    print("\nKNOWLEDGE BASE OK")


if __name__ == "__main__":
    main()
