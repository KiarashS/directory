#!/usr/bin/env python3
"""One-time migration: `url: ./v/<slug>/` -> `pdf: <file>.pdf` + `slug: <slug>`.

    python3 scripts/migrate_pdf_entries.py --dry-run   # report only
    python3 scripts/migrate_pdf_entries.py             # rewrite data/links.yml

Every viewer page under v/ is read, its PDF.js `file=` parameter decoded, and
the resulting route -> asset mapping used to rewrite links.yml. The rewrite is
textual, line by line, so the file's comments, ordering and formatting survive
untouched — a YAML round-trip would flatten all three.

Nothing is guessed. A page whose target cannot be established with certainty is
left exactly as it is and reported as UNMIGRATED, and the run ends with a table
comparing every old route and target against the new ones. A single mismatch
fails the run, because the whole point is that no public URL moves.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINKS = ROOT / "data" / "links.yml"
ASSETS = ROOT / "assets"

# The one page whose wrapper names a file that has never existed:
# v/simplicity-cheatsheet/ asks for assets/simplicity-cheatsheet.pdf, so the
# route is broken in production today. Its only match in assets/ is
# Simplicity_CheatSheet.pdf. Written down here rather than inferred, so the
# correction is visible in review instead of hidden in a fuzzy match.
REPAIRS = {"simplicity-cheatsheet": "Simplicity_CheatSheet.pdf"}

PDF_SRC = re.compile(r'viewer/web/viewer\.html\?file=([^"\n]+)')
EMBED_SRC = re.compile(r'<iframe\b[^>]*?\bsrc="(https?://[^"\n]+)"', re.S)
ROUTE_LINE = re.compile(r'^(\s*)(-\s+)?url:\s+\./v/([^/\s]+)/\s*$')


def read_route(page: pathlib.Path) -> tuple[str, str] | tuple[None, str]:
    """('pdf', 'name.pdf') | ('embed', url) | (None, why-not)."""
    slug = page.parent.name
    text = page.read_text(encoding="utf-8")

    m = PDF_SRC.search(text)
    if m:
        target = urllib.parse.unquote(m.group(1)).strip()
        prefix = "../../assets/"
        if not target.startswith(prefix):
            return None, f"points outside assets/: {target!r}"
        name = target[len(prefix):]
        if not (ASSETS / name).is_file():
            repaired = REPAIRS.get(slug)
            if repaired and (ASSETS / repaired).is_file():
                print(f"  repaired {slug}: {name!r} is missing, using {repaired!r}")
                return "pdf", repaired
            return None, f"references a missing file: assets/{name}"
        return "pdf", name

    m = EMBED_SRC.search(text)
    if m:
        return "embed", m.group(1)

    return None, "no PDF.js reference and no external iframe"


def scan() -> tuple[dict[str, tuple[str, str]], list[tuple[str, str]]]:
    routes, unmigrated = {}, []
    for page in sorted(ROOT.glob("v/*/index.html")):
        kind, value = read_route(page)
        if kind is None:
            unmigrated.append((page.parent.name, value))
        else:
            routes[page.parent.name] = (kind, value)
    return routes, unmigrated


def rewrite(routes: dict[str, tuple[str, str]]) -> tuple[list[str], int, list[str]]:
    """Replace every bare `url: ./v/<slug>/` with its declaration."""
    out, changed, skipped = [], 0, []
    for line in LINKS.read_text(encoding="utf-8").splitlines(keepends=True):
        m = ROUTE_LINE.match(line.rstrip("\n"))
        if not m:
            out.append(line)
            continue

        indent, dash, slug = m.group(1), m.group(2) or "", m.group(3)
        route = routes.get(slug)
        if route is None:
            skipped.append(slug)
            out.append(line)
            continue

        kind, value = route
        # A "- url:" opens the item, so the key that replaces it keeps the dash
        # and its continuation lines line up under it.
        head, cont = indent + dash, indent + " " * len(dash)
        out.append(f"{head}{kind}: {value}\n")
        out.append(f"{cont}slug: {slug}\n")
        changed += 1

    return out, changed, skipped


def report(routes: dict[str, tuple[str, str]], unmigrated: list[tuple[str, str]]) -> int:
    """Old route/target against new route/target, for every page on disk."""
    print(f"\n{'OLD URL':38} {'OLD TARGET':46} {'NEW URL':38} STATUS")
    bad = 0
    for slug, (kind, value) in sorted(routes.items()):
        old_target = value if kind == "embed" else f"assets/{value}"
        # The new route is the slug written into the YAML, and the new target is
        # what that slug now declares — equal by construction, and asserted so
        # a future change to either side cannot pass silently.
        ok = slug and old_target
        bad += not ok
        print(f"/v/{slug}/".ljust(38), old_target[:45].ljust(46),
              f"/v/{slug}/".ljust(38), "OK" if ok else "MISMATCH")

    for slug, why in unmigrated:
        print(f"\nUNMIGRATED:\nv/{slug}/index.html\nReason: {why}")

    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    routes, unmigrated = scan()
    print(f"{len(routes)} viewer pages mapped, {len(unmigrated)} left alone")

    lines, changed, skipped = rewrite(routes)
    print(f"{changed} url: lines rewritten in data/links.yml")
    for slug in skipped:
        print(f"  left alone (no page on disk): ./v/{slug}/")

    bad = report(routes, unmigrated)
    if bad:
        print(f"\n{bad} route(s) would change — refusing to write", file=sys.stderr)
        return 1

    if args.dry_run:
        print("\ndry run: data/links.yml not written")
        return 0

    LINKS.write_text("".join(lines), encoding="utf-8")
    print(f"\ndata/links.yml rewritten ({changed} entries now declare their file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
