"""
main.py
──────────────────────────────────────────────────────────────
FastAPI backend for uAdvance.

Locally:
    pip install fastapi uvicorn
    uvicorn main:app --reload

On Railway:
    Start command: uvicorn main:app --host 0.0.0.0 --port $PORT

ENDPOINTS
─────────
  GET  /                      → health check
  GET  /articles              → full article list (replaces articles_index.json)
  GET  /articles/{id}         → single article including full_text
  GET  /search?q=inflation    → full-text search via FTS5
"""

import json
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ── CONFIG ────────────────────────────────────────────────────────────────────

# On Railway, set a DB_PATH environment variable pointing to your volume.
# Locally it finds uadvance.db at the project root automatically.
DB_PATH = Path(os.environ.get("DB_PATH") or str(Path(__file__).resolve().parent.parent / "uadvance.db"))

def ensure_db():
    """
    If the database doesn't exist at DB_PATH, create it and
    run init + migrate so the app works on first deploy.
    """
    if DB_PATH.exists():
        return
    
    print(f"Database not found at {DB_PATH} — initialising...")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Create all tables (copied from init_db.py)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS newsletters (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            subject       TEXT NOT NULL,
            received_date TEXT
        );
        CREATE TABLE IF NOT EXISTS articles (
            id               TEXT PRIMARY KEY,
            newsletter_id    INTEGER REFERENCES newsletters(id),
            title            TEXT NOT NULL,
            full_text        TEXT,
            summary          TEXT,
            ticker_line      TEXT,
            key_points       TEXT,
            publication      TEXT,
            author           TEXT,
            published_date   TEXT,
            word_count       INTEGER,
            heading          TEXT,
            newsletter       TEXT,
            factiva_url      TEXT,
            final_url        TEXT,
            redirected_to_source INTEGER DEFAULT 0,
            summarised       INTEGER DEFAULT 0,
            scraped_at       TEXT,
            page_title       TEXT,
            selector_used    TEXT
        );
        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS article_tags (
            article_id  TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (article_id, tag_id)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            title, summary, full_text,
            content='articles', content_rowid='rowid'
        );
    """)
    conn.commit()
    conn.close()
    print(f"Database initialised at {DB_PATH}")

ensure_db()

# ── APP ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="uAdvance API", version="1.0.0")

# CORS — allows your GitHub Pages frontend to call this API.
# Replace the GitHub Pages URL with your actual domain once live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://uadvance.com.au",          # production domain — update to yours
        "http://localhost:8080",             # local dev
        "http://127.0.0.1:5500",            # VS Code Live Server
        "http://localhost:5500",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── DB HELPERS ────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a Row to a dict and parse key_points back to a list."""
    d = dict(row)
    try:
        d["key_points"] = json.loads(d.get("key_points") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["key_points"] = []
    return d


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.get("/")
def health_check():
    try:
        conn = get_conn()
        count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        conn.close()
        return {"status": "ok", "articles": count}
    except Exception as e:
        return {"status": "ok", "articles": 0, "note": str(e)}

@app.get("/articles")
def get_articles():
    """
    Returns all summarised articles as a JSON array.
    This is a drop-in replacement for articles_index.json —
    the response format is identical so the frontend needs no changes.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            a.id,
            a.title,
            a.summary,
            a.ticker_line,
            a.key_points,
            a.publication,
            a.author,
            a.published_date,
            a.word_count,
            a.heading,
            a.newsletter,
            a.final_url,
            a.factiva_url,
            a.summarised,
            a.scraped_at
        FROM articles a
        ORDER BY a.published_date DESC, a.scraped_at DESC
    """).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/articles/{article_id}")
def get_article(article_id: str):
    """
    Returns a single article by id, including full_text.
    Used when the user opens an article to read it in full.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return row_to_dict(row)


@app.get("/search")
def search_articles(q: str = Query(..., min_length=2, description="Search query")):
    """
    Full-text search across title, summary, and full_text using FTS5.
    Returns matching articles ordered by relevance (bm25 rank).

    Example: GET /search?q=inflation
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            a.id,
            a.title,
            a.summary,
            a.ticker_line,
            a.key_points,
            a.publication,
            a.author,
            a.published_date,
            a.word_count,
            a.heading,
            a.newsletter,
            a.final_url,
            a.scraped_at
        FROM articles_fts
        JOIN articles a ON articles_fts.rowid = a.rowid
        WHERE articles_fts MATCH ?
        ORDER BY rank
        LIMIT 50
    """, (q,)).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/tags")
def get_tags():
    """Returns all tags with article counts."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.id, t.name, COUNT(at.article_id) as article_count
        FROM tags t
        LEFT JOIN article_tags at ON t.id = at.tag_id
        GROUP BY t.id
        ORDER BY article_count DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]
