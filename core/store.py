"""SQLite persistence plus TF-IDF retrieval over InsightCards.

TF-IDF rather than a vector DB keeps the install light on locked-down corporate
machines; swap `search` for an embedding index without touching callers.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Iterable

from .config import DB_PATH
from .schema import CardStatus, ClientProfile, InsightCard, KnowledgeChunk

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    conference TEXT,
    day TEXT,
    company TEXT,
    asset TEXT,
    indication TEXT,
    status TEXT,
    is_historical INTEGER DEFAULT 0,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clients (
    name TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge (
    id TEXT PRIMARY KEY,
    category TEXT,
    conference TEXT,
    source_file TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runlog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, event TEXT, detail TEXT, seconds REAL
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def save_cards(cards: Iterable[InsightCard], is_historical: bool = False) -> int:
    rows = [
        (
            c.id, c.conference, c.day.isoformat(), c.company, c.asset,
            c.indication, c.status.value, int(is_historical), c.model_dump_json(),
        )
        for c in cards
    ]
    if not rows:
        return 0
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO cards "
            "(id, conference, day, company, asset, indication, status, is_historical, payload) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def _row_to_card(row: sqlite3.Row) -> InsightCard:
    return InsightCard.model_validate(json.loads(row["payload"]))


def load_cards(
    conference: str | None = None,
    day: date | None = None,
    include_historical: bool = False,
    statuses: Iterable[CardStatus] | None = None,
) -> list[InsightCard]:
    sql = "SELECT * FROM cards WHERE 1=1"
    params: list = []
    if not include_historical:
        sql += " AND is_historical = 0"
    if conference:
        sql += " AND conference = ?"
        params.append(conference)
    if day:
        sql += " AND day = ?"
        params.append(day.isoformat())
    if statuses:
        values = [s.value for s in statuses]
        sql += f" AND status IN ({','.join('?' * len(values))})"
        params.extend(values)
    with _conn() as conn:
        return [_row_to_card(r) for r in conn.execute(sql, params)]


def historical_cards() -> list[InsightCard]:
    with _conn() as conn:
        return [
            _row_to_card(r)
            for r in conn.execute("SELECT * FROM cards WHERE is_historical = 1")
        ]


def update_card(card: InsightCard) -> None:
    save_cards([card], is_historical=False)


def set_status(card_id: str, status: CardStatus) -> None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not row:
            return
        card = _row_to_card(row)
        card.status = status
        conn.execute(
            "UPDATE cards SET status = ?, payload = ? WHERE id = ?",
            (status.value, card.model_dump_json(), card_id),
        )


def delete_all(include_historical: bool = False) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM cards" if include_historical else "DELETE FROM cards WHERE is_historical = 0")


def conferences() -> list[str]:
    with _conn() as conn:
        return [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT conference FROM cards WHERE conference <> '' ORDER BY 1"
            )
        ]


def days(conference: str) -> list[date]:
    with _conn() as conn:
        return [
            date.fromisoformat(r[0])
            for r in conn.execute(
                "SELECT DISTINCT day FROM cards WHERE conference = ? AND is_historical = 0 ORDER BY 1",
                (conference,),
            )
        ]


# --- clients -----------------------------------------------------------------

def save_client(profile: ClientProfile) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO clients (name, payload) VALUES (?,?)",
            (profile.name, profile.model_dump_json()),
        )


def load_clients() -> list[ClientProfile]:
    with _conn() as conn:
        return [
            ClientProfile.model_validate(json.loads(r["payload"]))
            for r in conn.execute("SELECT * FROM clients ORDER BY name")
        ]


def delete_client(name: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM clients WHERE name = ?", (name,))


# --- knowledge base ----------------------------------------------------------

def save_knowledge(chunks: Iterable[KnowledgeChunk]) -> int:
    rows = [
        (c.id, c.category.value, c.conference, c.source_file, c.model_dump_json())
        for c in chunks
    ]
    if not rows:
        return 0
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO knowledge "
            "(id, category, conference, source_file, payload) VALUES (?,?,?,?,?)",
            rows,
        )
    return len(rows)


def load_knowledge(category: str | None = None) -> list[KnowledgeChunk]:
    sql = "SELECT payload FROM knowledge"
    params: list = []
    if category:
        sql += " WHERE category = ?"
        params.append(category)
    with _conn() as conn:
        return [
            KnowledgeChunk.model_validate(json.loads(r["payload"]))
            for r in conn.execute(sql, params)
        ]


def knowledge_sources() -> list[tuple[str, str, int]]:
    """(source_file, category, chunk_count) for the management view."""
    with _conn() as conn:
        return [
            (r["source_file"], r["category"], r["n"])
            for r in conn.execute(
                "SELECT source_file, category, COUNT(*) n FROM knowledge "
                "GROUP BY source_file, category ORDER BY source_file"
            )
        ]


def delete_knowledge(source_file: str | None = None) -> None:
    with _conn() as conn:
        if source_file:
            conn.execute("DELETE FROM knowledge WHERE source_file = ?", (source_file,))
        else:
            conn.execute("DELETE FROM knowledge")


def search_knowledge(
    query: str, top_k: int = 5, chunks: list[KnowledgeChunk] | None = None
) -> list[tuple[KnowledgeChunk, float]]:
    pool = chunks if chunks is not None else load_knowledge()
    if not pool:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [c.search_text() for c in pool]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vec.fit_transform(corpus + [query])
    sims = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    ranked = sorted(zip(pool, sims), key=lambda t: t[1], reverse=True)
    return [(c, float(s)) for c, s in ranked[:top_k] if s > 0.01]


# --- metrics -----------------------------------------------------------------

def log_event(event: str, detail: str = "", seconds: float = 0.0) -> None:
    from datetime import datetime

    with _conn() as conn:
        conn.execute(
            "INSERT INTO runlog (ts, event, detail, seconds) VALUES (?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), event, detail, seconds),
        )


def metrics() -> dict:
    with _conn() as conn:
        rows = list(conn.execute("SELECT event, COUNT(*) n, SUM(seconds) s FROM runlog GROUP BY event"))
    return {r["event"]: {"count": r["n"], "seconds": r["s"] or 0.0} for r in rows}


# --- retrieval ---------------------------------------------------------------

def search(query: str, cards: list[InsightCard], top_k: int = 8) -> list[tuple[InsightCard, float]]:
    """Rank cards against a natural-language question."""
    if not cards:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [c.search_text() for c in cards]
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vec.fit_transform(corpus + [query])
    sims = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    ranked = sorted(zip(cards, sims), key=lambda t: t[1], reverse=True)
    return [(c, float(s)) for c, s in ranked[:top_k] if s > 0.01]
