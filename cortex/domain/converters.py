from __future__ import annotations

from datetime import datetime

from cortex.domain.models import Checkpoint, Decision, Message, Stream, Update


def doc_to_stream(doc: dict) -> Stream:
    return Stream(
        id=doc["_id"],
        title=doc["title"],
        name=doc.get("name", ""),
        repos=doc.get("repos", []),
        status=doc["status"],
        summary=doc.get("summary"),
        created_at=datetime.fromisoformat(doc["created_at"]),
        updated_at=datetime.fromisoformat(doc["updated_at"]),
        metadata=doc.get("metadata"),
    )


def doc_to_update(doc: dict) -> Update:
    return Update(
        id=doc["_id"],
        stream_id=doc["stream_id"],
        content=doc["content"],
        summary=doc["summary"],
        created_at=datetime.fromisoformat(doc["created_at"]),
        metadata=doc.get("metadata"),
    )


def doc_to_decision(doc: dict) -> Decision:
    return Decision(
        id=doc["_id"],
        stream_id=doc["stream_id"],
        what=doc["what"],
        why=doc["why"],
        created_at=datetime.fromisoformat(doc["created_at"]),
        metadata=doc.get("metadata"),
    )


def doc_to_checkpoint(doc: dict) -> Checkpoint:
    return Checkpoint(
        id=doc["_id"],
        week_of=doc["week_of"],
        content=doc["content"],
        stream_ids=doc.get("stream_ids", []),
        created_at=datetime.fromisoformat(doc["created_at"]),
        updated_at=datetime.fromisoformat(doc["updated_at"]),
        metadata=doc.get("metadata"),
    )


def doc_to_message(doc: dict) -> Message:
    return Message(
        id=doc["_id"],
        sender=doc["from"],
        recipient=doc["to"],
        content=doc.get("content", ""),
        status=doc.get("status", "pending"),
        created_at=doc.get("created_at", ""),
        meta=doc.get("meta", {}),
        delivered_at=doc.get("delivered_at"),
    )
