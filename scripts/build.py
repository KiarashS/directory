#!/usr/bin/env python3
"""Render the site from data/links.yml.

    python3 scripts/build.py            # write every page
    python3 scripts/build.py --check    # exit 1 if any page is out of date

Pages produced:

    /                      the PDF entries (canonical: /pdfs/)
    /<category>/           that category's entries
    /courses/              the course list
    /courses/<slug>/       one course, its modules and materials

Every URL is relative and depth-aware. The site is served from a subpath
(kiarashs.github.io/directory/), so a root-absolute "/static/..." would break;
`rel()` prefixes each URL with the right number of "../" for the page it is
being written into.

Nothing here touches the network, so the build is reproducible.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import itertools
import json
import pathlib
import re
import shutil
import sys
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINKS = ROOT / "data" / "links.yml"
ASSETS = ROOT / "assets"
OUT_DEFAULT = ROOT / "_site"

# Course material lives under assets/courses/<course-slug>/, one folder per
# course, so a course's files stay together and can be archived as a unit.
COURSE_ASSETS = "courses"

# Copied into the output as-is. Everything else in the repository — the YAML,
# these scripts, .git, .github — is input to the build, not part of the site.
RUNTIME = [
    "assets", "static", "viewer",
    "sw.js", "manifest.webmanifest", "site.webmanifest", "browserconfig.xml",
    "favicon.ico", "favicon-16x16.png", "favicon-32x32.png",
    "apple-touch-icon.png", "safari-pinned-tab.svg",
    "android-chrome-192x192.png", "android-chrome-512x512.png",
    "mstile-150x150.png",
]

e = lambda s: html.escape(s or "", quote=True)

# Popover ids have to be unique per page, so the counter resets for each one.
_ids = itertools.count(1)


# --- URLs ------------------------------------------------------------------

def rel(url: str, depth: int) -> str:
    """A URL written for a page `depth` directories below the site root."""
    if url.startswith(("http://", "https://", "mailto:", "#", "data:")):
        return url
    if url.startswith("./"):
        url = url[2:]
    return ("../" * depth) + url if depth else "./" + url


def asset(path: str, depth: int) -> str:
    """A site asset, stamped with a hash of its contents.

    A changed file becomes a different URL, so no cache — service worker,
    browser or CDN — can answer with an old copy.
    """
    digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()[:8]
    return f"{rel(path, depth)}?v={digest}"


def is_local(url: str) -> bool:
    return not url.lower().startswith(("http://", "https://"))


def host_label(url: str) -> str:
    """What the badge prints: 'PDF' for our own files, else the host."""
    if is_local(url) or url.lower().endswith(".pdf"):
        return "PDF"
    netloc = urllib.parse.urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def link_attrs(url: str) -> str:
    return "" if is_local(url) else ' target="_blank" rel="noopener nofollow"'


# --- Local PDFs ------------------------------------------------------------
#
# A PDF is declared by its file — `pdf: action-verbs.pdf` — and everything
# else is derived: where it lives, what its viewer route is called, and the URL
# a card links to. `viewer_url` is the only place that route is spelled out, so
# the renderer, the validator and the generated page cannot drift apart.

def viewer_url(slug: str) -> str:
    return f"./v/{slug}/"


def viewer_depth(slug: str) -> int:
    """How many directories down v/<slug>/index.html sits.

    A flat slug gives 2, as it always has. A slug with slashes in it — which
    is what a course material gets — is deeper, and its page has to reach the
    site root with the right number of "../" or every asset on it 404s.
    """
    return 1 + len(slug.split("/"))


def slug_segment(text: str) -> str:
    """One path segment of a slug, made URL-safe.

    Case is kept: a slug is a public URL, and quietly lowercasing one would
    change the address of anything migrated with its name already set.
    """
    seg = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip())
    return re.sub(r"-{2,}", "-", seg).strip("-._")


def pdf_slug(rel_path: str) -> str:
    """The route derived from a PDF's path under assets/, minus the .pdf.

    'machine learning cheat sheet.pdf'      -> 'machine-learning-cheat-sheet'
    'courses/intro-ml/lecture-01.pdf'       -> 'courses/intro-ml/lecture-01'

    Mirroring the path is what keeps course material collision-free without
    anyone writing a slug by hand: two courses can both hold a lecture-01.pdf
    because their folders differ. A file directly in assets/ derives exactly
    the slug it always did.
    """
    parts = list(pathlib.PurePosixPath(rel_path).parts)
    if parts and parts[-1].lower().endswith(".pdf"):
        parts[-1] = parts[-1][:-4]
    segs = [s for s in (slug_segment(p) for p in parts) if s]
    if not segs:
        raise SystemExit(
            f"cannot derive a slug from {rel_path!r}; give the entry an explicit slug:")
    return "/".join(segs)


def check_slug(slug: str, subject: str) -> str:
    """A hand-written `slug:`, checked before it becomes a directory path.

    Nothing validated these before, so a slug could carry '..' or a space and
    the build would cheerfully write the page somewhere unintended.
    """
    if slug.startswith("/") or slug.endswith("/"):
        raise SystemExit(f'{subject}: "slug" must not start or end with "/": {slug!r}')
    for seg in slug.split("/"):
        if not seg or seg in {".", ".."} or seg != slug_segment(seg):
            raise SystemExit(
                f'{subject}: "slug" has an unusable path segment {seg!r} in {slug!r}')
    return slug


def pdf_path(value: str, subject: str, base: str = "") -> str:
    """Validate a `pdf:` value and return it as a repo-relative POSIX path.

    Everything that can go wrong with a hand-written filename is caught here
    rather than at 404 time: a path that climbs out of assets/, the wrong
    extension, a file that is not there, or a file that is not a PDF.

    `base` is the directory the value is written relative to — empty for an
    ordinary entry, "courses/<slug>" for a course's material, which is what
    lets a material name just its file.
    """
    raw = str(value or "").strip()
    if not raw:
        raise SystemExit(f'{subject}: "pdf" is empty')
    if raw.startswith("/") or "\\" in raw:
        raise SystemExit(f'{subject}: "pdf" must be a path inside assets/, not {raw!r}')

    where = f"assets/{base}/{raw}" if base else f"assets/{raw}"
    resolved = (ASSETS / base / raw).resolve()
    if not resolved.is_relative_to(ASSETS.resolve()):
        raise SystemExit(f'{subject}: "pdf" escapes assets/: {raw!r}')
    if resolved.suffix.lower() != ".pdf":
        raise SystemExit(f'{subject}: "pdf" must name a .pdf file, not {raw!r}')
    if not resolved.is_file():
        raise SystemExit(f"PDF not found: {where}\nReferenced by: {subject}")
    with resolved.open("rb") as fh:
        if fh.read(5) != b"%PDF-":
            raise SystemExit(
                f"not a PDF (no %PDF- signature): {where}\nReferenced by: {subject}")

    return resolved.relative_to(ROOT).as_posix()


def render_viewer(title: str, target: str, slug: str, *, embed: bool = False) -> str:
    """The page at v/<slug>/index.html.

    `target` is either a repo-relative PDF path or, for an embed, an external
    URL. Paths are relative so the page works both under the Pages project
    subpath and on the custom domain, with no host baked in — and relative to
    this page's own depth, which a nested slug changes.
    """
    depth = viewer_depth(slug)
    if embed:
        src = target
    else:
        # Encoded whole, slashes included, exactly as the hand-written pages
        # did — that is the form this viewer has been served with for years.
        src = rel("viewer/web/viewer.html", depth) + "?file=" + urllib.parse.quote(
            rel(target, depth), safe="")

    # A query on the wrapper is handed to PDF.js as a fragment, which is how
    # ./v/betty-blue/?page=37 opens page 37. Re-setting src reloads the frame
    # and fires load again, so it only ever runs once.
    script = """
        <script>
            function iframeDidLoad() {
                var q = window.location.search.slice(1);
                if (!q) return;
                var frame = document.getElementById('iframe-viewer');
                if (frame.src.indexOf('#') === -1) frame.src += '#' + q;
            }
        </script>""" if not embed else ""

    return f"""<!DOCTYPE html>
<html lang="en">
    <head>
        <meta charset="UTF-8" />
        <title>{e(title)}</title>
        <meta name="viewport" content="width=device-width, height=device-height, initial-scale=1.0, minimum-scale=1.0">
        <meta name="robots" content="noindex">

        <style>
            body, html {{width: 100%; height: 100%; margin: 0; padding: 0}}
            .viewer-container {{position: absolute; top: 0; left: 0; right: 0; bottom: 0;}}
            .viewer-container iframe {{display: block; width: 100%; height: 100%; border: none;}}
        </style>{script}
    </head>
    <body>
        <div class="viewer-container">
            <iframe
                id="iframe-viewer"{'' if embed else chr(10) + '                onload="iframeDidLoad();"'}
                src="{e(src)}"
                title="{e(title)}"
            ></iframe>
        </div>
    </body>
</html>
"""


def normalize(doc: dict) -> tuple[dict, dict[str, dict]]:
    """Turn every `pdf:`/`embed:` declaration into the URL the renderer expects.

    Nothing downstream needs to know a PDF was declared by filename: by the
    time `build_pages` sees an item it carries an ordinary `url:`, so cards,
    badges, search, sorting and modals all behave exactly as they did when
    those URLs were written by hand. The generated URL is never written back
    to links.yml — it lives only in the parsed document.
    """
    routes: dict[str, dict] = {}

    def claim(slug: str, target: str, title: str, kind: str) -> None:
        prior = routes.get(slug)
        if prior and (prior["target"], prior["kind"]) != (target, kind):
            raise SystemExit(
                f"Duplicate PDF viewer slug: {slug}\n\nUsed by:\n"
                f'- {prior["title"]} -> {prior["target"]}\n- {title} -> {target}')
        routes[slug] = {"target": target, "title": title, "kind": kind}

    def visit(item: dict, subject: str, base: str = "") -> None:
        subject = item.get("title") or item.get("text") or subject
        declared = [k for k in ("url", "pdf", "embed") if item.get(k)]
        if len(declared) > 1:
            raise SystemExit(
                f'Entry "{subject}" cannot contain both '
                + " and ".join(f"'{k}'" for k in declared) + ".")

        if item.get("pdf"):
            target = pdf_path(item["pdf"], f'"{subject}"', base)
            written = str(item.get("slug") or "").strip()
            # The derived slug comes from where the file actually landed, not
            # from what was typed, so a course material picks up its course's
            # folder without repeating it and `../` cannot smuggle in a slug
            # that disagrees with the path.
            slug = (check_slug(written, f'"{subject}"') if written
                    else pdf_slug(target[len("assets/"):]))
            claim(slug, target, subject, "pdf")
            item["url"] = viewer_url(slug)
        elif item.get("embed"):
            written = str(item.get("slug") or "").strip()
            if not written:
                raise SystemExit(f'Entry "{subject}" uses "embed" and needs a "slug".')
            slug = check_slug(written, f'"{subject}"')
            claim(slug, str(item["embed"]), subject, "embed")
            item["url"] = viewer_url(slug)

        for link in item.get("links") or []:
            visit(link, subject, base)

    for cat in doc.get("categories") or []:
        for entry in cat.get("entries") or []:
            visit(entry, "(untitled)")
        for course in cat.get("courses") or []:
            # A course's material lives in its own folder under assets/courses/,
            # named after the course, so a material names only its file and a
            # lecture-01.pdf in one course cannot collide with another's.
            title = course.get("title", "(course)")
            base = f'{COURSE_ASSETS}/{check_slug(str(course["slug"]), title)}'
            for link in course.get("links") or []:
                visit(link, title, base)
            for module in course.get("modules") or []:
                for mat in module.get("materials") or []:
                    visit(mat, title, base)

    return doc, routes


# --- Icons -----------------------------------------------------------------

ICONS = {
 'pdfs': '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M5 12V5a2 2 0 0 1 2-2h7l5 5v4"/><path d="M5 18h1.5a1.5 1.5 0 0 0 0-3H5v6"/><path d="M17 18h2"/><path d="M20 15h-3v6"/><path d="M11 15v6h1a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2z"/>',
 'links': '<path d="M9 15l6-6"/><path d="M11 6l.463-.536a5 5 0 0 1 7.071 7.072L18 13"/><path d="M13 18l-.397.534a5.068 5.068 0 0 1-7.127 0 4.972 4.972 0 0 1 0-7.071L6 11"/>',
 'tools': '<path d="M3 21h4L20 8a1.5 1.5 0 0 0-4-4L3 17v4"/><path d="M14.5 5.5l4 4"/><path d="M12 8l-5-5-3 3 5 5"/><path d="M7 8l-1.5 1.5"/><path d="M16 12l5 5-3 3-5-5"/><path d="M16 17l-1.5 1.5"/>',
 'datasets': '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.657 3.582 3 8 3s8-1.343 8-3V6"/><path d="M4 12v6c0 1.657 3.582 3 8 3s8-1.343 8-3v-6"/>',
 'talks': '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/><path d="M8.5 10.5 11 13l4.5-4.5"/>',
 'courses': '<path d="M22 9L12 5 2 9l10 4 10-4v6"/><path d="M6 10.6V16c0 1.1 2.7 2 6 2s6-.9 6-2v-5.4"/>',
}

# Material kinds a course module can hold. The label is what a reader sees;
# anything not listed here still renders, just without an icon.
MATERIAL_TYPES = {
    "slides":     ("Slides",     '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>'),
    "notes":      ("Notes",      '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M9 12h6M9 16h4"/>'),
    "assignment": ("Assignment", '<path d="M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1z"/><path d="M8 6H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-2"/><path d="m9 13 2 2 4-4"/>'),
    "reading":    ("Reading",    '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H12v16H6.5A2.5 2.5 0 0 0 4 21.5z"/><path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H12v16h5.5a2.5 2.5 0 0 1 2.5 2.5z"/>'),
    "video":      ("Video",      '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/>'),
    "code":       ("Code",       '<path d="m9 8-5 4 5 4"/><path d="m15 8 5 4-5 4"/>'),
    "dataset":    ("Dataset",    '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.657 3.582 3 8 3s8-1.343 8-3V6"/>'),
}

EXT = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-ext"/></svg>'
PDF = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-pdf"/></svg>'
LAYERS = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-layers"/></svg>'
PIN = '<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-pin"/></svg>'

_STROKE = ('fill="none" stroke="currentColor" stroke-width="2" '
           'stroke-linecap="round" stroke-linejoin="round"')

SPRITE = ('  <svg class="visually-hidden" aria-hidden="true" focusable="false">\n'
          '    <defs>\n'
          f'      <g id="i-ext" {_STROKE}><path d="M11 7H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-5"/><path d="M10 14 20 4"/><path d="M15 4h5v5"/></g>\n'
          f'      <g id="i-pdf" {_STROKE}><path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/></g>\n'
          f'      <g id="i-layers" {_STROKE}><path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="m3 13 9 5 9-5"/></g>\n'
          f'      <g id="i-pin" {_STROKE}><path d="M12 17v5"/><path d="M9 10.8V4h6v6.8l2 3.2H7z"/></g>\n'
          f'      <g id="i-info" {_STROKE}><circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v4h1"/></g>\n'
          + "".join(f'      <g id="i-mat-{k}" {_STROKE}>{v[1]}</g>\n'
                    for k, v in MATERIAL_TYPES.items())
          + '    </defs>\n  </svg>')


# --- Entry helpers ---------------------------------------------------------

def all_links(entry: dict) -> list[dict]:
    """Primary first, then the extras, as one uniform list."""
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


def entry_date(entry: dict) -> str:
    """The date used for sorting, as an ISO string, or "" when undated."""
    value = entry.get("added") or entry.get("date")
    return str(value) if value else ""


def ordered(entries: list[dict]) -> list[dict]:
    """Pinned first, then newest first, then undated in the order written.

    Four buckets rather than one clever sort key, because the two halves want
    different orderings: dated entries go newest first, undated ones keep their
    position in links.yml. That way dating the archive gradually never
    scrambles what is already there.
    """
    buckets: dict[tuple[int, int], list[tuple[int, dict]]] = {
        (p, d): [] for p in (0, 1) for d in (0, 1)
    }
    for i, entry in enumerate(entries):
        pinned = 0 if entry.get("pinned") else 1
        dated = 0 if entry_date(entry) else 1
        buckets[(pinned, dated)].append((i, entry))

    out: list[tuple[int, dict]] = []
    for pinned in (0, 1):
        dated = sorted(buckets[(pinned, 0)],
                       key=lambda pair: entry_date(pair[1]), reverse=True)
        out += dated + buckets[(pinned, 1)]     # undated already in file order
    return [entry for _, entry in out]


def tags_of(entry: dict) -> list[str]:
    raw = entry.get("tags") or []
    return [str(t).strip() for t in raw if str(t).strip()]


def pretty_date(value: str) -> str:
    """2026-08-28 -> 28 Aug 2026. Anything unparseable is printed as written."""
    try:
        d = dt.date.fromisoformat(value)
    except ValueError:
        return value
    return f"{d.day} {d.strftime('%b')} {d.year}"


def badge(url: str) -> str:
    label = host_label(url)
    if label == "PDF":
        return f'<span class="badge badge-pdf">{PDF} PDF</span>'
    return f'<span class="badge">{EXT} {e(label)}</span>'


def info(text: str, subject: str) -> str:
    """An (i) button plus the popover it describes."""
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


# --- Entry card ------------------------------------------------------------

def render_entry(entry: dict, depth: int, order: int = 0) -> str:
    links = all_links(entry)
    if not links:
        raise SystemExit(f"entry {entry.get('title')!r} has neither url nor links")

    note = desc(entry)
    tags = tags_of(entry)
    when = entry_date(entry)
    # A talk carries a few optional facts that read as one line under the
    # title: where it was given, who gave it, and where that was.
    meta = " · ".join(x for x in [
        (entry.get("event") or "").strip(),
        (f'by {entry["by"]}'.strip() if entry.get("by") else ""),
        (entry.get("location") or "").strip(),
    ] if x)

    # Tags join the haystack twice: bare, so a plain search finds them, and
    # prefixed, so "tag:python" can be made to match only tags.
    hay = " ".join(filter(None, [entry["title"], note, meta]
                          + tags + [f"tag:{t}" for t in tags]
                          + [l["text"] for l in links]
                          + [host_label(l["url"]) for l in links]
                          + [desc(l) for l in links]))

    classes = "card" + (" card-multi" if len(links) > 1 else "") \
        + (" is-pinned" if entry.get("pinned") else "")

    attrs = [f'class="{classes}"',
             f'data-search="{e(" ".join(hay.split()).lower())}"',
             f'data-order="{order}"',
             f'data-sort-title="{e(entry["title"].lower())}"']
    if when:
        attrs.append(f'data-date="{e(when)}"')
    if entry.get("pinned"):
        attrs.append("data-pinned")

    out = [f'        <li {" ".join(attrs)}>']

    if len(links) > 1:
        out.append(f'          <button class="card-title" type="button" '
                   f'data-open-modal aria-haspopup="dialog" '
                   f'data-title="{e(entry["title"])}">{e(entry["title"])}'
                   f'<span class="visually-hidden">, {len(links)} links</span></button>')
    else:
        link = links[0]
        out.append(f'          <a class="card-title" href="{e(rel(link["url"], depth))}"'
                   f'{link_attrs(link["url"])}>{e(entry["title"])}</a>')

    if meta:
        out.append(f'          <p class="card-meta">{e(meta)}</p>')

    if len(links) > 1:
        out.append('          <ul class="card-links">')
        for link in links:
            out.append(f'            <li><a href="{e(rel(link["url"], depth))}"'
                       f'{link_attrs(link["url"])}>{e(link["text"])}</a>'
                       + (f'<span class="link-note">{e(desc(link))}</span>' if desc(link) else "")
                       + f'{badge(link["url"])}</li>')
        out.append('          </ul>')

    if tags:
        chips = "".join(
            f'<li><a class="tag" href="?q=tag:{urllib.parse.quote(t)}">{e(t)}</a></li>'
            for t in tags)
        out.append(f'          <ul class="card-tags">{chips}</ul>')

    foot = []
    if entry.get("pinned"):
        foot.append(f'<span class="badge badge-pin">{PIN} Pinned</span>')
    if len(links) > 1:
        foot.append(f'<span class="badge badge-count">{LAYERS} {len(links)} links</span>')
    else:
        foot.append(badge(links[0]["url"]))
    if when:
        foot.append(f'<span class="badge badge-date">{e(pretty_date(when))}</span>')
    out.append(f'          <div class="card-foot">{"".join(foot)}</div>')

    out.append("          " + info(note, entry["title"]))
    out.append("        </li>")
    return "\n".join(x for x in out if x.strip())


# --- Courses ---------------------------------------------------------------

def course_counts(course: dict) -> tuple[int, int]:
    modules = course.get("modules") or []
    return len(modules), sum(len(m.get("materials") or []) for m in modules)


def render_course_card(course: dict, depth: int) -> str:
    mods, mats = course_counts(course)
    meta = " · ".join(filter(None, [course.get("institution"), course.get("term")]))
    hay = " ".join(filter(None, [course["title"], meta, course.get("description"),
                                 course.get("instructor")]))
    out = [f'        <li class="course-card" data-search="{e(" ".join(hay.split()).lower())}">']
    out.append(f'          <a class="course-title" href="{e(rel("courses/" + course["slug"] + "/", depth))}">'
               f'{e(course["title"])}</a>')
    if meta:
        out.append(f'          <p class="course-meta">{e(meta)}</p>')
    if course.get("description"):
        out.append(f'          <p class="course-desc">{e(course["description"])}</p>')
    counts = f'{mods} module{"" if mods == 1 else "s"} · {mats} material{"" if mats == 1 else "s"}'
    out.append(f'          <div class="card-foot"><span class="badge badge-count">'
               f'{LAYERS} {counts}</span></div>')
    out.append("        </li>")
    return "\n".join(out)


def render_material(mat: dict, depth: int) -> str:
    kind = (mat.get("type") or "").lower()
    label, _ = MATERIAL_TYPES.get(kind, ("", ""))
    icon = (f'<span class="material-kind"><svg viewBox="0 0 24 24" aria-hidden="true">'
            f'<use href="#i-mat-{kind}"/></svg>{e(label)}</span>'
            if kind in MATERIAL_TYPES else "")
    return (f'          <li class="material">'
            f'<a href="{e(rel(mat["url"], depth))}"{link_attrs(mat["url"])}>'
            f'{e(mat["title"])}</a>'
            + (f'<span class="material-note">{e(desc(mat))}</span>' if desc(mat) else "")
            + icon + badge(mat["url"]) + '</li>')


def render_course_page(course: dict, depth: int) -> str:
    modules = course.get("modules") or []
    mods, mats = course_counts(course)
    meta = " · ".join(filter(None, [course.get("institution"),
                                    course.get("instructor"), course.get("term")]))

    out = ['    <div class="course-head">']
    out.append(f'      <p class="crumb"><a href="{e(rel("courses/", depth))}">Courses</a></p>')
    out.append(f'      <h1>{e(course["title"])}</h1>')
    if meta:
        out.append(f'      <p class="course-meta">{e(meta)}</p>')
    if course.get("description"):
        out.append(f'      <p class="course-desc">{e(course["description"])}</p>')
    if course.get("links"):
        out.append('      <div class="course-links">')
        for link in course["links"]:
            out.append(f'        <a class="pill" href="{e(rel(link["url"], depth))}"'
                       f'{link_attrs(link["url"])}>{e(link["text"])}</a>')
        out.append("      </div>")
    out.append("    </div>")

    if not modules:
        out.append('    <p class="course-empty">No material has been added to this '
                   'course yet.</p>')
        return "\n".join(out)

    # A short index so a long course is navigable without scrolling it all.
    out.append(f'    <nav class="module-index" aria-label="Modules">')
    out.append(f'      <p class="module-index-head">{mods} module'
               f'{"" if mods == 1 else "s"} · {mats} material'
               f'{"" if mats == 1 else "s"}</p>')
    out.append("      <ol>")
    for i, m in enumerate(modules, 1):
        out.append(f'        <li><a href="#module-{i}">{e(m["title"])}</a></li>')
    out.append("      </ol>")
    out.append("    </nav>")

    for i, m in enumerate(modules, 1):
        out.append(f'    <section class="module" id="module-{i}">')
        out.append(f'      <h2><span class="module-n">{i}</span>{e(m["title"])}</h2>')
        if m.get("summary"):
            out.append(f'      <p class="module-summary">{e(m["summary"])}</p>')
        materials = m.get("materials") or []
        if materials:
            out.append('      <ul class="materials">')
            out += [render_material(x, depth) for x in materials]
            out.append("      </ul>")
        out.append("    </section>")

    return "\n".join(out)


# --- Page shell ------------------------------------------------------------

def nav(cats: list[dict], active: str | None, depth: int) -> str:
    out = ['    <nav class="tabs" aria-label="Sections">']
    for cat in cats:
        slug, name = cat["slug"], cat["name"]
        n = len(cat.get("entries") or []) or len(cat.get("courses") or [])
        current = ' aria-current="page"' if slug == active else ""
        out.append(
            f'      <a class="tab" href="{e(rel(slug + "/", depth))}" '
            f'data-slug="{slug}"{current}>\n'
            f'        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{ICONS[slug]}</svg>\n'
            f'        <span>{e(name)}</span><span class="tab-count">{n}</span>\n'
            f'      </a>')
    out.append("    </nav>")
    return "\n".join(out)


def shell(*, site, cats, title, description, path, depth, active, hero, main,
          index_json, total, hash_redirect=False, canonical_path=None) -> str:
    base = site["url"].rstrip("/") + "/"
    # The front page shows the PDF entries, so it names /pdfs/ as canonical
    # rather than advertising two URLs for one listing.
    canonical = base + (path if canonical_path is None else canonical_path)
    nl = "\n"

    redirect = ""
    if hash_redirect:
        redirect = """
      // Old #pdfs-style links are still in the wild; send them to the page.
      var slugs = %s;
      var h = location.hash.replace('#', '').toLowerCase();
      if (slugs.indexOf(h) !== -1) location.replace(h + '/');
""" % json.dumps([c["slug"] for c in cats])

    return f'''<!DOCTYPE html>
<html lang="en" class="no-js">

<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{e(title)}</title>
  <meta name="description" content="{e(description)}">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#f4f5f8">
  <link rel="canonical" href="{e(canonical)}">

  <meta property="og:type" content="website">
  <meta property="og:url" content="{e(canonical)}">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:image" content="{e(base)}android-chrome-512x512.png">
  <meta name="twitter:card" content="summary">

  <link rel="apple-touch-icon" sizes="180x180" href="{rel("apple-touch-icon.png", depth)}">
  <link rel="icon" type="image/png" sizes="32x32" href="{rel("favicon-32x32.png", depth)}">
  <link rel="icon" type="image/png" sizes="16x16" href="{rel("favicon-16x16.png", depth)}">
  <link rel="icon" type="image/svg+xml" href="{rel("static/icon.svg", depth)}">
  <link rel="mask-icon" href="{rel("safari-pinned-tab.svg", depth)}" color="#4f5bd5">
  <meta name="msapplication-TileColor" content="#4f5bd5">
  <meta name="msapplication-config" content="{rel("browserconfig.xml", depth)}">
  <link rel="manifest" href="{rel("manifest.webmanifest", depth)}">

  <link rel="stylesheet" href="{asset("static/css/directory.css", depth)}">

  <script>
    // Runs before first paint, so none of this can flash.
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
{redirect}    }})();
  </script>
</head>

<body>
{SPRITE}

  <a class="skip-link" href="#main">Skip to content</a>

  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="{rel("", depth) or "./"}">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 6a2 2 0 0 1 2-2h3l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>
          </svg>
        </span>
        <span class="brand-text">{e(site["title"])}</span>
      </a>

      <div class="header-actions">
        <button class="icon-btn theme-btn" type="button" data-theme-toggle aria-label="Switch theme" data-tip="Switch theme">
          <svg data-theme-icon="system" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/></svg>
          <svg data-theme-icon="light" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
          <svg data-theme-icon="dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
        </button>

        <a class="icon-btn" href="{e(site["author_url"])}" aria-label="{e(site["author_url"])}" data-tip="{e(site["author_url"])}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3.6 9h16.8M3.6 15h16.8"/><path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"/></svg>
        </a>
      </div>
    </div>
  </header>

{hero}
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

      <div class="sort-control">
        <label class="visually-hidden" for="sort">Sort entries</label>
        <svg class="sort-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 4v16"/><path d="m3 8 4-4 4 4"/><path d="M17 20V4"/><path d="m13 16 4 4 4-4"/></svg>
        <select id="sort" data-sort>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="az">A – Z</option>
        </select>
      </div>

      <div class="view-switch" role="group" aria-label="Layout">
        <button type="button" data-view="grid" aria-pressed="true" aria-label="Grid view" data-tip="Grid view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>
        </button>
        <button type="button" data-view="list" aria-pressed="false" aria-label="List view" data-tip="List view">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/></svg>
        </button>
      </div>
    </div>
  </div>

  <main id="main" class="container" data-base="{rel("", depth) or "./"}">
{nav(cats, active, depth)}

    <div class="results-bar">
      <span data-results-text></span>
      <button type="button" data-search-clear>Clear search</button>
    </div>

    <p class="visually-hidden" role="status" aria-live="polite" data-live></p>

{main}

    <section class="elsewhere" hidden>
      <h2>Found in other sections</h2>
      <ul class="cards" data-elsewhere></ul>
    </section>

    <div class="empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/><path d="M8.5 11h5"/></svg>
      <h2>Nothing matches “<span data-empty-term></span>”</h2>
      <p>Try a shorter word, or a different spelling.</p>
    </div>
  </main>

  <dialog class="link-modal" tabindex="-1" aria-labelledby="link-modal-title">
    <div class="link-modal-head">
      <h2 id="link-modal-title"></h2>
      <button class="icon-btn" type="button" data-close-modal aria-label="Close">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>
    <p class="link-modal-note" data-modal-note hidden></p>
    <ul class="link-modal-list" data-modal-list></ul>
  </dialog>

  <div class="tip" role="presentation" aria-hidden="true"></div>

  <button class="to-top" type="button" aria-label="Back to top" data-tip="Back to top">
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

  <script type="application/json" id="search-index">{index_json}</script>
  <script src="{asset("static/js/directory.js", depth)}" defer></script>
  <script>
    if ('serviceWorker' in navigator) {{
      window.addEventListener('load', function () {{
        navigator.serviceWorker
          .register('{rel("sw.js", depth)}', {{ scope: '{rel("", depth) or "./"}' }})
          .catch(function () {{}});
      }});
    }}
  </script>
</body>

</html>
'''


# --- Page assembly ---------------------------------------------------------

def search_index(cats: list[dict]) -> str:
    """Every entry on the site as [title, category-slug, tags].

    Small enough to inline on every page (about 30KB), which is what lets a
    search from /pdfs/ still find something filed under /datasets/ without any
    page carrying another page's markup.
    """
    rows = []
    for cat in cats:
        for entry in cat.get("entries") or []:
            rows.append([entry["title"], cat["slug"], tags_of(entry)])
        for course in cat.get("courses") or []:
            rows.append([course["title"], cat["slug"], []])
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def count_label(n: int, slug: str, courses: list) -> str:
    noun = "course" if courses or slug == "courses" else "entry"
    plural = "courses" if noun == "course" else "entries"
    return f"{n} {noun if n == 1 else plural}"


def build_pages(doc: dict, routes: dict[str, dict] | None = None) -> dict[str, str]:
    site, cats = doc["site"], doc["categories"]
    total = sum(len(c.get("entries") or []) or len(c.get("courses") or []) for c in cats)
    index_json = search_index(cats)
    pages: dict[str, str] = {}

    for cat in cats:
        if cat["slug"] not in ICONS:
            raise SystemExit(f"category {cat['slug']!r} has no icon; add one to ICONS")

    # --- the front page ----------------------------------------------------
    # It lists the PDF entries rather than a menu of categories: that is the
    # section that actually gets used, and the nav already names the others.
    front = next((c for c in cats if c["slug"] == "pdfs"), cats[0])
    front_entries = front.get("entries") or []

    hero = f'''  <div class="container hero">
    <h1>{e(site["heading"])} <span class="accent">{e(site["heading_accent"])}</span></h1>
    <p>{e(site["tagline"])}</p>
  </div>

'''

    body = ['    <ul class="cards">']
    body += [render_entry(x, 0, i) for i, x in enumerate(ordered(front_entries))]
    body.append("    </ul>")

    pages["index.html"] = shell(
        site=site, cats=cats, title=f'{site["title"]} — files, links, tools and datasets',
        description=(f'A hand-kept directory of {total}+ PDFs, reading links, web tools '
                     f'and open datasets, collected by {site["author"]}.'),
        path="", depth=0, active=front["slug"], hero=hero, main="\n".join(body),
        index_json=index_json, total=total, hash_redirect=True,
        canonical_path=f'{front["slug"]}/')

    # --- one page per category ---------------------------------------------
    for cat in cats:
        slug, name = cat["slug"], cat["name"]
        entries = cat.get("entries") or []
        courses = cat.get("courses") or []
        n = len(entries) or len(courses)

        head = (f'  <div class="container hero hero-section">\n'
                f'    <h1>{e(name)}</h1>\n'
                + (f'    <p>{e(cat["blurb"])}</p>\n' if cat.get("blurb") else "")
                + f'    <p class="hero-count">{count_label(n, slug, courses)}</p>\n'
                f'  </div>\n\n')

        if entries:
            body = ['    <ul class="cards">']
            body += [render_entry(x, 1, i) for i, x in enumerate(ordered(entries))]
            body.append("    </ul>")
        elif courses:
            body = ['    <ul class="course-cards">']
            body += [render_course_card(c, 1) for c in courses]
            body.append("    </ul>")
        else:
            body = ['    <div class="section-empty">',
                    '      <p>Nothing here yet.</p>',
                    f'      <p class="section-empty-hint">Add entries to <code>{slug}</code> '
                    'in <code>data/links.yml</code> and they will appear here.</p>',
                    '    </div>']

        pages[f"{slug}/index.html"] = shell(
            site=site, cats=cats, title=f'{name} — {site["title"]}',
            description=(cat.get("blurb") or f'{n} entries filed under {name}.'),
            path=f"{slug}/", depth=1, active=slug, hero=head, main="\n".join(body),
            index_json=index_json, total=total)

        # --- one page per course -------------------------------------------
        for course in courses:
            mods, mats = course_counts(course)
            pages[f'{slug}/{course["slug"]}/index.html'] = shell(
                site=site, cats=cats,
                title=f'{course["title"]} — {name} — {site["title"]}',
                description=(course.get("description")
                             or f'{mats} materials across {mods} modules.'),
                path=f'{slug}/{course["slug"]}/', depth=2, active=slug,
                hero="", main=render_course_page(course, 2),
                index_json=index_json, total=total)

    # --- one page per declared PDF -----------------------------------------
    # Same dictionary as everything else, so there is one build and one place
    # that decides what the site contains.
    for slug, route in sorted((routes or {}).items()):
        pages[f"v/{slug}/index.html"] = render_viewer(
            route["title"], route["target"], slug, embed=route["kind"] == "embed")

    return pages


def unreferenced_pdfs(routes: dict[str, dict]) -> list[str]:
    """PDFs sitting in assets/ that nothing in links.yml points at.

    Reported, never fatal: an unused file costs nothing but a little space, and
    deleting someone's document because it lost its last link would be worse.
    """
    used = {r["target"] for r in routes.values() if r["kind"] == "pdf"}
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in ASSETS.rglob("*")
        if p.is_file() and p.suffix.lower() == ".pdf"
        and p.relative_to(ROOT).as_posix() not in used)


def validate_generated_routes(pages: dict[str, str], routes: dict[str, dict]) -> list[str]:
    """Every declared PDF has a page, and every page points at its own PDF."""
    problems = []
    for slug, route in routes.items():
        path = f"v/{slug}/index.html"
        page = pages.get(path)
        if page is None:
            problems.append(f"{path}: declared by {route['title']!r} but not generated")
            continue
        if route["kind"] == "embed":
            want = route["target"]
        else:
            want = urllib.parse.quote(
                rel(route["target"], viewer_depth(slug)), safe="")
        if e(want) not in page:
            problems.append(f"{path}: does not reference {route['target']}")
    return problems


def validate_rendered_links(doc: dict, pages: dict[str, str]) -> list[str]:
    """Every link in links.yml reached the page it belongs on.

    The expected href comes from `rel()` — the same function the renderer
    used — so this checks the pages, not a second guess at how a URL is built.
    """
    problems = []

    def check(url: str, path: str, depth: int, where: str) -> None:
        page = pages.get(path, "")
        if f'href="{e(rel(url, depth))}"' not in page:
            problems.append(f"{where}: {url} missing from {path}")

    for cat in doc["categories"]:
        slug = cat["slug"]
        for entry in cat.get("entries") or []:
            for link in all_links(entry):
                check(link["url"], f"{slug}/index.html", 1, slug)
        for course in cat.get("courses") or []:
            cpath = f'{slug}/{course["slug"]}/index.html'
            for link in course.get("links") or []:
                check(link["url"], cpath, 2, course["slug"])
            for module in course.get("modules") or []:
                for mat in module.get("materials") or []:
                    check(mat["url"], cpath, 2, course["slug"])

    # The front page lists the PDF entries, so they have to be there too.
    front = next((c for c in doc["categories"] if c["slug"] == "pdfs"), None)
    for entry in (front or {}).get("entries") or []:
        for link in all_links(entry):
            check(link["url"], "index.html", 0, "front page")

    return problems


def copy_runtime(out: pathlib.Path) -> None:
    for name in RUNTIME:
        src = ROOT / name
        if not src.exists():
            print(f"  note: {name} does not exist; not copied")
            continue
        dest = out / name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)


def load() -> tuple[dict, dict[str, dict], dict[str, str]]:
    """links.yml -> validated, normalized document, its routes and its pages."""
    doc, routes = normalize(yaml.safe_load(LINKS.read_text(encoding="utf-8")))
    return doc, routes, build_pages(doc, routes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=str(OUT_DEFAULT), type=pathlib.Path,
                    help="where to write the site (default: _site)")
    ap.add_argument("--validate", action="store_true",
                    help="check the data and the rendered pages, write nothing")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the output directory is not what this would write")
    args = ap.parse_args()

    doc, routes, pages = load()

    entries = sum(len(c.get("entries") or []) for c in doc["categories"])
    links = sum(len(all_links(x)) for c in doc["categories"]
                for x in (c.get("entries") or []))
    multi = sum(1 for c in doc["categories"] for x in (c.get("entries") or [])
                if len(all_links(x)) > 1)
    viewers = len(routes)

    if args.validate:
        problems = (validate_generated_routes(pages, routes)
                    + validate_rendered_links(doc, pages))
        if links < 400:
            problems.append(f"only {links} links in links.yml — refusing to publish")
        for path in unreferenced_pdfs(routes):
            print(f"warning: unreferenced PDF: {path}")
        if problems:
            print("validation failed:", file=sys.stderr)
            for p in problems[:40]:
                print(f"  {p}", file=sys.stderr)
            return 1
        print(f"ok: {entries} entries, {links} links, {viewers} viewer routes, "
              f"{len(pages)} pages")
        return 0

    out = args.output_dir

    if args.check:
        stale = [path for path, page in sorted(pages.items())
                 if not (out / path).exists()
                 or (out / path).read_text(encoding="utf-8") != page]
        if stale:
            print(f"out of date — run: python3 scripts/build.py", file=sys.stderr)
            for path in stale[:20]:
                print(f"  {path}", file=sys.stderr)
            return 1
        print(f"{len(pages)} pages up to date ({entries} entries, {links} links)")
        return 0

    # Built from scratch every time: a route that is no longer declared has to
    # disappear from the output, not linger because nothing deleted it.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for path, page in sorted(pages.items()):
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")

    copy_runtime(out)

    for path in unreferenced_pdfs(routes):
        print(f"  warning: unreferenced PDF: {path}")

    size = sum(len(p) for p in pages.values())
    print(f"{len(pages)} pages into {out.name}/ — {entries} entries, {links} links, "
          f"{multi} of them open a modal, {viewers} viewer routes ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
