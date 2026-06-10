#!/bin/bash
# run_pipeline.sh
# ─────────────────────────────────────────────────────────────
# Runs the full uAdvance news pipeline then uploads the updated
# database to Railway.
#
# Usage (from /Users/david/GitHub/uAdvance):
#   bash run_pipeline.sh
# ─────────────────────────────────────────────────────────────

set -e  # stop immediately if any step fails

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/dowjones-news-bot/.venv/bin/python"

echo "═══════════════════════════════════════════"
echo "  uAdvance pipeline — $(date '+%Y-%m-%d %H:%M')"
echo "═══════════════════════════════════════════"

echo ""
echo "▶  Step 1/5 — Extract article links"
"$PYTHON" "$SCRIPT_DIR/dowjones-news-bot/extract_article_links.py"

echo ""
echo "▶  Step 2/5 — Extract article content"
"$PYTHON" "$SCRIPT_DIR/dowjones-news-bot/extract_article_content.py"

echo ""
echo "▶  Step 3/5 — Extract regulator emails"
"$PYTHON" "$SCRIPT_DIR/dowjones-news-bot/extract_regulator_emails.py"

echo ""
echo "▶  Step 4/5 — Summarise"
"$PYTHON" "$SCRIPT_DIR/dowjones-news-bot/summarise.py"

echo ""
echo "▶  Step 5/5 — Upload to Railway"
cd "$SCRIPT_DIR"
echo "  Checkpointing WAL..."
sqlite3 uadvance.db "PRAGMA wal_checkpoint(TRUNCATE);"
railway volume files upload uadvance.db /data/uadvance.db --overwrite

echo ""
echo "═══════════════════════════════════════════"
echo "  Done."
echo "═══════════════════════════════════════════"