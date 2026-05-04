"""Fetch obituary/death trend keywords without browser automation."""

from __future__ import annotations

import logging
import os
import random
from typing import Iterable
from urllib.parse import quote_plus

import requests

LOGGER = logging.getLogger(__name__)

SEEDS = ("obituary", "death")
DEFAULT_KEYWORDS = (
    "recent obituary",
    "who passed away today obituary",
    "death news today",
    "death notice today",
    "funeral obituary notices",
    "local obituary passed away",
    "celebrity obituary today",
    "death notice obituary",
)


def _clean_keyword(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _google_suggest(seed: str, session: requests.Session) -> list[str]:
    url = (
        "https://suggestqueries.google.com/complete/search"
        f"?client=firefox&gl=us&hl=en&q={quote_plus(seed)}"
    )
    response = session.get(url, timeout=10)
    response.raise_for_status()
    payload = response.json()
    return [_clean_keyword(item) for item in payload[1] if isinstance(item, str)]


def _pytrends_related(seed: str) -> list[str]:
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return []

    try:
        trend = TrendReq(hl="en-US", tz=360, timeout=(5, 15), retries=1, backoff_factor=0.2)
        trend.build_payload([seed], cat=0, timeframe="now 7-d", geo="US", gprop="")
        related = trend.related_queries()
        rows = related.get(seed, {}).get("rising")
        if rows is None:
            return []
        return [_clean_keyword(str(value)) for value in rows["query"].head(10).tolist()]
    except Exception as exc:
        LOGGER.warning("pytrends failed for %s: %s", seed, exc)
        return []


def fetch_trending_keywords(max_keywords: int | None = None, exclude: Iterable[str] = ()) -> list[str]:
    """Return 5-10 obituary/death keywords from Google Trends-style sources."""

    max_keywords = max_keywords or int(os.getenv("MAX_KEYWORDS_PER_RUN", "8"))
    max_keywords = max(1, min(max_keywords, 10))
    excluded = {_clean_keyword(value) for value in exclude}
    candidates: list[str] = []
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": os.getenv(
                "SCRAPER_USER_AGENT",
                "Mozilla/5.0 (compatible; ObituaryContentCollector/1.0; +https://example.com/bot)",
            )
        }
    )

    for seed in SEEDS:
        candidates.extend(_pytrends_related(seed))
        try:
            candidates.extend(_google_suggest(seed, session))
        except Exception as exc:
            LOGGER.warning("Google suggest failed for %s: %s", seed, exc)

    candidates.extend(DEFAULT_KEYWORDS)
    filtered: list[str] = []
    for keyword in candidates:
        cleaned = _clean_keyword(keyword)
        if not cleaned or cleaned in excluded or cleaned in filtered:
            continue
        if any(term in cleaned for term in ("obituary", "death", "passed away", "rip", "funeral")):
            filtered.append(cleaned)

    if len(filtered) < max_keywords:
        for keyword in DEFAULT_KEYWORDS:
            cleaned = _clean_keyword(keyword)
            if cleaned not in filtered:
                filtered.append(cleaned)

    random.shuffle(filtered)
    return filtered[:max_keywords]
