from __future__ import annotations

import json
import sys
from pathlib import Path

COMPACT_SUMMARY_PREFIX = "This session is being continued"


def _parse_records(transcript_path: Path) -> list[dict]:
    records = []
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return records


def _extract_message_content(record: dict) -> str | None:
    try:
        content = record["message"]["content"]
    except (KeyError, TypeError):
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else None
    return None


def extract_compact_summaries(transcript_path: Path) -> list[dict]:
    records = _parse_records(transcript_path)
    summaries = []
    i = 0
    while i < len(records):
        rec = records[i]
        if rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
            metadata = rec.get("compactMetadata", {})
            trigger = metadata.get("trigger")
            pre_tokens = metadata.get("preTokens")
            timestamp = rec.get("timestamp")

            j = i + 1
            while j < len(records):
                next_rec = records[j]
                if next_rec.get("type") == "file-history-snapshot":
                    j += 1
                    continue
                if next_rec.get("type") == "user":
                    content = _extract_message_content(next_rec)
                    if content and content.startswith(COMPACT_SUMMARY_PREFIX):
                        summaries.append({
                            "trigger": trigger,
                            "pre_tokens": pre_tokens,
                            "timestamp": timestamp,
                            "content": content,
                        })
                break
            i = j + 1 if j < len(records) else i + 1
        else:
            i += 1
    return summaries


def extract_post_compact_messages(transcript_path: Path) -> list[dict]:
    records = _parse_records(transcript_path)

    last_boundary_idx = None
    for i, rec in enumerate(records):
        if rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
            last_boundary_idx = i

    if last_boundary_idx is None:
        return []

    messages = []
    skipped_summary = False
    for rec in records[last_boundary_idx + 1 :]:
        if rec.get("type") == "file-history-snapshot":
            continue
        role = rec.get("type")
        if role not in ("user", "assistant"):
            continue
        content = _extract_message_content(rec)
        if content is None:
            continue
        if not skipped_summary and role == "user" and content.startswith(COMPACT_SUMMARY_PREFIX):
            skipped_summary = True
            continue
        messages.append({"role": role, "content": content})
    return messages


def main():
    if len(sys.argv) < 3:
        print("Usage: nova-transcripts <list-summaries|post-compact> <path>", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    path = Path(sys.argv[2])

    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    if command == "list-summaries":
        result = extract_compact_summaries(path)
    elif command == "post-compact":
        result = extract_post_compact_messages(path)
    else:
        print(f"Unknown command: {command}. Use 'list-summaries' or 'post-compact'.", file=sys.stderr)
        sys.exit(1)

    json.dump(result, sys.stdout, indent=2)
    print()
