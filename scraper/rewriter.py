"""Respectful rewrite and SEO enrichment for obituary records."""

from __future__ import annotations

import os
import re
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency path
    OpenAI = None


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:90] or "obituary"


def _fallback_article(record: dict[str, Any]) -> str:
    name = record["name"]
    location = record.get("location")
    date_of_death = record.get("date_of_death")

    intro_bits = [f"{name} passed away"]
    if date_of_death:
        intro_bits.append(f"on {date_of_death}")
    if location:
        intro_bits.append(f"and was connected with the {location} community")
    intro = " ".join(intro_bits) + "."

    paragraphs = [
        intro,
        (
            f"This obituary update is prepared from public source information for readers looking for "
            f"respectful remembrance details, funeral context, and verified notices about the person who "
            f"has passed away."
        ),
        (
            f"At times like this, family members, friends, and neighbors may use an obituary to share "
            f"memories, confirm memorial information, and honor {name}'s life with care."
        ),
        (
            "Readers should consult the linked source for the latest funeral arrangements, official "
            "family announcements, memorial updates, and any changes to service information."
        ),
    ]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _ai_article(record: dict[str, Any]) -> str | None:
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return None

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = (
        "Rewrite the following obituary source summary into a unique, respectful, SEO-friendly article. "
        "Do not invent facts, relatives, service dates, or causes of death. Use the keywords obituary, "
        "passed away, and funeral naturally. Keep the tone human and concise.\n\n"
        f"Name: {record.get('name')}\n"
        f"Date of death: {record.get('date_of_death') or 'Unknown'}\n"
        f"Location: {record.get('location') or 'Unknown'}\n"
        f"Source summary: {record.get('summary')}\n"
        f"Source URL: {record.get('source_url')}"
    )
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=prompt,
        max_output_tokens=650,
    )
    text = response.output_text.strip()
    return text or None


def enrich_record(record: dict[str, Any]) -> dict[str, Any]:
    name = record["name"]
    location = record.get("location")
    date_of_death = record.get("date_of_death")
    title_parts = [f"{name} Obituary"]
    if location:
        title_parts.append(location)
    if date_of_death:
        title_parts.append(str(date_of_death)[:4])

    title = " - ".join(title_parts)
    content = _ai_article(record) or _fallback_article(record)
    meta_location = f" in {location}" if location else ""
    meta_description = (
        f"Read the obituary for {name}{meta_location}. Respectful update with passed away notice, "
        "funeral context, and source information."
    )[:155]

    enriched = dict(record)
    enriched.update(
        {
            "title": title,
            "slug": slugify(title),
            "content": content,
            "meta_description": meta_description,
        }
    )
    return enriched
