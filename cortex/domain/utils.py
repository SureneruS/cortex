from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _new_msg_id() -> str:
    return "msg_" + uuid.uuid4().hex[:16]


def _slugify(title: str, max_length: int = 50) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:max_length].rstrip("-")
