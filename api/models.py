"""Pydantic response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Obituary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    name: str
    title: str
    slug: str
    content: str
    meta_description: str
    date_of_death: str | None = None
    location: str | None = None
    source_url: str
    created_at: datetime
    hash: str


class ObituaryList(BaseModel):
    page: int
    limit: int
    total: int
    items: list[Obituary]


class TrendingKeyword(BaseModel):
    keyword: str
    seen_count: int = 0
    last_seen_at: datetime | None = None


def serialize_document(document: dict[str, Any]) -> dict[str, Any]:
    document = dict(document)
    document["_id"] = str(document["_id"])
    return document
