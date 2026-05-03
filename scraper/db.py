"""MongoDB helpers shared by the scraper modules."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.database import Database


def get_database() -> Database:
    mongo_uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "obituary_api")

    if not mongo_uri:
        raise RuntimeError("MONGODB_URI is required")

    client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=12000,
        retryWrites=True,
    )
    client.admin.command("ping")
    return client[db_name]


def obituaries_collection(db: Database) -> Collection:
    return db["obituaries"]


def trends_collection(db: Database) -> Collection:
    return db["trending_keywords"]


def ensure_indexes(db: Database) -> None:
    obits = obituaries_collection(db)
    obits.create_index([("slug", ASCENDING)], unique=True, background=True)
    obits.create_index([("hash", ASCENDING)], unique=True, background=True)
    obits.create_index([("created_at", DESCENDING)], background=True)
    obits.create_index([("name", "text"), ("title", "text"), ("content", "text")], background=True)

    trends = trends_collection(db)
    trends.create_index([("keyword", ASCENDING)], unique=True, background=True)
    trends.create_index([("last_seen_at", DESCENDING)], background=True)


def save_obituaries(db: Database, documents: Iterable[dict[str, Any]]) -> int:
    now = datetime.now(timezone.utc)
    operations: list[UpdateOne] = []

    for doc in documents:
        doc.setdefault("created_at", now)
        doc.setdefault("updated_at", now)
        operations.append(
            UpdateOne(
                {"hash": doc["hash"]},
                {
                    "$setOnInsert": doc,
                    "$set": {"updated_at": now},
                },
                upsert=True,
            )
        )

    if not operations:
        return 0

    result = obituaries_collection(db).bulk_write(operations, ordered=False)
    return int(result.upserted_count)


def save_keywords(db: Database, keywords: Iterable[str]) -> None:
    now = datetime.now(timezone.utc)
    operations = [
        UpdateOne(
            {"keyword": keyword},
            {
                "$set": {"last_seen_at": now},
                "$setOnInsert": {"keyword": keyword, "created_at": now},
                "$inc": {"seen_count": 1},
            },
            upsert=True,
        )
        for keyword in keywords
    ]
    if operations:
        trends_collection(db).bulk_write(operations, ordered=False)


def recently_seen_keywords(db: Database, limit: int = 100) -> set[str]:
    cursor = trends_collection(db).find({}, {"keyword": 1}).sort("last_seen_at", DESCENDING).limit(limit)
    return {doc["keyword"] for doc in cursor if doc.get("keyword")}
