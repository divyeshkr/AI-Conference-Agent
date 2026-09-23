"""Synthesis: client-tailored debriefs, Q&A and historical deltas.

The debrief skeleton is assembled deterministically from real cards so the output
is always grounded and traceable; the LLM writes narrative on top of that
skeleton rather than inventing it.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date

from .llm import complete_text
from .schema import ClientProfile, Debrief, DebriefSection, InsightCard, KnowledgeChunk
from .store import search, search_knowledge

ANALYST_SYSTEM = """You are a senior life-sciences consultant writing a daily \
conference debrief for a named client. Write in tight, declarative business \
prose. Every claim must be supported by the evidence supplied to you -- never \
introduce facts, numbers or companies that are not in the evidence. Prefer \
implications over description: the client already knows what was presented, they \
are paying for what it means for them. No preamble, no headings unless asked."""


# --- relevance ---------------------------------------------------------------

def relevance(card: InsightCard, client: ClientProfile) -> float:
    """How much this card matters to this specific client."""
    text = card.search_text().lower()
    score = 0.0
    for comp in client.competitors:
        if comp.lower() in text:
            score += 3.0
    for asset in client.own_assets:
        if asset.lower() in text:
            score += 3.5
    for area in client.therapeutic_areas:
        if area.lower() in text:
            score += 2.0
    for question in client.standing_questions:
        words = {w for w in question.lower().split() if len(w) > 4}
        if words:
            score += 2.5 * len(words & set(text.split())) / len(words)
    score += card.confidence
    if card.is_unpublished:
        score += 1.0
    if card.data_points:
        score += 0.5
    return round(score, 2)


def rank_for_client(cards: list[InsightCard], client: ClientProfile) -> list[tuple[InsightCard, float]]:
    scored = [(c, relevance(c, client)) for c in cards]
    return sorted(scored, key=lambda t: t[1], reverse=True)


# --- evidence packing --------------------------------------------------------

def _evidence_block(cards: list[InsightCard], limit: int = 30) -> str:
    lines: list[str] = []
    for card in cards[:limit]:
        bits = [f"[{card.id}] {card.title}"]
        if card.company:
            bits.append(f"Company: {card.company}")
        if card.asset:
            bits.append(f"Asset: {card.asset}")
        if card.indication:
            bits.append(f"Indication: {card.indication}")
        if card.trial_name or card.phase:
            bits.append(f"Study: {card.trial_name} {card.phase}".strip())
        if card.key_message:
            bits.append(f"Message: {card.key_message}")
        for dp in card.data_points:
            bits.append(f"Data: {dp}")
        if card.kol_quote:
            bits.append(f'Quote: "{card.kol_quote}"')
        if card.is_unpublished:
            bits.append("NOTE: flagged as unpublished / not in public domain")
        bits.append(f"Source: {card.citation()}")
        lines.append("\n".join(bits))
    return "\n\n".join(lines)


# --- themes and deltas -------------------------------------------------------

def top_themes(cards: list[InsightCard], n: int = 6) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for card in cards:
        counter.update(t.strip().lower() for t in card.themes if t.strip())
    return counter.most_common(n)


def _norm(value: str) -> str:
    """Normalise an entity name so 'MariTide (maridebart cafraglutide)' == 'maritide'."""
    value = value.lower().split("(")[0]
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _history_index(historical: list[InsightCard]) -> dict[str, dict[str, list[InsightCard]]]:
    """Three lookup tables, tried in descending order of precision."""
    index: dict[str, dict[str, list[InsightCard]]] = {
        "asset": defaultdict(list),
        "trial": defaultdict(list),
        "programme": defaultdict(list),  # company + indication
    }
    for card in historical:
        if card.asset:
            index["asset"][_norm(card.asset)].append(card)
        if card.trial_name:
            index["trial"][_norm(card.trial_name)].append(card)
        if card.company and card.indication:
            index["programme"][f"{_norm(card.company)}|{_norm(card.indication)}"].append(card)
    return index


def _find_prior(card: InsightCard, index: dict) -> tuple[InsightCard | None, str]:
    if card.asset:
        hits = index["asset"].get(_norm(card.asset))
        if hits:
            return hits[0], "same asset"
    if card.trial_name:
        hits = index["trial"].get(_norm(card.trial_name))
        if hits:
            return hits[0], "same trial programme"
    if card.company and card.indication:
        key = f"{_norm(card.company)}|{_norm(card.indication)}"
        hits = index["programme"].get(key)
        if hits:
            return hits[0], "same company and indication"
    return None, ""


def historical_delta(
    current: list[InsightCard], historical: list[InsightCard]
) -> list[dict]:
    """Match this year's cards to prior intelligence, most precise match first."""
    if not historical:
        return []
    index = _history_index(historical)
    deltas: list[dict] = []
    for card in current:
        prior, basis = _find_prior(card, index)
        if not prior:
            continue
        deltas.append(
            {
                "asset": card.asset or card.company or card.title,
                "company": card.company,
                "basis": basis,
                "now": card.key_message or card.title,
                "now_data": card.data_points[:2],
                "then": prior.key_message or prior.title,
                "then_data": prior.data_points[:2],
                "then_conference": prior.conference or "prior conference",
                "card_id": card.id,
            }
        )
    return deltas


def new_developments(
    current: list[InsightCard], historical: list[InsightCard]
) -> list[InsightCard]:
    """Cards with no counterpart in prior intelligence — genuinely new this year."""
    if not historical:
        return []
    index = _history_index(historical)
    fresh = []
    for card in current:
        prior, _ = _find_prior(card, index)
        if prior is None and (card.asset or card.company):
            fresh.append(card)
    return fresh


def _history_context(deltas: list[dict], fresh: list[InsightCard]) -> str:
    """Compact prior-year context injected into the narrative prompts."""
    if not deltas and not fresh:
        return ""
    lines = ["PRIOR CONFERENCE INTELLIGENCE (for comparison, not for restating):"]
    for d in deltas[:8]:
        lines.append(
            f"- {d['asset']}: at {d['then_conference']} we recorded \"{d['then']}\""
            f"{' (' + '; '.join(d['then_data']) + ')' if d['then_data'] else ''}."
        )
    if fresh:
        names = ", ".join(
            dict.fromkeys(c.asset or c.company for c in fresh[:8] if c.asset or c.company)
        )
        lines.append(f"- No prior intelligence exists for: {names}. Treat these as new.")
    return "\n".join(lines)


# --- question answering ------------------------------------------------------

def _knowledge_block(chunks: list[KnowledgeChunk], limit: int = 4) -> str:
    if not chunks:
        return ""
    lines = ["ESTABLISHED INTERNAL KNOWLEDGE (background, not observed at this conference):"]
    for chunk in chunks[:limit]:
        body = re.sub(r"\s+", " ", chunk.text)[:700]
        lines.append(f"- [{chunk.category.value}] {chunk.title}: {body} (source: {chunk.citation()})")
    return "\n".join(lines)


def answer_question(
    question: str,
    cards: list[InsightCard],
    top_k: int = 8,
    use_knowledge: bool = True,
) -> tuple[str, list[InsightCard], list[KnowledgeChunk]]:
    """Answer from conference cards, grounded additionally in internal knowledge."""
    hits = search(question, cards, top_k=top_k)
    knowledge = (
        [k for k, _ in search_knowledge(question, top_k=4)] if use_knowledge else []
    )

    if not hits and not knowledge:
        return ("Nothing in the material captured so far addresses this question.", [], [])

    matched = [c for c, _ in hits]
    answer = complete_text(
        system=ANALYST_SYSTEM,
        user=(
            f"Question from the client:\n{question}\n\n"
            f"Conference evidence:\n{_evidence_block(matched)}\n\n"
            f"{_knowledge_block(knowledge)}\n\n"
            "Answer in at most 140 words. Cite the bracketed card ids inline like [a1b2c3] "
            "for claims from the conference. Where internal knowledge adds context, say so "
            "explicitly and name the source. If the evidence is partial, say so."
        ),
    )
    if answer.startswith("Mock narrative"):
        answer = _fallback_answer(matched, knowledge)
    return answer, matched, knowledge


def _fallback_answer(
    cards: list[InsightCard], knowledge: list[KnowledgeChunk] | None = None
) -> str:
    parts = []
    if cards:
        lines = []
        for card in cards[:4]:
            detail = card.key_message or card.title
            data = f" ({card.data_points[0]})" if card.data_points else ""
            lines.append(f"- {card.company or 'Unattributed'}: {detail}{data} [{card.id}]")
        parts.append("From material captured at this conference:\n" + "\n".join(lines))
    if knowledge:
        lines = [f"- {k.title} ({k.citation()})" for k in knowledge[:3]]
        parts.append("Relevant existing internal knowledge:\n" + "\n".join(lines))
    return "\n\n".join(parts) if parts else "No relevant material found."


# --- debrief -----------------------------------------------------------------

def build_debrief(
    cards: list[InsightCard],
    client: ClientProfile,
    conference: str,
    day: date,
    historical: list[InsightCard] | None = None,
) -> Debrief:
    ranked = rank_for_client(cards, client)
    relevant = [c for c, s in ranked]
    evidence = _evidence_block(relevant)

    history = historical or []
    deltas = historical_delta(relevant, history)
    fresh = new_developments(relevant, history)
    history_context = _history_context(deltas, fresh)

    # Pull the internal knowledge most relevant to what was seen today.
    probe = " ".join(
        x for c in relevant[:8] for x in (c.asset, c.indication, c.key_message) if x
    ) or client.name
    knowledge = [k for k, _ in search_knowledge(probe, top_k=4)]
    knowledge_context = _knowledge_block(knowledge)

    debrief = Debrief(
        conference=conference,
        day=day,
        client=client.name,
        card_ids=[c.id for c in relevant],
    )

    # Executive summary, written against prior intelligence rather than in isolation
    summary = complete_text(
        ANALYST_SYSTEM,
        f"{client.as_prompt_context()}\n\n"
        f"Conference: {conference}, day of {day:%d %B %Y}.\n\n"
        f"Evidence:\n{evidence}\n\n"
        f"{history_context}\n\n"
        f"{knowledge_context}\n\n"
        "Write a 4-6 sentence executive summary of today for this client. Lead with the "
        "single most consequential development for them. Where prior intelligence exists, "
        "say explicitly what has changed since then rather than restating the old position. "
        "Where something is new, say so. Where today's observations confirm or contradict "
        "established internal knowledge, call that out. Cite card ids inline like [a1b2c3].",
    )
    if summary.startswith("Mock narrative"):
        summary = _fallback_summary(relevant, client, conference, deltas, fresh)
    debrief.executive_summary = summary.strip()
    debrief.headline = (relevant[0].key_message or relevant[0].title) if relevant else ""

    # Top takeaways
    takeaways = [
        f"{c.company + ': ' if c.company else ''}{c.key_message or c.title} [{c.id}]"
        for c in relevant[:5]
    ]
    if takeaways:
        debrief.sections.append(
            DebriefSection(
                heading="Top takeaways",
                bullets=takeaways,
                citations=[c.citation() for c in relevant[:5]],
            )
        )

    # Competitor-by-competitor
    by_company: dict[str, list[InsightCard]] = defaultdict(list)
    for card in relevant:
        if card.company:
            by_company[card.company].append(card)
    watched = [c for c in client.competitors if c in by_company] or list(by_company)[:5]
    for company in watched:
        group = by_company.get(company, [])
        if not group:
            continue
        bullets = []
        for card in group[:4]:
            line = card.key_message or card.title
            if card.data_points:
                line += " — " + "; ".join(card.data_points[:2])
            bullets.append(f"{line} [{card.id}]")
        debrief.sections.append(
            DebriefSection(
                heading=f"Competitor focus — {company}",
                bullets=bullets,
                citations=[c.citation() for c in group[:4]],
            )
        )

    # Data highlights
    data_cards = [c for c in relevant if c.data_points][:6]
    if data_cards:
        debrief.sections.append(
            DebriefSection(
                heading="Data highlights",
                bullets=[
                    f"{c.asset or c.company or c.title}"
                    f"{f' ({c.trial_name} {c.phase})' if c.trial_name else ''}: "
                    + "; ".join(c.data_points[:3])
                    + f" [{c.id}]"
                    for c in data_cards
                ],
                citations=[c.citation() for c in data_cards],
            )
        )

    # Conference themes
    themes = top_themes(relevant)
    if themes:
        debrief.sections.append(
            DebriefSection(
                heading="Emerging conference themes",
                bullets=[f"{t.title()} — referenced in {n} captured item(s)" for t, n in themes],
            )
        )

    # Movement vs prior intelligence
    if deltas:
        debrief.sections.append(
            DebriefSection(
                heading="Movement versus prior conference intelligence",
                body="Comparison against intelligence captured at previous conferences.",
                bullets=[
                    f"{d['asset']} ({d['company']}): then — {d['then']}"
                    f"{' (' + '; '.join(d['then_data']) + ')' if d['then_data'] else ''}. "
                    f"Now — {d['now']}"
                    f"{' (' + '; '.join(d['now_data']) + ')' if d['now_data'] else ''}. "
                    f"[matched on {d['basis']}] [{d['card_id']}]"
                    for d in deltas[:6]
                ],
            )
        )

    # What the organisation already knew that bears on today
    if knowledge:
        debrief.sections.append(
            DebriefSection(
                heading="Context from existing intelligence",
                body="Relevant prior analysis and internal knowledge, provided as background.",
                bullets=[f"{k.title} — {re.sub(r'\\s+', ' ', k.text)[:220]}…" for k in knowledge],
                citations=[k.citation() for k in knowledge],
            )
        )

    # Genuinely new, i.e. nothing comparable in prior intelligence
    if fresh:
        debrief.sections.append(
            DebriefSection(
                heading="New since the last conference",
                body="No prior intelligence exists on the following — these are first sightings.",
                bullets=[
                    f"{c.company + ': ' if c.company else ''}{c.key_message or c.title} [{c.id}]"
                    for c in fresh[:6]
                ],
            )
        )

    # Unverified / private intelligence, kept visually separate for compliance
    unpublished = [c for c in relevant if c.is_unpublished][:5]
    if unpublished:
        debrief.sections.append(
            DebriefSection(
                heading="Unpublished / to be verified",
                body="The following was captured from booth materials, private discussions "
                "or non-public slides and has not been externally verified.",
                bullets=[
                    f"{c.company + ': ' if c.company else ''}{c.key_message or c.title} [{c.id}]"
                    for c in unpublished
                ],
            )
        )

    # Implications
    implications = complete_text(
        ANALYST_SYSTEM,
        f"{client.as_prompt_context()}\n\nEvidence:\n{evidence}\n\n"
        "List 3-5 specific strategic implications for this client, each one sentence, "
        "each starting with a verb. Cite card ids inline.",
    )
    if not implications.startswith("Mock narrative"):
        bullets = [
            line.lstrip("-•* ").strip()
            for line in implications.splitlines()
            if line.strip()
        ]
        debrief.sections.append(
            DebriefSection(heading="Strategic implications", bullets=bullets[:5])
        )
    elif relevant:
        debrief.sections.append(
            DebriefSection(
                heading="Strategic implications",
                bullets=[
                    f"Assess the competitive impact of {c.company}'s position on "
                    f"{c.asset or c.indication or 'this area'} [{c.id}]"
                    for c in relevant[:3]
                ],
            )
        )

    # Client's standing questions
    for question in client.standing_questions:
        answer, used, used_knowledge = answer_question(question, relevant, top_k=5)
        debrief.question_answers.append(
            {
                "question": question,
                "answer": answer,
                "citations": [c.citation() for c in used]
                + [k.citation() for k in used_knowledge],
            }
        )

    # Watchlist
    debrief.watchlist = [
        f"Follow up on {c.asset or c.title} ({c.company})"
        for c in relevant[:4]
        if c.confidence < 0.8 or c.is_unpublished
    ]
    return debrief


def _fallback_summary(
    cards: list[InsightCard],
    client: ClientProfile,
    conference: str,
    deltas: list[dict] | None = None,
    fresh: list[InsightCard] | None = None,
) -> str:
    if not cards:
        return "No material has been captured for this day yet."
    lead = cards[0]
    companies = [c.company for c in cards[:6] if c.company]
    seen: list[str] = []
    for company in companies:
        if company not in seen:
            seen.append(company)
    themes = ", ".join(t for t, _ in top_themes(cards, 3))
    parts = [
        f"The most consequential development today for {client.name or 'the client'} is "
        f"{lead.key_message or lead.title} [{lead.id}].",
        f"Activity clustered around {themes or 'several areas'}, with material captured from "
        f"{', '.join(seen[:4]) or 'multiple organisations'}.",
    ]
    if deltas:
        d = deltas[0]
        parts.append(
            f"Against prior intelligence, {d['asset']} has moved from \"{d['then']}\" at "
            f"{d['then_conference']} to \"{d['now']}\" [{d['card_id']}]."
        )
    if fresh:
        names = ", ".join(
            dict.fromkeys(c.asset or c.company for c in fresh[:3] if c.asset or c.company)
        )
        if names:
            parts.append(f"No prior intelligence exists on {names}, which are new this year.")
    parts.append(
        f"{len(cards)} intelligence items were logged at {conference}, of which "
        f"{sum(1 for c in cards if c.is_unpublished)} are unpublished and require verification "
        f"before external circulation."
    )
    return " ".join(parts)
