"""Organisational knowledge: what the team already knew before the conference.

Prior debriefs, therapy-area reviews, competitor landscape documents and reference
tables. Kept separate from InsightCards because the provenance and trust level are
different -- a card is something a consultant observed this week, a chunk is
established internal knowledge.

No LLM call is involved in ingestion. Documents are parsed and chunked
deterministically, which means an archive of hundreds of files costs nothing and
takes seconds.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .ingest import IMAGE_EXT, ingest
from .schema import KnowledgeCategory, KnowledgeChunk

# Files worth reading from an archive folder. Images are excluded: OCR-ing a
# folder of scanned reports is a different and much more expensive problem.
ARCHIVE_EXT = {".docx", ".pdf", ".pptx", ".txt", ".md", ".csv"}

_CONF_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _guess_category(name: str) -> KnowledgeCategory:
    lowered = name.lower()
    if any(k in lowered for k in ("debrief", "daily", "readout", "recap")):
        return KnowledgeCategory.PRIOR_DEBRIEF
    if lowered.endswith(".csv"):
        return KnowledgeCategory.REFERENCE_DATA
    if any(k in lowered for k in ("press", "release", "publication", "abstract")):
        return KnowledgeCategory.EXTERNAL
    return KnowledgeCategory.INTERNAL_REPORT


def _guess_conference(name: str) -> str:
    """Pull something like 'ASCO 2025' out of a filename."""
    stem = Path(name).stem.replace("_", " ").replace("-", " ")
    match = _CONF_YEAR.search(stem)
    if not match:
        return ""
    before = stem[: match.start()].strip()
    token = before.split()[-1] if before.split() else ""
    return f"{token} {match.group(0)}".strip()


def chunks_from_file(
    name: str,
    data: bytes,
    category: KnowledgeCategory | None = None,
    conference: str = "",
    tags: list[str] | None = None,
) -> list[KnowledgeChunk]:
    """Parse a document into indexed passages. Reuses the conference parsers."""
    if Path(name).suffix.lower() in IMAGE_EXT:
        raise ValueError("Images are not supported in the knowledge base.")

    artifacts = ingest(name, data)
    category = category or _guess_category(name)
    conference = conference or _guess_conference(name)
    out: list[KnowledgeChunk] = []

    for art in artifacts:
        text = (art.text or "").strip()
        if len(text) < 40:  # skip title slides and near-empty pages
            continue
        out.append(
            KnowledgeChunk(
                category=category,
                title=_derive_title(text, name),
                text=text,
                source_file=name,
                source_ref=art.source_ref,
                conference=conference,
                tags=tags or [],
            )
        )
    return out


def _derive_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if 8 <= len(line) <= 120:
            return line
    return Path(fallback).stem


def chunks_from_folder(
    folder: str | Path,
    category: KnowledgeCategory | None = None,
    recursive: bool = True,
    max_files: int = 500,
) -> tuple[list[KnowledgeChunk], list[str]]:
    """Bulk-load an archive directory. Returns (chunks, errors)."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ValueError(f"Not a folder: {root}")

    pattern = "**/*" if recursive else "*"
    files = [
        p
        for p in sorted(root.glob(pattern))
        if p.is_file() and p.suffix.lower() in ARCHIVE_EXT
    ][:max_files]

    chunks: list[KnowledgeChunk] = []
    errors: list[str] = []
    for path in files:
        try:
            chunks += chunks_from_file(path.name, path.read_bytes(), category)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the import
            errors.append(f"{path.name}: {exc}")
    return chunks, errors


def seed_demo_knowledge(conference_stem: str = "Obesity Week") -> list[KnowledgeChunk]:
    """Representative internal knowledge, so the capability is demonstrable offline."""
    year = date.today().year - 1
    entries = [
        (
            KnowledgeCategory.PRIOR_DEBRIEF,
            f"{conference_stem} {year} — Day 2 client debrief",
            "Novo Nordisk led its entire day-two narrative on headline weight-loss "
            "magnitude, positioning CagriSema against tirzepatide on percentage reduction "
            "alone. Payer questions from the floor focused on durability and "
            "discontinuation rather than peak efficacy. Our recommendation to the client "
            "was to prepare for an outcomes-led evidence bar within 24 months.",
        ),
        (
            KnowledgeCategory.PRIOR_DEBRIEF,
            f"{conference_stem} {year} — Day 3 client debrief",
            "Lilly's retatrutide Phase 2 data drew the largest audience of the congress. "
            "KOL commentary was enthusiastic but repeatedly flagged that the trial had not "
            "yet separated from tirzepatide on a like-for-like basis. Amgen kept MariTide "
            "messaging confined to the booth and declined to discuss dosing intervals.",
        ),
        (
            KnowledgeCategory.INTERNAL_REPORT,
            "Obesity therapy area landscape review",
            "The incretin market is consolidating around three axes of differentiation: "
            "absolute weight reduction, dosing convenience, and quality of weight lost "
            "(lean mass preservation). Oral small molecules are expected to compete on "
            "access and manufacturing scale rather than efficacy. Persistence remains the "
            "single largest determinant of realised market size, with real-world "
            "discontinuation running above 50% at twelve months.",
        ),
        (
            KnowledgeCategory.INTERNAL_REPORT,
            "Payer evidence requirements — obesity, US commercial",
            "Across interviews with twelve US commercial plans, weight reduction alone was "
            "not considered a reimbursable outcome. Plans indicated that cardiovascular or "
            "renal outcomes data would be required for unrestricted formulary placement, "
            "with step-through requirements expected to persist through 2027.",
        ),
        (
            KnowledgeCategory.REFERENCE_DATA,
            "Competitor asset tracker — obesity",
            "Eli Lilly: tirzepatide (marketed), retatrutide (Phase 3), orforglipron (Phase 3). "
            "Novo Nordisk: semaglutide (marketed), CagriSema (Phase 3), amycretin (Phase 1). "
            "Amgen: MariTide (Phase 2). Boehringer Ingelheim: survodutide (Phase 3, MASH lead). "
            "Structure Therapeutics: aleniglipron (Phase 2b, oral). "
            "Regeneron: trevogrumab combination (Phase 2, lean mass).",
        ),
    ]
    return [
        KnowledgeChunk(
            category=cat,
            title=title,
            text=text,
            source_file=f"{title}.docx",
            conference=f"{conference_stem} {year}" if cat == KnowledgeCategory.PRIOR_DEBRIEF else "",
            tags=["demo"],
        )
        for cat, title, text in entries
    ]
