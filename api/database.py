"""Async MongoDB connection utilities for the API."""

from __future__ import annotations

import os
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase


@lru_cache
def get_client() -> AsyncIOMotorClient:
    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        raise RuntimeError("MONGODB_URI is required")
    return AsyncIOMotorClient(
        mongo_uri,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
        retryWrites=True,
    )


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[os.getenv("MONGODB_DB", "obituary_api")]


def obituaries_collection() -> AsyncIOMotorCollection:
    return get_database()["obituaries"]


def trends_collection() -> AsyncIOMotorCollection:
    return get_database()["trending_keywords"]
