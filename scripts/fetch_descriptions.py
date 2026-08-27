#!/usr/bin/env python3
"""Fetch a one-line description for every external link in data/links.yml.

Descriptions written by hand in links.yml always win — this script never looks
at those URLs. Everything else is fetched once and cached in
data/descriptions.json, which is committed, so a normal build does no network
I/O at all and stays reproducible.

    python3 scripts/fetch_descriptions.py            # only what is missing
    python3 scripts/fetch_descriptions.py --all      # refresh everything
    python3 scripts/fetch_descriptions.py --limit 50 # cap the work

A failure is cached too, with a timestamp, so a dead link is not re-fetched on
every single build; it is retried after RETRY_AFTER_DAYS.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINKS = ROOT / "data" / "links.yml"
CACHE = ROOT / "data" / "descriptions.json"

RETRY_AFTER_DAYS = 14
MAX_LEN = 220
TIMEOUT = 15
WORKERS = 8
READ_BYTES = 300_000          # plenty for <head>; avoids pulling whole pages

UA = ("Mozilla/5.0 (compatible; directory.kiarashs.ir link describer; "
      "+https://github.com/KiarashS/directory)")

GITHUB_REPO = re.compile(r"^https?://github\.com/([^/]+)/([^/#?]+)/?$", re.I)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def tidy(text: str | None) -> str:
    """Collapse whitespace, unescape entities, trim to one readable line."""
    if not text:
        return ""
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) <= MAX_LEN:
        return text
    cut = text[:MAX_LEN].rsplit(" ", 1)[0].rstrip(" ,;:.—-")
    return cut + "…"


def meta(body: str, *names: str) -> str:
    """First matching <meta> content, by property or name.

    A parser rather than a regex on purpose: an earlier regex version let the
    captured group run across tag boundaries and returned the tail of one meta
    element glued to the head of another.
    """
    head = BeautifulSoup(body, "html.parser")
    for name in names:
        for attr in ("property", "name"):
            tag = head.find("meta", attrs={attr: re.compile(rf"^{re.escape(name)}$", re.I)})
            if tag and tag.get("content", "").strip():
                return tag["content"]
    return ""


def from_github(session: requests.Session, owner: str, repo: str) -> str:
    """A repo's own description beats scraping github.com's HTML."""
    repo = re.sub(r"\.git$", "", repo)
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = session.get(f"https://api.github.com/repos/{owner}/{repo}",
                    headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return tidy(r.json().get("description"))


def describe(session: requests.Session, url: str) -> tuple[str, str]:
    """Return (description, source). Raises on network/HTTP failure."""
    gh = GITHUB_REPO.match(url)
    if gh:
        try:
            text = from_github(session, gh.group(1), gh.group(2))
            if text:
                return text, "github-api"
        except Exception:                              # noqa: BLE001
            pass          # fall through and read the repo page like any other

    r = session.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT,
                    stream=True, allow_redirects=True)
    r.raise_for_status()

    ctype = r.headers.get("content-type", "")
    if "html" not in ctype.lower():
        # A PDF or an image has no description to read; say so and move on.
        return "", "not-html"

    chunk = r.raw.read(READ_BYTES, decode_content=True) or b""
    body = chunk.decode(r.encoding or "utf-8", errors="replace")

    text = tidy(meta(body, "og:description", "description", "twitter:description",
                     "citation_abstract"))
    if text:
        return text, "meta"

    title_tag = BeautifulSoup(body, "html.parser").find("title")
    title = tidy(title_tag.get_text() if title_tag else "")
    return (title, "title") if title else ("", "none")


def collect_urls(doc: dict) -> list[str]:
    """Every external URL that has no hand-written description."""
    urls, seen = [], set()
    for cat in doc.get("categories") or []:
        for entry in cat.get("entries") or []:
            pinned = bool(entry.get("description"))
            candidates = []
            if entry.get("url"):
                candidates.append((entry["url"], pinned))
            for link in entry.get("links") or []:
                # A sub-link may carry its own pinned description.
                candidates.append((link["url"], bool(link.get("description"))))
            for url, is_pinned in candidates:
                if is_pinned or not url.lower().startswith(("http://", "https://")):
                    continue
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
    return urls


def is_stale(record: dict, retry_failures: bool) -> bool:
    if "failed_at" not in record:
        return False
    if not retry_failures:
        return False
    try:
        when = dt.datetime.fromisoformat(record["failed_at"])
    except ValueError:
        return True
    age = dt.datetime.now(dt.timezone.utc) - when
    return age.days >= RETRY_AFTER_DAYS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="refetch every URL")
    ap.add_argument("--limit", type=int, default=0, help="stop after N fetches")
    ap.add_argument("--retry-failures", action="store_true",
                    help="retry URLs that failed more than "
                         f"{RETRY_AFTER_DAYS} days ago")
    args = ap.parse_args()

    doc = yaml.safe_load(LINKS.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

    urls = collect_urls(doc)
    if args.all:
        todo = urls
    else:
        todo = [u for u in urls
                if u not in cache or is_stale(cache[u], args.retry_failures)]
    if args.limit:
        todo = todo[: args.limit]

    print(f"{len(urls)} external links, {len(cache)} cached, {len(todo)} to fetch")
    if not todo:
        return 0

    session = requests.Session()
    ok = failed = empty = 0

    def work(url: str):
        try:
            text, source = describe(session, url)
            return url, {"description": text, "source": source, "fetched_at": now()}
        except Exception as exc:                      # noqa: BLE001 - cached as data
            return url, {"error": f"{type(exc).__name__}: {exc}"[:200],
                         "failed_at": now()}

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, (url, record) in enumerate(pool.map(work, todo), 1):
            cache[url] = record
            if "error" in record:
                failed += 1
            elif record["description"]:
                ok += 1
            else:
                empty += 1
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  ok={ok} empty={empty} failed={failed}")

    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False,
                                sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {CACHE.relative_to(ROOT)} — {len(cache)} entries "
          f"({ok} described, {empty} with nothing to say, {failed} failed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
