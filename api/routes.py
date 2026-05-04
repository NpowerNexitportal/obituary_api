"""REST API routes. Scraping is intentionally kept out of this layer."""

from __future__ import annotations

import re

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pymongo import DESCENDING

from .database import obituaries_collection, trends_collection
from .models import Obituary, ObituaryList, TrendingKeyword, serialize_document

router = APIRouter(prefix="/api", tags=["obituaries"])


def _page_params(page: int, limit: int) -> tuple[int, int, int]:
    page = max(page, 1)
    limit = min(max(limit, 1), 50)
    skip = (page - 1) * limit
    return page, limit, skip


@router.api_route("/obituaries", methods=["GET", "HEAD"], response_model=ObituaryList)
async def latest_obituaries(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
) -> ObituaryList:
    page, limit, skip = _page_params(page, limit)
    collection = obituaries_collection()
    cursor = collection.find({}).sort("created_at", DESCENDING).skip(skip).limit(limit)
    items = [Obituary.model_validate(serialize_document(doc)) async for doc in cursor]
    total = await collection.count_documents({})
    return ObituaryList(page=page, limit=limit, total=total, items=items)


@router.api_route("/obituaries/{id_or_slug}", methods=["GET", "HEAD"], response_model=Obituary)
async def single_obituary(id_or_slug: str) -> Obituary:
    collection = obituaries_collection()
    query = {"slug": id_or_slug}
    if ObjectId.is_valid(id_or_slug):
        query = {"$or": [{"_id": ObjectId(id_or_slug)}, {"slug": id_or_slug}]}

    document = await collection.find_one(query)
    if not document:
        raise HTTPException(status_code=404, detail="Obituary not found")
    return Obituary.model_validate(serialize_document(document))


@router.api_route("/search", methods=["GET", "HEAD"], response_model=ObituaryList)
async def search_obituaries(
    q: str = Query(..., min_length=2, max_length=80),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
) -> ObituaryList:
    page, limit, skip = _page_params(page, limit)
    collection = obituaries_collection()
    query: dict
    if re.match(r"^[\w\s.'-]+$", q):
        query = {"$text": {"$search": q}}
        cursor = collection.find(query, {"score": {"$meta": "textScore"}}).sort(
            [("score", {"$meta": "textScore"}), ("created_at", DESCENDING)]
        )
    else:
        safe = re.escape(q)
        query = {"$or": [{"name": {"$regex": safe, "$options": "i"}}, {"title": {"$regex": safe, "$options": "i"}}]}
        cursor = collection.find(query).sort("created_at", DESCENDING)

    cursor = cursor.skip(skip).limit(limit)
    items = [Obituary.model_validate(serialize_document(doc)) async for doc in cursor]
    total = await collection.count_documents(query)
    return ObituaryList(page=page, limit=limit, total=total, items=items)


@router.api_route("/trending", methods=["GET", "HEAD"], response_model=list[TrendingKeyword])
async def trending_keywords(limit: int = Query(10, ge=1, le=50)) -> list[TrendingKeyword]:
    cursor = trends_collection().find({}).sort("last_seen_at", DESCENDING).limit(limit)
    return [TrendingKeyword.model_validate(doc) async for doc in cursor]
