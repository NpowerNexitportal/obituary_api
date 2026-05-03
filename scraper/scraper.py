"""Entrypoint for the independent obituary content collector."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from db import ensure_indexes, get_database, recently_seen_keywords, save_keywords, save_obituaries
from parser import collect_from_keywords
from rewriter import enrich_record
from trends import fetch_trending_keywords

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
LOGGER = logging.getLogger("scraper")


def main() -> int:
    load_dotenv()
    db = get_database()
    ensure_indexes(db)

    seen = recently_seen_keywords(db)
    keywords = fetch_trending_keywords(exclude=seen)
    if not keywords:
        keywords = fetch_trending_keywords(exclude=set())

    LOGGER.info("Collecting from keywords: %s", ", ".join(keywords))
    save_keywords(db, keywords)

    extracted = collect_from_keywords(keywords)
    enriched = [enrich_record(record) for record in extracted]
    inserted = save_obituaries(db, enriched)

    LOGGER.info("Extracted=%s inserted=%s", len(extracted), inserted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
