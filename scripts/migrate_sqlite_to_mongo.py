#!/usr/bin/env python3
"""One-time migration: SQLite state.db -> MongoDB collections.

Usage:
    uv run python scripts/migrate_sqlite_to_mongo.py [--db-path PATH]

Idempotent — uses upsert so safe to re-run.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from cortex.mongo import get_db


def migrate(sqlite_path: Path) -> None:
    if not sqlite_path.exists():
        print(f"SQLite DB not found at {sqlite_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row

    db = get_db()
    counts: dict[str, int] = {}

    # Streams
    rows = conn.execute("SELECT * FROM streams").fetchall()
    for row in rows:
        doc = {
            "_id": row["id"],
            "title": row["title"],
            "repos": json.loads(row["repos"]),
            "status": row["status"],
            "summary": row["summary"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        db["streams"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    counts["streams"] = len(rows)

    # Updates
    rows = conn.execute("SELECT * FROM updates").fetchall()
    for row in rows:
        metadata = None
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
        except (json.JSONDecodeError, KeyError):
            pass
        doc = {
            "_id": row["id"],
            "stream_id": row["stream_id"],
            "content": row["content"],
            "summary": row["summary"],
            "metadata": metadata,
            "created_at": row["created_at"],
        }
        db["updates"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    counts["updates"] = len(rows)

    # Decisions
    rows = conn.execute("SELECT * FROM decisions").fetchall()
    for row in rows:
        metadata = None
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
        except (json.JSONDecodeError, KeyError):
            pass
        doc = {
            "_id": row["id"],
            "stream_id": row["stream_id"],
            "what": row["what"],
            "why": row["why"],
            "metadata": metadata,
            "created_at": row["created_at"],
        }
        db["decisions"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    counts["decisions"] = len(rows)

    # Checkpoints
    rows = conn.execute("SELECT * FROM checkpoints").fetchall()
    for row in rows:
        metadata = None
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
        except (json.JSONDecodeError, KeyError):
            pass
        doc = {
            "_id": row["id"],
            "week_of": row["week_of"],
            "content": row["content"],
            "stream_ids": json.loads(row["stream_ids"]) if row["stream_ids"] else [],
            "metadata": metadata,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        db["checkpoints"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    counts["checkpoints"] = len(rows)

    # Sessions (stream links) — deduplicate by (session_id, stream_id)
    rows = conn.execute("SELECT * FROM sessions").fetchall()
    seen_pairs: set[tuple[str, str]] = set()
    skipped = 0
    for row in rows:
        pair = (row["session_id"], row["stream_id"])
        if pair in seen_pairs:
            skipped += 1
            continue
        seen_pairs.add(pair)
        doc = {
            "_id": row["id"],
            "session_id": row["session_id"],
            "stream_id": row["stream_id"],
            "repo": row["repo"],
            "branch": row["branch"],
            "status": row["status"],
            "last_summary": row["last_summary"],
            "created_at": row["created_at"],
        }
        try:
            db["stream_sessions"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
        except Exception:
            skipped += 1
    counts["stream_sessions"] = len(rows) - skipped
    if skipped:
        print(f"  (skipped {skipped} duplicate session links)")

    # Dashboard blueprints
    rows = conn.execute("SELECT * FROM dashboard_blueprints").fetchall()
    for row in rows:
        doc = {
            "_id": row["id"],
            "blueprint": json.loads(row["blueprint"]),
            "resolved_data": json.loads(row["resolved_data"]) if row["resolved_data"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        db["dashboard_blueprints"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    counts["dashboard_blueprints"] = len(rows)

    # Dashboard snapshots
    rows = conn.execute("SELECT * FROM dashboard_snapshots").fetchall()
    for row in rows:
        doc = {
            "_id": row["id"],
            "snapshot_type": row["snapshot_type"],
            "data": json.loads(row["data"]),
            "created_at": row["created_at"],
        }
        db["dashboard_snapshots"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    counts["dashboard_snapshots"] = len(rows)

    conn.close()

    print("Migration complete:")
    for collection, count in counts.items():
        print(f"  {collection}: {count} documents")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Cortex SQLite to MongoDB")
    parser.add_argument("--db-path", default="~/.cortex/state.db", help="Path to SQLite state.db")
    args = parser.parse_args()

    migrate(Path(args.db_path).expanduser())
