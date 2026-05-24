"""
migrate_add_regulator_columns.py
──────────────────────────────────────────────────────────────────────────────
One-time migration: adds regulator columns to your existing uadvance.db.

Run once from your project root:
    python migrate_add_regulator_columns.py

Safe to re-run — checks if each column already exists before adding it,
so it will never break or duplicate anything.

NEW COLUMNS ADDED TO articles
──────────────────────────────
  is_regulator       INTEGER DEFAULT 0   — quick filter flag (0 = news, 1 = regulator release)
  regulator_name     TEXT                — short code e.g. "RBA", "ASIC", "APRA"
  regulator_full_name TEXT               — display name e.g. "Reserve Bank of Australia"
  source_type        TEXT DEFAULT 'newsletter'  — 'newsletter' | 'rss' | 'scraped'

NEW INDEXES
───────────
  idx_articles_is_regulator   — fast filtering by regulator flag
  idx_articles_regulator_name — fast filtering by specific regulator
  idx_articles_source_type    — fast filtering by source
"""

import sqlite3
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Points to uadvance.db at the project root (same logic as your other scripts).

SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR  # run from project root, or adjust if needed
DB_PATH      = PROJECT_ROOT / "uadvance.db"

# ── MIGRATION ─────────────────────────────────────────────────────────────────

NEW_COLUMNS = [
    # (column_name, column_definition)
    ("is_regulator",        "INTEGER DEFAULT 0"),
    ("regulator_name",      "TEXT"),
    ("regulator_full_name", "TEXT"),
    ("source_type",         "TEXT DEFAULT 'newsletter'"),
]

NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_articles_is_regulator   ON articles(is_regulator);",
    "CREATE INDEX IF NOT EXISTS idx_articles_regulator_name ON articles(regulator_name);",
    "CREATE INDEX IF NOT EXISTS idx_articles_source_type    ON articles(source_type);",
]


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names that already exist in a table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}  # column name is index 1


def migrate(db_path: Path):
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        print("Run init_db.py first, then run this migration.")
        raise SystemExit(1)

    print(f"Database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    existing = get_existing_columns(conn, "articles")
    print(f"Existing columns in articles: {len(existing)} found\n")

    added = []
    skipped = []

    for col_name, col_def in NEW_COLUMNS:
        if col_name in existing:
            print(f"  ↷  Skipping  '{col_name}' — already exists")
            skipped.append(col_name)
        else:
            sql = f"ALTER TABLE articles ADD COLUMN {col_name} {col_def};"
            conn.execute(sql)
            print(f"  ✓  Added     '{col_name}  {col_def}'")
            added.append(col_name)

    print()
    print("Creating indexes...")
    for idx_sql in NEW_INDEXES:
        conn.execute(idx_sql)
        # Extract index name for display
        idx_name = idx_sql.split("IF NOT EXISTS ")[1].split(" ON ")[0]
        print(f"  ✓  {idx_name}")

    conn.commit()
    conn.close()

    print()
    print("=" * 60)
    print(f"Migration complete.")
    print(f"  Columns added:   {len(added)}  {added if added else ''}")
    print(f"  Columns skipped: {len(skipped)}  (already existed)")
    print()
    print("Next step: run fetch_regulators.py to start importing regulator releases.")


if __name__ == "__main__":
    migrate(DB_PATH)
