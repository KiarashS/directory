# My Directory

The site behind [directory.kiarashs.ir](https://directory.kiarashs.ir/): a hand-kept
collection of PDFs, reading links, web tools and open datasets.

## Pages

Each category is a real page, not a fragment:

| URL | |
| --- | --- |
| `/` | the PDF entries, with `/pdfs/` as its canonical URL |
| `/pdfs/`, `/links/`, `/tools/`, `/datasets/` | that category's entries |
| `/talks/` | talks, presentations and slide decks |
| `/courses/` | the course list |
| `/courses/<slug>/` | one course, its modules and materials |

Search still spans everything. Each page carries a small index of every entry on
the site, so a search from `/pdfs/` turns up matches in `/datasets/` and links
across to them. Old `#pdfs`-style links redirect to `/pdfs/`.

A search is in the URL as `?q=`, so it can be shared: `/?q=python` and
`/datasets/?q=mri` both arrive already filtered. Typing rewrites the address with
`replaceState`, so the Back button still goes back a page rather than a
keystroke, and clearing the box drops the parameter.

## Adding or changing a link

Everything on the site comes from [`data/links.yml`](data/links.yml). Edit that file —
in the GitHub web editor is fine — and the site rebuilds and republishes itself.
Nothing else needs touching; the HTML is generated and should never be edited
by hand.

An entry is a title and a URL:

```yaml
- title: Fluent Python 2nd Edition
  url: https://example.com/fluent-python
```

Give it a `links:` list and the card stops navigating directly. It opens a modal
showing every link instead:

```yaml
- title: Docker Cheat sheet 1
  url: ./v/docker-cheatsheet/
  links:
    - text: Docker Cheat sheet 2
      url: ./v/docker-cheatsheet-2/
    - text: Docker Cheat sheet 3
      url: https://example.com/docker
```

A URL starting with `./` is a file in this repository — a PDF under `assets/`
shown through the viewer pages in `v/`. Anything else is treated as external and
opens in a new tab.

### Tags, pinning and dates

```yaml
- title: Fluent Python 2nd Edition
  url: https://example.com/book
  tags: [python, reference]
  pinned: true
  added: 2026-08-28
```

Tags render as chips and are clickable: a chip links to `?q=tag:python`, which
matches only entries carrying that tag — a plain search for `python` still
matches titles and link text as well. Several `tag:` terms intersect, so
`tag:python tag:reference` finds entries with both.

`pinned: true` holds an entry at the top of its page under every sort order.

`added` sets the default order, newest first. A sort control next to the view
switch offers Newest, Oldest and A–Z, and remembers your choice. Entries with no
`added` keep the order they have in `links.yml` and sit below the dated ones, so
dating the archive gradually never scrambles what is already there.

### Talks

A talk is an ordinary entry with two extras, shown as a line under the title:

```yaml
- title: Making a static site searchable
  url: ./v/slides-deck/
  event: PyCon
  date: 2026-05-14
  tags: [search]
  links:
    - text: Recording
      url: https://example.com/video
```

Slides, video, code and paper are just its links, so a talk with several opens
the same modal everything else does.

### Descriptions

Optional, and always yours to write — nothing is fetched or generated. An entry
with a `description` gets a small (i) button in the top-right corner of its
card, and the text appears in a popover on hover or keyboard focus. On a touch
screen, tapping the button toggles it.

```yaml
- title: Simple Icons
  url: https://simpleicons.org/
  description: 3052 free SVG icons for popular brands.
```

Sub-links take one too, and it shows next to that link inside the modal:

```yaml
links:
  - text: Errata
    url: https://example.com/errata
    description: Corrections through the third printing.
```

Entries without a `description` get no (i) button. Descriptions are searchable
either way.

## Courses

A course gets its own page. Materials go in modules, and each one can name a
`type` so it renders with the right icon and label:

```yaml
- slug: courses
  name: Courses
  courses:
    - slug: intro-ml
      title: Introduction to Machine Learning
      institution: Sharif University of Technology
      instructor: Some Lecturer
      term: Spring 2026
      description: One or two lines about the course.
      links:                       # optional, shown at the top of the page
        - text: Syllabus
          url: ./assets/syllabus.pdf
      modules:
        - title: Week 1 — Linear regression
          summary: Optional line under the module heading.
          materials:
            - title: Lecture slides
              url: ./v/wk1-slides/
              type: slides
            - title: Problem set 1
              url: ./assets/ps1.pdf
              type: assignment
              description: Due at the end of week two.
```

`type` is one of `slides`, `notes`, `assignment`, `reading`, `video`, `code`,
`dataset`. Anything else still renders, just without an icon. A course with no
`modules` yet shows an empty state rather than a blank page.

## How the build works

`.github/workflows/build.yml` runs on any push that touches `data/links.yml`,
`scripts/`, or `static/`:

1. `scripts/build.py` renders every page from the YAML.
2. A check asserts every URL in the YAML appears on the page it belongs on.
3. The regenerated pages are committed, and the site deploys to Pages.

Because the workflow only triggers on its *inputs*, its own commit does not set
off another run. The build needs no network access.

To run it locally:

```bash
pip install pyyaml
python3 scripts/build.py                # writes every page
python3 scripts/make_favicon.py         # only after editing the icon
python3 scripts/build.py --check        # exits 1 if any page is stale
python3 -m http.server                  # then open http://localhost:8000
```

## Layout

| Path | What it is |
| --- | --- |
| `data/links.yml` | Every entry on the site. The only file you edit. |
| `scripts/build.py` | Renders every page. |
| `scripts/make_favicon.py` | Regenerates the icon set from `static/icon.svg`. |
| `static/css/directory.css`, `static/js/directory.js` | The front end. |
| `index.html`, `<category>/index.html` | Generated output. Do not edit. |
| `assets/`, `v/`, `viewer/` | The PDFs and the pdf.js viewer that displays them. |
