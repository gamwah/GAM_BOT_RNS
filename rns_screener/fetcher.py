"""Fetches RNS announcement listings and full text from Investegate.

Uses the OS certificate store (via truststore) instead of the bundled
certifi list, because some machines run antivirus HTTPS scanning
(e.g. Norton) that certifi doesn't trust but Windows does.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import truststore

truststore.inject_into_ssl()

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.investegate.co.uk"
USER_AGENT = "RNS-Screener-Bot/0.1 (personal research tool; contact: hywelgammage@gmail.com)"
REQUEST_DELAY_SECONDS = 0.75  # politeness: well under 1-2 req/sec

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


@dataclass
class Announcement:
    time: str
    source: str
    company: str
    ticker: str
    headline: str
    url: str
    id: str


def _cache_path(*parts: str) -> Path:
    safe_parts = [re.sub(r"[^A-Za-z0-9_.-]", "_", p) for p in parts]
    return CACHE_DIR.joinpath(*safe_parts)


def _get(url: str, cache_file: Path | None = None) -> str:
    """GET a URL with disk caching and a politeness delay between real requests."""
    if cache_file and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    time.sleep(REQUEST_DELAY_SECONDS)
    resp = _session.get(url, timeout=20)
    resp.raise_for_status()
    html = resp.text

    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(html, encoding="utf-8")

    return html


def _parse_listing_page(html: str) -> list[Announcement]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    results: list[Announcement] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) != 4:
            continue  # header row or unexpected layout

        time_cell, _source_cell, company_cell, headline_cell = cells

        source_link = _source_cell.find("a")
        source = source_link.get_text(strip=True) if source_link else ""

        company_link = company_cell.find_all("a")[-1] if company_cell.find_all("a") else None
        company_text = company_link.get_text(strip=True) if company_link else ""
        match = re.match(r"^(.*)\s+\(([^()]+)\)$", company_text)
        if match:
            company, ticker = match.group(1).strip(), match.group(2).strip()
        else:
            company, ticker = company_text, ""

        headline_link = headline_cell.find("a", class_="announcement-link")
        if headline_link is None:
            continue
        headline = headline_link.get_text(strip=True)
        url = headline_link["href"]
        ann_id = url.rstrip("/").rsplit("/", 1)[-1]

        results.append(
            Announcement(
                time=time_cell.get_text(strip=True),
                source=source,
                company=company,
                ticker=ticker,
                headline=headline,
                url=url,
                id=ann_id,
            )
        )

    return results


def _page_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"[?&]page=(\d+)", a["href"])
        if m:
            pages.add(int(m.group(1)))
    return max(pages) if pages else 1


def fetch_day_announcements(date_str: str, use_cache: bool = True) -> list[Announcement]:
    """Fetch every announcement listed for a given day (YYYY-MM-DD), across all pages."""
    url = f"{BASE_URL}/today-announcements/{date_str}"
    cache_file = _cache_path("listings", date_str, "page-1.html") if use_cache else None
    first_html = _get(url, cache_file)

    all_results = _parse_listing_page(first_html)
    total_pages = _page_count(first_html)

    for page in range(2, total_pages + 1):
        page_url = f"{url}?page={page}"
        page_cache = _cache_path("listings", date_str, f"page-{page}.html") if use_cache else None
        html = _get(page_url, page_cache)
        all_results.extend(_parse_listing_page(html))

    return all_results


def fetch_article_text(announcement: Announcement, use_cache: bool = True) -> str:
    """Fetch the full announcement body text (the div.news-window content)."""
    cache_file = _cache_path("articles", f"{announcement.id}.html") if use_cache else None
    html = _get(announcement.url, cache_file)
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div.news-window")
    return body.get_text("\n", strip=True) if body else ""
