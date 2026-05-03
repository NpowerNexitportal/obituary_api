"""Search-result scraping and obituary field extraction."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
DATE_RE = re.compile(
    rf"\b(?:{'|'.join(MONTHS)})\s+\d{{1,2}},\s+\d{{4}}\b|\b\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"\b(?:obituary for|in memory of|remembering|celebrating the life of)\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})",
    re.IGNORECASE,
)
LOCATION_RE = re.compile(
    r"\b(?:of|from|in)\s+([A-Z][A-Za-z.' -]+,\s+[A-Z]{2}|[A-Z][A-Za-z.' -]+,\s+[A-Z][A-Za-z.' -]+)\b"
)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; ObituaryContentCollector/1.0; respectful scraping)",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def search_obituary_results(keyword: str, limit: int = 4) -> list[SearchResult]:
    """Scrape lightweight DuckDuckGo HTML search results for source pages."""

    url = f"https://duckduckgo.com/html/?q={quote_plus(keyword + ' obituary')}&kl=us-en"
    session = _session()
    response = session.get(url, timeout=12)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results: list[SearchResult] = []

    for result in soup.select(".result")[: limit * 2]:
        link = result.select_one(".result__a")
        snippet = result.select_one(".result__snippet")
        if not link or not link.get("href"):
            continue
        href = _unwrap_duckduckgo_url(link["href"])
        if not href.startswith(("http://", "https://")):
            continue
        title = link.get_text(" ", strip=True)
        text = snippet.get_text(" ", strip=True) if snippet else ""
        results.append(SearchResult(title=title, url=href, snippet=text))
        if len(results) >= limit:
            break

    return results


def _unwrap_duckduckgo_url(href: str) -> str:
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    return href


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "header"]):
        tag.decompose()

    article = soup.find("article") or soup.find("main") or soup.body or soup
    text = article.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def _meta_content(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _extract_name(title: str, text: str) -> str | None:
    candidates = [title, text[:900]]
    for candidate in candidates:
        match = NAME_RE.search(candidate)
        if match:
            return _titlecase_name(match.group(1))

    title_clean = re.sub(r"\b(obituary|death notice|funeral|passed away|rip)\b", "", title, flags=re.I)
    title_clean = re.split(r"[-|:]", title_clean)[0]
    words = re.findall(r"\b[A-Z][A-Za-z.'-]+\b", title_clean)
    if 2 <= len(words) <= 5:
        return _titlecase_name(" ".join(words))
    return None


def _titlecase_name(name: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in name.split()).strip(" ,.-")


def _extract_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    raw = match.group(0)
    for fmt in ("%B %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def _extract_location(text: str) -> str | None:
    match = LOCATION_RE.search(text[:1500])
    if not match:
        return None
    return match.group(1).strip(" .,")


def _summary(text: str, fallback: str) -> str:
    source = text if len(text) > 240 else fallback
    sentences = re.split(r"(?<=[.!?])\s+", source)
    selected = [sentence.strip() for sentence in sentences if len(sentence.strip()) > 40][:4]
    return " ".join(selected)[:1400].strip()


def _content_hash(name: str, date_of_death: str | None, summary: str, source_url: str) -> str:
    normalized = f"{name.lower()}|{date_of_death or ''}|{summary[:500].lower()}|{source_url}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fetch_and_extract(result: SearchResult) -> dict[str, str] | None:
    """Fetch one source page and extract conservative obituary fields."""

    session = _session()
    try:
        response = session.get(result.url, timeout=12)
        response.raise_for_status()
    except Exception as exc:
        LOGGER.warning("Could not fetch %s: %s", result.url, exc)
        return None

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    page_title = (_meta_content(soup, "og:title", "twitter:title") or result.title).strip()
    description = _meta_content(soup, "description", "og:description", "twitter:description") or result.snippet
    text = _visible_text(response.text)
    combined = f"{page_title}. {description}. {text}"

    if not any(term in combined.lower() for term in ("obituary", "passed away", "funeral", "death notice")):
        return None

    name = _extract_name(page_title, combined)
    summary = _summary(text, description)
    if not name or len(summary) < 80:
        return None

    date_of_death = _extract_date(combined)
    location = _extract_location(combined)
    published = response.headers.get("last-modified")
    if published:
        try:
            parsedate_to_datetime(published)
        except (TypeError, ValueError):
            pass

    return {
        "name": name,
        "date_of_death": date_of_death,
        "location": location,
        "summary": summary,
        "source_url": result.url,
        "hash": _content_hash(name, date_of_death, summary, result.url),
    }


def collect_from_keywords(keywords: Iterable[str], per_keyword: int = 3) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for keyword in keywords:
        try:
            results = search_obituary_results(keyword, limit=per_keyword)
        except Exception as exc:
            LOGGER.warning("Search failed for %s: %s", keyword, exc)
            continue
        for result in results:
            record = fetch_and_extract(result)
            if record:
                record["keyword"] = keyword
                records.append(record)
    return records
