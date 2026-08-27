#!/usr/bin/env python3
"""Render index.html from data/links.yml.

    python3 scripts/build.py            # write index.html
    python3 scripts/build.py --check    # exit 1 if index.html is out of date

Everything comes from data/links.yml, including descriptions — nothing is
fetched or generated. An entry with a `description` gets an (i) button in the
top-right of its card, and the text shows in a popover on hover or focus.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import itertools
import pathlib
import sys
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINKS = ROOT / "data" / "links.yml"
OUT = ROOT / "index.html"

# Every popover needs an id so its button can point at it with aria-describedby.
_ids = itertools.count(1)


def asset(path: str) -> str:
    """A site-relative asset URL stamped with a hash of its contents.

    A changed file becomes a different URL, so no cache — service worker,
    browser or CDN — can answer with an old copy. Without this, the service
    worker happily served the stylesheet and script from a first visit
    indefinitely while the HTML kept updating around them.
    """
    digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()[:8]
    return f"./{path}?v={digest}"

e = lambda s: html.escape(s or "", quote=True)

# Tabler-style category glyphs, drawn at 24x24 with a 1.8 stroke.
ICONS = {
 'pdfs': '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M5 12V5a2 2 0 0 1 2-2h7l5 5v4"/><path d="M5 18h1.5a1.5 1.5 0 0 0 0-3H5v6"/><path d="M17 18h2"/><path d="M20 15h-3v6"/><path d="M11 15v6h1a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2z"/>',
 'links': '<path d="M9 15l6-6"/><path d="M11 6l.463-.536a5 5 0 0 1 7.071 7.072L18 13"/><path d="M13 18l-.397.534a5.068 5.068 0 0 1-7.127 0 4.972 4.972 0 0 1 0-7.071L6 11"/>',
 'tools': '<path d="M3 21h4L20 8a1.5 1.5 0 0 0-4-4L3 17v4"/><path d="M14.5 5.5l4 4"/><path d="M12 8l-5-5-3 3 5 5"/><path d="M7 8l-1.5 1.5"/><path d="M16 12l5 5-3 3-5-5"/><path d="M16 17l-1.5 1.5"/>',
 'datasets': '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.657 3.582 3 8 3s8-1.343 8-3V6"/><path d="M4 12v6c0 1.657 3.582 3 8 3s8-1.343 8-3v-6"/>',
 'courses': '<path d="M22 9L12 5 2 9l10 4 10-4v6"/><path d="M6 10.6V16c0 1.1 2.7 2 6 2s6-.9 6-2v-5.4"/>',
}

EXT = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-ext"/></svg>'
PDF = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-pdf"/></svg>'

SPRITE = '''  <svg class="visually-hidden" aria-hidden="true" focusable="false">
    <defs>
      <g id="i-ext" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 7H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-5"/><path d="M10 14 20 4"/><path d="M15 4h5v5"/>
      </g>
      <g id="i-info" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v4h1"/>
      </g>
      <g id="i-pdf" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/>
      </g>
    </defs>
  </svg>'''


# --- helpers ---------------------------------------------------------------

def is_local(url: str) -> bool:
    return not url.lower().startswith(("http://", "https://"))


def host_label(url: str) -> str:
    """What to print on the badge: 'PDF' for our own files, else the host."""
    if is_local(url) or url.lower().endswith(".pdf"):
        return "PDF"
    netloc = urllib.parse.urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def info(text: str, subject: str) -> str:
    """An (i) button plus the popover it describes.

    The popover is a sibling, shown by CSS on hover or focus, so it works with
    no JavaScript at all; directory.js only adds tap-to-toggle and Escape.
    """
    if not text:
        return ""
    pid = f"info-{next(_ids)}"
    return (
        '<span class="card-info">'
        f'<button class="info-btn" type="button" aria-describedby="{pid}" '
        f'aria-label="About {e(subject)}">'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-info"/></svg>'
        '</button>'
        f'<span class="popover" role="tooltip" id="{pid}">{e(text)}</span>'
        '</span>')


def all_links(entry: dict) -> list[dict]:
    """Primary first, then the extras, as a single uniform list."""
    out = []
    if entry.get("url"):
        out.append({"text": entry["title"], "url": entry["url"],
                    "description": entry.get("description")})
    for link in entry.get("links") or []:
        out.append({"text": link["text"], "url": link["url"],
                    "description": link.get("description")})
    return out


def desc(item: dict) -> str:
    return (item.get("description") or "").strip()


def badge(url: str) -> str:
    label = host_label(url)
    if label == "PDF":
        return f'<span class="badge badge-pdf">{PDF} PDF</span>'
    return f'<span class="badge">{EXT} {e(label)}</span>'


def link_attrs(url: str) -> str:
    return "" if is_local(url) else ' target="_blank" rel="noopener nofollow"'


# --- rendering -------------------------------------------------------------

def render_entry(entry: dict) -> str:
    links = all_links(entry)
    if not links:
        raise SystemExit(f"entry {entry.get('title')!r} has neither url nor links")

    note = desc(entry)

    # The search haystack: title, descriptions, every link label and every host.
    hay = " ".join(filter(None, [entry["title"], note]
                          + [l["text"] for l in links]
                          + [host_label(l["url"]) for l in links]
                          + [desc(l) for l in links]))

    out = [f'        <li class="card{" card-multi" if len(links) > 1 else ""}" '
           f'data-search="{e(" ".join(hay.split()).lower())}">']

    if len(links) > 1:
        # Multi-link entries do not navigate. The button opens a modal listing
        # every link; the <ul> below is what the modal is built from, and is
        # also the whole no-JS fallback.
        out.append(f'          <button class="card-title" type="button" '
                   f'data-open-modal aria-haspopup="dialog">{e(entry["title"])}</button>')
        out.append(f'          <ul class="card-links">')
        for link in links:
            out.append(f'            <li><a href="{e(link["url"])}"{link_attrs(link["url"])}>'
                       f'{e(link["text"])}</a>'
                       + (f'<span class="link-note">{e(desc(link))}</span>' if desc(link) else "")
                       + f'{badge(link["url"])}</li>')
        out.append('          </ul>')
        out.append(f'          <div class="card-foot">'
                   f'<span class="badge badge-count">{len(links)} links</span></div>')
    else:
        link = links[0]
        out.append(f'          <a class="card-title" href="{e(link["url"])}"'
                   f'{link_attrs(link["url"])}>{e(entry["title"])}</a>')
        out.append(f'          <div class="card-foot">{badge(link["url"])}</div>')

    # Sits last in the markup, positioned into the top-right corner by CSS, so
    # it is also the last thing reached by Tab rather than interrupting the
    # title on the way in.
    out.append("          " + info(note, entry["title"]))
    out.append("        </li>")
    return "\n".join(x for x in out if x.strip())


def build(doc: dict) -> str:
    site = doc["site"]
    cats = doc["categories"]

    tabs, panels, stats = [], [], []
    total = sum(len(c.get("entries") or []) for c in cats)

    for i, cat in enumerate(cats):
        slug, name = cat["slug"], cat["name"]
        if slug not in ICONS:
            raise SystemExit(f"category {slug!r} has no icon; add one to ICONS")
        entries = cat.get("entries") or []
        groups = cat.get("groups") or []
        n = len(entries) or len(groups)

        stats.append(f"        <li><b>{n}</b> {e(name.lower())}</li>")
        tabs.append(
            f'          <button class="tab" role="tab" type="button" id="tab-{slug}" '
            f'data-slug="{slug}"\n'
            f'                  aria-controls="panel-{slug}" '
            f'aria-selected="{"true" if i == 0 else "false"}" '
            f'tabindex="{0 if i == 0 else -1}">\n'
            f'            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONS[slug]}</svg>\n'
            f'            <span>{e(name)}</span>'
            f'<span class="tab-count" data-total="{n}">{n}</span>\n'
            f"          </button>")

        body = [f'      <section class="panel" role="tabpanel" id="panel-{slug}" '
                f'data-slug="{slug}"\n               aria-labelledby="tab-{slug}">',
                '        <div class="panel-head">',
                f"          <h2>{e(name)}</h2>",
                f'          <span class="panel-count" data-panel-count>{n} '
                f'{"entry" if n == 1 else "entries"}</span>',
                "        </div>"]
        if cat.get("blurb"):
            body.append(f'        <p class="panel-blurb">{e(cat["blurb"])}</p>')
        if entries:
            body.append('        <ul class="cards">')
            body += [render_entry(x) for x in entries]
            body.append("        </ul>")
        if groups:
            body.append('        <div class="groups">')
            for g in groups:
                hay = e(" ".join(f"{g['title']} {g['body']} {name}".split()).lower())
                body.append(f'          <details class="group" data-search="{hay}">')
                body.append(f'            <summary>{e(g["title"])}</summary>')
                body.append(f'            <div class="group-body">{e(g["body"])}</div>')
                body.append("          </details>")
            body.append("        </div>")
        body.append("      </section>")
        panels.append("\n".join(body))

    nl = "\n"
    return f'''<!DOCTYPE html>
<html lang="en" class="no-js">

<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{e(site["title"])} — files, links, tools and datasets</title>
  <meta name="description" content="A hand-kept directory of {total}+ PDFs, reading links, web tools and open datasets, collected by {e(site["author"])}.">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#f4f5f8">
  <link rel="canonical" href="{e(site["url"])}">

  <meta property="og:type" content="website">
  <meta property="og:url" content="{e(site["url"])}">
  <meta property="og:title" content="{e(site["title"])}">
  <meta property="og:description" content="A hand-kept directory of PDFs, reading links, web tools and open datasets.">
  <meta property="og:image" content="{e(site["url"])}android-chrome-512x512.png">
  <meta name="twitter:card" content="summary">

  <link rel="apple-touch-icon" sizes="180x180" href="./apple-touch-icon.png">
  <link rel="icon" type="image/png" sizes="32x32" href="./favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="./favicon-16x16.png">
  <link rel="mask-icon" href="./safari-pinned-tab.svg" color="#4f5bd5">
  <meta name="msapplication-TileColor" content="#4f5bd5">
  <link rel="manifest" href="./manifest.webmanifest">

  <link rel="stylesheet" href="{asset("static/css/directory.css")}">

  <script>
    // Runs before first paint, so neither of these can flash.
    (function () {{
      var root = document.documentElement;

      // Marking the document as scripted here, rather than in the deferred
      // directory.js, means the inline link lists on multi-link cards are
      // never painted at all — they exist only as the no-JavaScript fallback.
      root.className = root.className.replace('no-js', 'js');

      try {{
        var t = localStorage.getItem('directory:theme');
        if (t === 'light' || t === 'dark') root.setAttribute('data-theme', t);
      }} catch (e) {{}}
    }})();
  </script>
</head>

<body>
{SPRITE}

  <a class="skip-link" href="#main">Skip to content</a>

  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="./">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 6a2 2 0 0 1 2-2h3l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>
          </svg>
        </span>
        <span class="brand-text">{e(site["title"])}</span>
      </a>

      <div class="header-actions">
        <button class="icon-btn theme-btn" type="button" data-theme-toggle aria-label="Switch theme">
          <svg data-theme-icon="system" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/></svg>
          <svg data-theme-icon="light" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
          <svg data-theme-icon="dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
        </button>

        <a class="icon-btn" href="{e(site["author_url"])}" aria-label="{e(site["author_url"])}" title="{e(site["author_url"])}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3.6 9h16.8M3.6 15h16.8"/><path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"/></svg>
        </a>
      </div>
    </div>
  </header>

  <div class="container hero">
    <h1>{e(site["heading"])} <span class="accent">{e(site["heading_accent"])}</span></h1>
    <p>{e(site["tagline"])}</p>
    <ul class="hero-stats">
{nl.join(stats)}
    </ul>
  </div>

  <div class="toolbar">
    <div class="container toolbar-inner">
      <div class="search">
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <label class="visually-hidden" for="search">Search the directory</label>
        <input id="search" type="search" placeholder="Search {total} entries…" autocomplete="off" spellcheck="false">
        <span class="search-hint" aria-hidden="true"><kbd>/</kbd></span>
        <button class="search-clear" type="button" data-search-clear aria-label="Clear search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
      </div>

      <div class="view-switch" role="group" aria-label="Layout">
        <button type="button" data-view="grid" aria-pressed="true" aria-label="Grid view" title="Grid view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>
        </button>
        <button type="button" data-view="list" aria-pressed="false" aria-label="List view" title="List view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/></svg>
        </button>
      </div>
    </div>
  </div>

  <main id="main" class="container">
    <div class="tabs" role="tablist" aria-label="Categories">
{nl.join(tabs)}
    </div>

    <div class="notice">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>
      <p>Something missing? Send it over through the <a href="{e(site["suggest_form"])}" target="_blank" rel="noopener">suggestion form</a>, or just get in touch.</p>
    </div>

    <div class="results-bar">
      <span data-results-text></span>
      <button type="button" data-search-clear>Clear search</button>
    </div>

    <p class="visually-hidden" role="status" aria-live="polite" data-live></p>

{nl.join(panels)}

    <div class="empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/><path d="M8.5 11h5"/></svg>
      <h2>Nothing matches “<span data-empty-term></span>”</h2>
      <p>Try a shorter word, or a different spelling.</p>
    </div>
  </main>

  <dialog class="link-modal" aria-labelledby="link-modal-title">
    <div class="link-modal-head">
      <h2 id="link-modal-title"></h2>
      <button class="icon-btn" type="button" data-close-modal aria-label="Close">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>
    <p class="link-modal-note" data-modal-note hidden></p>
    <ul class="link-modal-list" data-modal-list></ul>
  </dialog>

  <button class="to-top" type="button" aria-label="Back to top">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5"/><path d="m5 12 7-7 7 7"/></svg>
  </button>

  <footer class="site-footer">
    <div class="container footer-inner">
      <span>Compiled by <a href="{e(site["author_url"])}">{e(site["author"])}</a>.</span>
      <ul class="footer-links">
        <li><a href="{e(site["suggest_form"])}" target="_blank" rel="noopener">Suggest a resource</a></li>
        <li><a href="{e(site["author_url"])}">{e(urllib.parse.urlparse(site["author_url"]).netloc)}</a></li>
      </ul>
    </div>
  </footer>

  <script src="{asset("static/js/directory.js")}" defer></script>
  <script>
    if ('serviceWorker' in navigator) {{
      window.addEventListener('load', function () {{
        navigator.serviceWorker.register('./sw.js', {{ scope: './' }}).catch(function () {{}});
      }});
    }}
  </script>
</body>

</html>
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if index.html differs from what this would write")
    args = ap.parse_args()

    doc = yaml.safe_load(LINKS.read_text(encoding="utf-8"))
    page = build(doc)

    entries = sum(len(c.get("entries") or []) for c in doc["categories"])
    links = sum(len(all_links(x)) for c in doc["categories"]
                for x in (c.get("entries") or []))
    multi = sum(1 for c in doc["categories"] for x in (c.get("entries") or [])
                if len(all_links(x)) > 1)

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current == page:
            print(f"index.html is up to date ({entries} entries, {links} links)")
            return 0
        print("index.html is STALE — run: python3 scripts/build.py", file=sys.stderr)
        return 1

    OUT.write_text(page, encoding="utf-8")
    print(f"index.html — {entries} entries, {links} links, "
          f"{multi} of them open a modal ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
