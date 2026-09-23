"""Artifact -> InsightCard. The step everything else is built on."""

from __future__ import annotations

from datetime import date

from .ingest import Artifact
from .llm import complete_json
from .schema import EXTRACTION_SCHEMA_HINT, CardStatus, Evidence, InsightCard

SYSTEM = """You are a senior pharmaceutical competitive-intelligence analyst working \
the floor at a medical conference. You read posters, slides, booth panels and \
consultant notes and convert them into precise, structured intelligence records.

Rules:
- Extract only what the source actually supports. Never invent trial names, \
numbers or quotes. Leave a field empty rather than guessing.
- Capture every numeric result verbatim, including units, timepoints and \
comparators.
- Set is_unpublished to true when the content appears to be data not yet in the \
public domain (booth-only material, unpublished slides, private conversations).
- confidence reflects how legible and unambiguous the source is, 0.0 to 1.0.
- Produce one card per distinct message. A dense poster may yield 2-3 cards; a \
title slide may yield none.
Return JSON only, matching this shape exactly:"""


def _user_prompt(artifact: Artifact, conference: str) -> str:
    header = (
        f"Conference: {conference}\n"
        f"Source file: {artifact.source_file}\n"
        f"Source type: {artifact.source_type.value}\n"
        f"Source reference: {artifact.source_ref or 'n/a'}\n"
    )
    if artifact.image_bytes and not artifact.text:
        return header + "---\nRead the attached image and extract the intelligence it contains."
    return header + "---\n" + artifact.text


def _coerce(raw: dict, artifact: Artifact, conference: str, day: date) -> InsightCard:
    return InsightCard(
        conference=conference,
        day=day,
        title=str(raw.get("title", "")).strip(),
        company=str(raw.get("company", "")).strip(),
        asset=str(raw.get("asset", "")).strip(),
        indication=str(raw.get("indication", "")).strip(),
        trial_name=str(raw.get("trial_name", "")).strip(),
        phase=str(raw.get("phase", "")).strip(),
        key_message=str(raw.get("key_message", "")).strip(),
        data_points=[str(d) for d in raw.get("data_points", []) if str(d).strip()],
        competitor_mentions=[
            str(c) for c in raw.get("competitor_mentions", []) if str(c).strip()
        ],
        kol_quote=str(raw.get("kol_quote", "")).strip(),
        session_name=str(raw.get("session_name", "")).strip(),
        themes=[str(t) for t in raw.get("themes", []) if str(t).strip()],
        confidence=float(raw.get("confidence", 0.5) or 0.5),
        is_unpublished=bool(raw.get("is_unpublished", False)),
        status=CardStatus.DRAFT,
        evidence=Evidence(
            source_file=artifact.source_file,
            source_type=artifact.source_type,
            source_ref=artifact.source_ref,
            thumbnail_path=artifact.thumbnail_path,
            verbatim=str(raw.get("verbatim", ""))[:1200]
            or (artifact.text[:600] if artifact.text else ""),
        ),
    )


def extract_cards(
    artifact: Artifact, conference: str, day: date | None = None
) -> list[InsightCard]:
    day = day or date.today()
    result = complete_json(
        system=SYSTEM + EXTRACTION_SCHEMA_HINT,
        user=_user_prompt(artifact, conference),
        images=[artifact.image_bytes] if artifact.image_bytes else None,
        mock_key="extract",
    )
    raws = result.get("cards") or []
    if isinstance(raws, dict):
        raws = [raws]
    cards = [_coerce(r, artifact, conference, day) for r in raws if isinstance(r, dict)]
    return [c for c in cards if c.title or c.key_message]
