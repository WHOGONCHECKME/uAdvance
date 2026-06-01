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
  GET  /tags                  → all tags with article counts
  POST /chat                  → AI chat via OpenAI (key stored server-side)
"""

import json
import os
import sqlite3
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── CONFIG ────────────────────────────────────────────────────────────────────

DB_PATH = Path(os.environ.get("DB_PATH") or str(Path(__file__).resolve().parent.parent / "uadvance.db"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

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
            selector_used    TEXT,
            is_regulator       INTEGER DEFAULT 0,
            regulator_name     TEXT,
            regulator_full_name TEXT,
            source_type        TEXT DEFAULT 'newsletter'
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://uadvance.com.au",
        "https://www.uadvance.com.au",
        "http://localhost:8080",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_methods=["GET", "POST"],
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
            a.scraped_at,
            a.is_regulator,
            a.regulator_name,
            a.regulator_full_name,
            a.source_type
        FROM articles a
        ORDER BY a.published_date DESC, a.scraped_at DESC
    """).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/articles/{article_id}")
def get_article(article_id: str):
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
    conn = get_conn()

    tokens = q.split()
    escaped_tokens = [token.replace('"', '""') for token in tokens]

    if len(escaped_tokens) == 1:
        fts_q = f'"{escaped_tokens[0]}"*'
    else:
        fts_q = '"' + " ".join(escaped_tokens[:-1]) + f' {escaped_tokens[-1]}*' + '"'

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
            a.scraped_at,
            a.is_regulator,
            a.regulator_name
        FROM articles_fts
        JOIN articles a ON articles_fts.rowid = a.rowid
        WHERE articles_fts MATCH ?
        ORDER BY rank
        LIMIT 50
    """, (fts_q,)).fetchall()

    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/tags")
def get_tags():
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


# ── CHAT ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str    # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]          # full conversation history
    article_title: str | None = None     # currently selected article (optional)
    article_summary: str | None = None
    article_text: str | None = None      # first 3000 chars passed from frontend
    article_publication: str | None = None
    article_date: str | None = None


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Proxies chat requests to OpenAI server-side so the API key
    is never exposed to the browser.

    The frontend sends the conversation history plus optional article
    context. This endpoint adds the system prompt and calls OpenAI,
    returning just the assistant's reply text.
    """
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    # Build system prompt
    system = (
        "You are a helpful research assistant for uAdvance, an Australian "
        "professional development platform for actuaries and financial services "
        "professionals. Answer clearly and concisely."
    )

    # Append article context if an article is selected
    if req.article_title:
        ctx_parts = [
            req.article_title  and f"Title: {req.article_title}",
            req.article_publication and f"Publication: {req.article_publication}",
            req.article_date   and f"Date: {req.article_date}",
            req.article_summary and f"Summary: {req.article_summary}",
            req.article_text   and f"Article text (first 3000 chars):\n{req.article_text}",
        ]
        ctx = "\n".join(p for p in ctx_parts if p)
        system += f"\n\nThe user is currently reading this article:\n{ctx}"

    messages = [{"role": "system", "content": system}]
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type":  "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                },
                json={
                    "model":      "gpt-4o",
                    "max_tokens": 600,
                    "messages":   messages,
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {str(e)}")

    reply = data["choices"][0]["message"]["content"]
    return {"reply": reply}
