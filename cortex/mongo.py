from __future__ import annotations

import os

from pymongo import MongoClient
from pymongo.database import Database

_client: MongoClient | None = None

MONGO_URI = os.environ.get("CORTEX_MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("CORTEX_MONGO_DB", "cortex")


def get_db() -> Database:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client[MONGO_DB]


def close() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
