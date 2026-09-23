"""Canonical data model for the Conference Intelligence Assistant.

Everything ingested -- a poster photo, a slide, a page of 1:1 notes -- is reduced
to one or more InsightCards. All downstream features (feed, debrief, Q&A,
historical delta) are operations over this single table.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    PHOTO = "photo"
    SLIDE = "slide"
    PDF_PAGE = "pdf_page"
    NOTE = "note"
    AUDIO = "audio"


class CardStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class Evidence(BaseModel):
    """Traceability back to the exact artifact a claim came from."""

    source_file: str = ""
    source_type: SourceType = SourceType.NOTE
    source_ref: str = ""  # "slide 12", "page 3", "photo"
    thumbnail_path: str | None = None
    verbatim: str = ""


class InsightCard(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    conference: str = ""
    day: date = Field(default_factory=date.today)

    title: str = ""
    company: str = ""
    asset: str = ""  # product / drug / platform
    indication: str = ""
    trial_name: str = ""
    phase: str = ""

    key_message: str = ""
    data_points: list[str] = Field(default_factory=list)
    competitor_mentions: list[str] = Field(default_factory=list)
    kol_quote: str = ""
    session_name: str = ""
    themes: list[str] = Field(default_factory=list)

    confidence: float = 0.5
    is_unpublished: bool = False  # flag for data not yet in the public domain
    status: CardStatus = CardStatus.DRAFT

    evidence: Evidence = Field(default_factory=Evidence)
    created_at: datetime = Field(default_factory=datetime.now)

    def search_text(self) -> str:
        parts = [
            self.title, self.company, self.asset, self.indication,
            self.trial_name, self.phase, self.key_message, self.kol_quote,
            self.session_name, " ".join(self.data_points),
            " ".join(self.competitor_mentions), " ".join(self.themes),
            self.evidence.verbatim,
        ]
        return "\n".join(p for p in parts if p)

    def citation(self) -> str:
        ref = self.evidence.source_ref
        return f"{self.evidence.source_file}{f' · {ref}' if ref else ''}"


class KnowledgeCategory(str, Enum):
    PRIOR_DEBRIEF = "prior_debrief"   # debriefs this team wrote at earlier conferences
    INTERNAL_REPORT = "internal_report"  # landscape reviews, therapy area assessments
    REFERENCE_DATA = "reference_data"  # asset/competitor/trial tables
    EXTERNAL = "external"              # publications, press releases, filings


class KnowledgeChunk(BaseModel):
    """A passage of pre-existing organisational knowledge the app can draw on.

    Distinct from InsightCard: cards are things observed at a conference, chunks
    are what the organisation already knew before walking in.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    category: KnowledgeCategory = KnowledgeCategory.INTERNAL_REPORT
    title: str = ""
    text: str = ""
    source_file: str = ""
    source_ref: str = ""
    conference: str = ""      # if this came from a specific prior conference
    published: date | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

    def search_text(self) -> str:
        return "\n".join(x for x in [self.title, self.text, " ".join(self.tags)] if x)

    def citation(self) -> str:
        bits = [self.source_file or self.title]
        if self.source_ref:
            bits.append(self.source_ref)
        if self.conference:
            bits.append(self.conference)
        return " · ".join(b for b in bits if b)


class ClientProfile(BaseModel):
    """Drives the repackaging of the same conference data per client."""

    name: str = ""
    therapeutic_areas: list[str] = Field(default_factory=list)
    own_assets: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    standing_questions: list[str] = Field(default_factory=list)
    tone: str = "Concise, evidence-led, suitable for a commercial leadership audience."

    def as_prompt_context(self) -> str:
        return (
            f"Client: {self.name}\n"
            f"Therapeutic areas of interest: {', '.join(self.therapeutic_areas) or 'n/a'}\n"
            f"Client's own assets: {', '.join(self.own_assets) or 'n/a'}\n"
            f"Competitors to watch: {', '.join(self.competitors) or 'n/a'}\n"
            f"Standing strategic questions:\n"
            + "\n".join(f"  {i+1}. {q}" for i, q in enumerate(self.standing_questions))
            + f"\nPreferred tone: {self.tone}"
        )


class DebriefSection(BaseModel):
    heading: str
    body: str = ""
    bullets: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class Debrief(BaseModel):
    conference: str = ""
    day: date = Field(default_factory=date.today)
    client: str = ""
    headline: str = ""
    executive_summary: str = ""
    sections: list[DebriefSection] = Field(default_factory=list)
    question_answers: list[dict[str, Any]] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    card_ids: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


# JSON schema handed to the LLM for structured extraction.
EXTRACTION_SCHEMA_HINT = """
{
  "cards": [
    {
      "title": "short descriptive title",
      "company": "sponsoring / presenting company, '' if unclear",
      "asset": "drug, product or platform name",
      "indication": "disease or indication",
      "trial_name": "study or trial identifier if present",
      "phase": "Phase 1/2/3/4 or ''",
      "key_message": "the single most important takeaway, 1-2 sentences",
      "data_points": ["specific numeric results, endpoints, safety signals"],
      "competitor_mentions": ["other companies or assets referenced"],
      "kol_quote": "verbatim quote from a KOL or company person, '' if none",
      "session_name": "session / symposium / booth name if identifiable",
      "themes": ["2-4 broad themes e.g. 'obesity combination therapy'"],
      "confidence": 0.0,
      "is_unpublished": false,
      "verbatim": "the exact source text supporting this card"
    }
  ]
}
"""
