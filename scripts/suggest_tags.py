#!/usr/bin/env python3
"""One-shot: propose tags for entries that have none.

    python3 scripts/suggest_tags.py --dry-run   # print what it would add
    python3 scripts/suggest_tags.py             # write them into links.yml

The archive was imported from a site that had no tags, so 371 of 374 entries
carry none and the tag chips, the `tag:` search and a good deal of the sort
control have nothing to work with. This proposes a starting set from what each
entry already says about itself — its title and the text of its sub-links.

Every pattern is word-boundary anchored, which matters more than it sounds:
an unanchored 'ui' tags "B(ui)lding Grammar Skills" and "G(ui)de" as design.

Nothing here is clever, and nothing is certain. It never touches an entry that
already has tags, it rewrites the file textually so comments and ordering
survive, and the result is a diff for a person to read before it ships.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINKS = ROOT / "data" / "links.yml"

# tag -> what, in a title, means it. Deliberately conservative: a tag that is
# wrong is worse than a tag that is missing, because a wrong one sends someone
# to the wrong shelf and quietly erodes trust in the whole vocabulary.
VOCAB = {
    "python":           r"python|pandas|numpy|django|flask|pytest|matplotlib",
    "sql":              r"\bsql\b|postgres|mysql|sqlite|\bdatabase|\bdba\b|t-sql",
    "javascript":       r"javascript|\bjs\b|typescript|\breact\b|\bvue\b|\bnode\b",
    "csharp":           r"\bc#|\.net\b|asp\.?net|linq",
    "toefl":            r"\btoefl\b",
    "gre":              r"\bgre\b",
    "english":          (r"grammar|vocabular|collocation|preposition|phrase|writing"
                         r"|speaking|idiom|\bverbs?\b|transition|\bessay|dictionary"
                         r"|pronunciation|\bwords?\b"),
    "machine-learning": r"machine learning|deep learning|neural|\bml\b|pytorch|tensorflow|keras",
    "statistics":       r"statistic|probabilit|regression|bayes",
    "math":             r"\bmath|calculus|algebra|formula|derivative|integral|geometry|convergence",
    "git":              r"\bgit\b|github",
    "docker":           r"docker|kubernetes|container",
    "linux":            r"\blinux\b|\bbash\b|\bshell\b|\bawk\b|\bsed\b|\bvim\b|command line",
    "design":           r"\bdesign\b|\bcss\b|\bui\b|\bux\b|figma|\bcolou?rs?\b|\bicons?\b",
    "security":         r"security|crypto|hacking|penetration|\bowasp\b",
    "data-science":     r"data science|data analysis|visuali[sz]ation|\bdatasets?\b",
    "cheatsheet":       r"cheat ?sheet|\breference\b",
    "algorithms":       r"algorithm|data structure|leetcode|interview",
    "ai":               r"artificial intelligence|\bai\b|\bllm\b|\bgpt\b|\bprompt",
    "agile":            r"\bagile\b|\bscrum\b|kanban",
}
PATTERNS = {tag: re.compile(pat, re.I) for tag, pat in VOCAB.items()}

# An entry at the top level of a category's `entries:` list. Nested links open
# with "- text:" and courses with "- slug:", so neither is matched here.
ENTRY_LINE = re.compile(r"^  - title:")
# The entry's own keys, at exactly four spaces. A sub-link's keys are deeper.
OWN_KEY = re.compile(r"^    (url|pdf|slug|embed|event|date|added):")


def tags_for(entry: dict) -> list[str]:
    hay = entry["title"] + " " + " ".join(
        l.get("text", "") for l in entry.get("links") or [])
    # Underscores read as spaces here: half these titles are file names, and
    # \b sees no boundary inside "GRE_Equation_Guide", so `\bgre\b` would miss it.
    return sorted(tag for tag, pat in PATTERNS.items()
                  if pat.search(hay.replace("_", " ")))


def proposals() -> list[list[str]]:
    """One entry per top-level entry, in file order: the tags to add, or []."""
    doc = yaml.safe_load(LINKS.read_text(encoding="utf-8"))
    out = []
    for cat in doc["categories"]:
        for entry in cat.get("entries") or []:
            out.append([] if entry.get("tags") else tags_for(entry))
    return out


def rewrite(plan: list[list[str]]) -> tuple[str, int]:
    """Insert a tags: line after each entry's own url/pdf/slug block."""
    lines = LINKS.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    idx = -1          # which top-level entry we are inside
    last_own = None   # index in `out` of that entry's last own key line
    title_at = None   # its "- title:" line, the fallback anchor
    added = 0

    def flush() -> None:
        nonlocal added, last_own, title_at
        # An entry that is nothing but a title and a links: list has no own
        # url/pdf/slug line, so anchor on the title instead of skipping it.
        anchor = last_own if last_own is not None else title_at
        if idx >= 0 and anchor is not None and plan[idx]:
            out.insert(anchor + 1, f'    tags: [{", ".join(plan[idx])}]\n')
            added += 1
        last_own = title_at = None

    for line in lines:
        if ENTRY_LINE.match(line):
            flush()
            idx += 1
            out.append(line)
            title_at = len(out) - 1
            continue
        out.append(line)
        if idx >= 0 and OWN_KEY.match(line):
            last_own = len(out) - 1
    flush()
    return "".join(out), added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = ap.parse_args()

    plan = proposals()
    doc = yaml.safe_load(LINKS.read_text(encoding="utf-8"))
    titles = [x["title"] for c in doc["categories"] for x in (c.get("entries") or [])]
    if len(plan) != len(titles):
        print("entry count mismatch; refusing to write", file=sys.stderr)
        return 1

    hits = collections.Counter(t for tags in plan for t in tags)
    n = sum(1 for t in plan if t)
    print(f"{n} of {len(plan)} entries would gain tags; "
          f"{len(plan) - n} left alone (already tagged, or nothing matched)")
    print("vocabulary used: "
          + ", ".join(f"{t}({c})" for t, c in hits.most_common()))

    if args.dry_run:
        print()
        for title, tags in zip(titles, plan):
            if tags:
                print(f"  {title[:56]:58} {', '.join(tags)}")
        return 0

    text, added = rewrite(plan)
    # Round-trip before writing: the rewrite is textual, so the only real
    # proof it stayed valid is parsing it back and finding the entries intact.
    reparsed = yaml.safe_load(text)
    after = [x["title"] for c in reparsed["categories"] for x in (c.get("entries") or [])]
    if after != titles:
        print("rewrite changed the entries; refusing to write", file=sys.stderr)
        return 1

    LINKS.write_text(text, encoding="utf-8")
    print(f"\ndata/links.yml: {added} entries tagged. Review the diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
