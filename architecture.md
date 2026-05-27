# uAdvance — Architecture & Operations

This is the living reference document for the uAdvance project. Read this first when you (or an LLM helping you) need context on how the system works. Update it whenever a structural change is made.

---

## 1. What uAdvance Is

A two-part product sharing one codebase and domain:

- **Marketing/courses site** — `uadvance.com.au` — landing page and course pages (AI in Financial Services as the flagship, plus Excel, Power BI, SQL, Python, ML, Data Analytics, R).
- **News aggregator (`news.html`)** — pulls Dow Jones (via Outlook newsletter) and regulator updates (APRA, ASIC, etc.), summarises each article with OpenAI, makes everything full-text searchable, and serves it to a private password-gated reader UI.

Currently single-user/private. Future direction: logins → subscriptions → payments → saved/tagged articles → mobile-friendly UI.

---

## 2. Tech Stack at a Glance

| Layer | Tech |
|---|---|
| Frontend | Static HTML/CSS/JS hosted on **GitHub Pages** |
| Backend | **FastAPI** (Python) on **Railway** (uvicorn) |
| Database | **SQLite** in WAL mode on a Railway persistent volume |
| Search | **FTS5** virtual table with BM25 ranking |
| Email ingest | Microsoft Graph API via **MSAL** auth |
| Scraping | **Playwright** browser automation for accessing licensed article content |
| Summarisation | **OpenAI GPT-4o-mini** |
| Auth/Payments | Not yet built |

---

## 3. Current Deployment Model

The split between *where things run* is the single most important operational fact about uAdvance:

- **GitHub Pages** serves the static frontend (`index.html`, `news.html`, course pages). Updated via `git push`.
- **Railway** serves the FastAPI backend and hosts the production SQLite database at `/data/uadvance.db`. Code updates via `git push`; data updates via `railway volume files upload`.
- **Your laptop** runs the daily ingest pipeline. Railway does **not** automatically receive new data — you have to push the SQLite file up after each run.

These three places are independent. Pushing code does not move data. Uploading the DB does not redeploy code. Editing a local `articles_index.json` does not change anything on the live API.

---

## 4. Folder Structure

```
uAdvance/                              ← repo root, also PROJECT_ROOT for scripts
├── index.html                         ← marketing homepage
├── news.html                          ← private news reader (password-gated)
├── about.html, courses.html, contact.html
├── excel/, da/, pbi/, sql/, python/, ml/, r/    ← course pages
│   └── (matching .html files at root)
├── articles/                          ← per-article JSON backups (archive only)
├── articles_index.json                ← frontend fallback snapshot
├── uadvance.db                        ← local SQLite (production copy lives on Railway)
├── assets/, favicon/
├── CNAME                              ← uadvance.com.au
│
├── backend/                           ← FastAPI app deployed to Railway
│   ├── main.py                        ← API: /articles, /articles/{id}, /search, etc.
│   ├── requirements.txt
│   └── railway.toml                   ← Railway picks this up automatically
│
└── dowjones-news-bot/                 ← daily ETL pipeline (runs locally for now)
    ├── extract_article_links.py       ← Step 1: Outlook → article_links.json
    ├── extract_article_content_2.py   ← Step 2: Playwright → DB + JSON
    ├── fetch_regulators.py            ← Step 3: APRA/ASIC etc. → DB
    ├── summarise3.py                  ← Step 4: OpenAI → DB + articles_index.json
    ├── init_db.py                     ← one-off DB schema creator
    ├── migrate_json.py                ← one-off historical JSON → DB import
    ├── .env                           ← secrets (never commit)
    ├── msal_token_cache.json
    └── archive/
```

**Path convention in scripts:**
```python
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent          # one level up from dowjones-news-bot/
DB_PATH      = PROJECT_ROOT / "uadvance.db"
```

---

## 5. Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│  DAILY PIPELINE (runs locally, on demand)                   │
└─────────────────────────────────────────────────────────────┘

  Outlook (Dow Jones newsletter)
        │
        ▼
  extract_article_links.py ──► article_links.json
        │
        ▼
  extract_article_content_2.py
        │   (Playwright, opens article tabs)
        ▼
  uadvance.db (articles table, summarised=0)
        +
  articles/*.json (per-article JSON backups)

  Regulator emails (APRA, ASIC, RBA, etc.)
        │
        ▼
  fetch_regulators.py ──► uadvance.db (tagged source="APRA" etc.)
        │
        ▼
  summarise3.py
        │   (queries WHERE summarised=0, calls OpenAI, UPDATEs row)
        ▼
  uadvance.db (summarised=1)
        +
  articles_index.json (frontend fallback snapshot)

        │
        ▼
  railway volume files upload uadvance.db /data/uadvance.db --overwrite
        │
        ▼
  Railway volume → FastAPI sees new data → frontend shows new articles

┌─────────────────────────────────────────────────────────────┐
│  READ PATH (always-on)                                      │
└─────────────────────────────────────────────────────────────┘

  Browser → news.html (GitHub Pages)
        │   password gate (hardcoded in JS — obscurity, not security)
        ▼
  fetch('https://uadvance-production.up.railway.app/articles')
        │
        ▼
  FastAPI on Railway → SQLite (/data/uadvance.db) → JSON response
        │
        ▼
  If API fails → falls back to articles_index.json snapshot
```

---

## 6. Source of Truth

Articles exist in several forms. Knowing which is canonical for what avoids confusion.

| Storage | Role | Notes |
|---|---|---|
| Railway SQLite at `/data/uadvance.db` | **Production read path** — canonical for what users see | Only updated by `railway volume files upload` |
| Local `uadvance.db` | **Working copy** — canonical for what your pipeline writes | Becomes production once uploaded |
| `articles_index.json` | **Frontend fallback only** | Snapshot used if the API is unreachable |
| `articles/*.json` | **Per-article backups / debug archive** | Not read by the live site |

Rule of thumb: if you want to change what users see, the change must end up in the Railway SQLite file. Touching JSON files alone will not do it.

---

## 7. Database Schema

SQLite with WAL mode. Four normal tables + one FTS5 virtual table.

**`newsletters`** — one row per ingested newsletter email
- `id`, `received_at`, `subject`, `source` (e.g. "Dow Jones")

**`articles`** — the core table
- `id`, `newsletter_id` (FK), `title`, `heading`, `author`, `publication`,
- `published_date`, `final_url`, `summary`, `ticker_line`, `key_points`,
- `full_text`, `word_count`, `source` ("Dow Jones", "APRA", "ASIC", ...),
- `category` ("regulator_release" etc.), `is_regulator` (0/1),
- `summarised` (0/1), `created_at`

**`tags`** — tag definitions (for future save/group feature)
- `id`, `name`

**`article_tags`** — many-to-many join
- `article_id` (FK), `tag_id` (FK)

**`articles_fts`** — FTS5 virtual table
- Indexes `title`, `summary`, `full_text`
- Kept in sync by insert/update/delete triggers on `articles`
- Queried with `MATCH` + `bm25()` for ranked full-text search

**Idempotency:** ingestion uses `INSERT OR IGNORE` based on URL/hash so re-running the pipeline is safe.

---

## 8. Backend API (`backend/main.py`)

Deployed at: `https://uadvance-production.up.railway.app`

| Endpoint | Returns |
|---|---|
| `GET /articles` | All articles (no `full_text` — keeps payload light) |
| `GET /articles/{id}` | Single article including `full_text` |
| `GET /search?q=...` | FTS5 BM25-ranked results, capped at 50 |
| `POST /inbound-email` | (planned) Mailgun/Postmark webhook for regulator emails |

CORS restricted to `uadvance.com.au` and `www.uadvance.com.au`.

**Environment variables (set in Railway):**
- `DB_PATH=/data/uadvance.db`
- `OPENAI_API_KEY=...` (for any server-side OpenAI calls; never put in frontend)
- MSAL credentials if/when pipeline moves server-side

---

## 9. Frontend (`news.html`)

Single file. Three-panel desktop layout: sidebar (filters + article list) | article view | chat panel. No mobile layout yet.

**Two distinct search modes — don't confuse them:**

1. **Frontend filter/search** — runs in the browser against the in-memory `allArticles` array. Matches `title`, `summary`, `publication`, `heading`, and `full_text` *only if those fields have been loaded*. Since `/articles` omits `full_text` to keep the payload light, full-text matching in this mode only works for articles whose full text has been fetched (e.g. ones the user has opened).
2. **Backend search** — `GET /search?q=...` runs SQLite FTS5 with BM25 ranking across `title`, `summary`, and `full_text` for *every* article in the DB. Capped at 50 results.

When you need real full-text search, use the backend endpoint — it's authoritative.

**Other things to know:**
- Password gate is a JS overlay with a hardcoded password — see Security Notes
- On init: `fetch(API_BASE + '/articles')`, falls back to `articles_index.json` if API is down
- `applyFilters()` is the central function for in-browser filtering
- Chat panel is currently single-turn (no history sent to OpenAI) — known limitation
- `API_BASE = 'https://uadvance-production.up.railway.app'` — leave this alone

---

## 10. Daily Operations Workflow

Until the pipeline is automated server-side, every "publish new articles" cycle is:

```bash
cd /Users/david/GitHub/uAdvance

# 0. Back up the current local DB — one-command rollback if anything goes wrong
cp uadvance.db uadvance.db.bak

# 1. Ingest
python dowjones-news-bot/extract_article_links.py
python dowjones-news-bot/extract_article_content_2.py
python dowjones-news-bot/fetch_regulators.py

# 2. Summarise
python dowjones-news-bot/summarise3.py

# 3. Push DB to Railway
railway volume files upload uadvance.db /data/uadvance.db --overwrite

# 4. Verify production is reading the new file (belt-and-braces)
curl https://uadvance-production.up.railway.app/articles | head -c 500
```

The `curl` check confirms the API is up and serving data. Look at the newest article date to make sure your changes are actually live.

**Rolling back a bad upload:**

If a bad upload breaks the site, re-upload the backup:
```bash
railway volume files upload uadvance.db.bak /data/uadvance.db --overwrite
```
One command, back to the previous good state.

**Code changes** are separate — they go via `git push`, Railway auto-deploys from the `backend/` folder. **Data changes ≠ code changes.** Pushing code does not update the database; uploading the DB does not redeploy code.

---

## 11. Security Notes

Be honest about where the system stands:

- **The password gate is obscurity, not access control.** Anyone who can view the page source can find or bypass it. Do not put commercially or legally sensitive content behind it expecting real protection.
- **No real auth yet.** All requests to the API are unauthenticated. Anyone who knows the Railway URL can hit `/articles`. The deterrent is that the URL isn't widely shared, not that the API enforces anything.
- **Secrets live in Railway environment variables, not in code or frontend JS.** Exposing the OpenAI key in browser JavaScript would let anyone view-source it and use your account.
- **Tighten before any commercial launch.** Real login, signed sessions, rate limiting, and (likely) per-user article access controls all need to exist before users pay or sensitive data is involved.

---

## 12. Key Design Decisions (the "why")

- **SQLite over Postgres** — single-user, single-file, zero server cost; FTS5 is excellent for this scale. Migrate later only if multi-user write contention becomes real.
- **FTS5 with content-based virtual table** — full-text search without a separate search service. Triggers keep it in sync automatically.
- **Frontend stays on GitHub Pages** — free, fast, no server to maintain. Backend is the only thing that costs money.
- **`articles_index.json` fallback retained** — the site keeps working even if Railway is down. Remove only when the API is proven stable.
- **`INSERT OR IGNORE` everywhere in the pipeline** — re-runs are safe, no duplicate articles.
- **Regulator articles run through the same summariser as Dow Jones** — one pipeline, tagged differently via `source` / `is_regulator` / `category`.
- **OpenAI API key lives on Railway, never frontend** — exposing a key in browser JS would mean anyone could view-source and steal it.
- **Mobile-friendly happens *before* the next wave of complex UI** (side menu, save/tag/read states). Not the very next task, but slotted in before any feature-heavy interactive components — retrofitting responsive design over those later is much harder than building it in alongside.

---

## 13. Known Limitations

What's deliberately not solved yet (distinct from the backlog — these are accepted current-state realities, not next-up tasks):

- **Auth is not secure** — password gate is obscurity only
- **Pipeline depends on the local laptop** — if it's off, no new articles
- **DB upload is manual** — every publish is a CLI command
- **No user accounts or audit trail** — no one is identified, nothing is logged per-user
- **No automated backup/restore** — `.bak` discipline is up to you
- **Licensing for redistribution is unresolved** — fine for private personal use, not yet evaluated for any commercial scenario
- **Chat is single-turn** — no conversation history is sent back to OpenAI on follow-ups
- **`articles_index.json` can drift from the DB** — it's written at the end of `summarise3.py` and won't reflect anything added to the DB after that

---

## 14. Backlog (rough priority order)

1. **Login system** — needed before any per-user features
2. **Save/tag articles** — schema (`tags`, `article_tags`) is ready, needs UI + auth
3. **Mobile-friendly pass** — before the side menu and other interactive UI gets built
4. **Subscriptions + payments** — Stripe, gated by login
5. **Automate the daily pipeline on Railway** — currently runs locally
6. **Regulator email webhook** — Mailgun/Postmark → `/inbound-email` so APRA/ASIC updates land in the DB without manual fetching
7. **Multi-turn chat** — currently each question is sent without history
8. **Automated DB backups** — versioned snapshots rather than ad-hoc `.bak` files
9. **Remove `articles_index.json` fallback** — once the API has proven stable over weeks

---

## 15. Common Gotchas

- **Path depth in scripts.** Scripts live in `dowjones-news-bot/` which is one level inside the repo, so `PROJECT_ROOT = SCRIPT_DIR.parent` (not `.parent.parent`).
- **Railway env vars.** When adding variables in the Railway UI, the **name** goes in the left field and the **value** goes in the right — not as two separate variables called `Key` and `Value`.
- **Browser cache during dev.** Hard refresh doesn't always hit sub-resource JSON. Keep DevTools open with "Disable cache" ticked while editing.
- **Railway deployments cache.** If an env var change isn't taking effect, force a clean redeploy (`railway redeploy`).
- **The DB on Railway and the DB locally are separate files.** Local changes don't appear on the site until you run the `railway volume files upload` command.

---

## 16. Never Commit

Anything in this list goes in `.gitignore` and stays out of the repo:

- `.env` files
- `msal_token_cache.json`
- OpenAI API keys
- MSAL client IDs/secrets
- Railway tokens
- Local browser/session profiles (Playwright user data dirs etc.)
- Downloaded full article text if licensing ever becomes a concern
- Any `.db` file containing real production data, if the repo ever becomes public

Run `git status` before every commit. If you see something secret-looking in the staged files, stop.

---

## 17. How to Use This Document with an LLM

When asking for help on a change:

1. Paste the relevant section(s) of this doc (e.g. "Database Schema" + "Backend API")
2. Paste only the specific function or block of code you want changed — not the whole file
3. State the change plainly: "In `extract_article_content_2.py`, in `save_article_to_db()`, also store `published_date` parsed as ISO format."
4. Ask the LLM to output a diff or before/after, not a rewritten file
5. Read what changed before applying it

The principle: the LLM doesn't need the whole codebase — it needs enough context to be confident about *this change*.

---

**Last updated:** 2026-05-27
**Owner:** David
**Status:** private / single-user prototype

*When you make a structural change (new table, new endpoint, new script, new design decision), update the matching section above before moving on.*
