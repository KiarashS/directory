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
  pdf: docker-cheatsheet.pdf
  links:
    - text: Docker Cheat sheet 2
      pdf: docker-cheatsheet-2.pdf
    - text: Docker Cheat sheet 3
      url: https://example.com/docker
```

`url:` is an external address and opens in a new tab. `pdf:` is one of your own
files under `assets/`, and the build gives it a reader page of its own.

## Adding a PDF

Three steps, and none of them is writing HTML.

**1.** Put the file in `assets/`:

```
assets/xai-cheat-sheet.pdf
```

**2.** Add an entry to `data/links.yml`:

```yaml
- title: Explainable AI Cheat Sheet
  pdf: xai-cheat-sheet.pdf
  tags: [ai, xai]
  added: 2026-09-01
```

**3.** Commit and push.

The site then creates `/v/xai-cheat-sheet/` and opens the PDF there in the
built-in pdf.js reader. Nothing under `v/` or `viewer/` is ever edited by hand —
`v/` does not exist in this repository at all; it is generated at build time.

An entry needs `title` and `pdf`. `slug`, `description`, `tags`, `pinned`,
`added` and `links` are all optional, and `pdf:` works the same way in a nested
`links:` list and in a course's `materials:`.

The build refuses to publish rather than shipping a broken reader page, so it
stops if a `pdf:` names a file that is missing, is not a `.pdf`, does not begin
with a `%PDF-` signature, or points outside `assets/`. Two entries claiming the
same viewer URL stop it too, naming both.

### Custom slugs

The reader URL mirrors the file's path under `assets/`, so
`xai-cheat-sheet.pdf` becomes `/v/xai-cheat-sheet/` and
`courses/intro-ml/lecture-01.pdf` becomes `/v/courses/intro-ml/lecture-01/`.
Set `slug:` to choose it yourself:

```yaml
- title: Probability & Statistics
  pdf: Probability_Statistics.pdf
  slug: probability-statistics       # -> /v/probability-statistics/
```

**A slug is a public URL.** Changing one on an entry that is already published
breaks every existing link and bookmark to it, so leave existing slugs alone.
Every PDF already on the site carries its slug explicitly for exactly that
reason, even where the derived one would have matched.

A PDF can also be reached with a page number, which the reader opens directly:

```yaml
- text: Causative verbs 2
  url: ./v/betty-blue/?page=37
```

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
  pdf: slides-deck.pdf
  event: PyCon
  by: Kiarash Soleimanzadeh
  location: Tehran, Iran
  date: 2026-05-14
  tags: [search]
  links:
    - text: Recording
      url: https://example.com/video
```

`event`, `by` and `location` are all optional and join into one line under the
title, separated by `·`.

Slides, video, code and paper are just its links, so a talk with several opens
the same modal everything else does.

### Descriptions

Optional, and always yours to write — nothing is fetched or generated. An entry
with a `description` gets a small (i) button in the top-right corner of its
card, and the text appears in a popover on hover or keyboard focus. On a touch
screen, tapping the button toggles it.

The popover and the tooltips on the toolbar controls share one surface, so they
read as the same object. Those tooltips replace the browser's built-in `title`
box, which cannot be styled, waits about a second to appear, and never shows on
keyboard focus.

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

A course gets its own page, and its files live in a folder of its own:

```
assets/courses/intro-ml/syllabus.pdf
assets/courses/intro-ml/wk1-slides.pdf
```

A material names only its file — the build already knows which course it
belongs to, and looks in `assets/courses/<course-slug>/`. Its reader URL
mirrors that path, so two courses can each have a `lecture-01.pdf` and neither
needs a hand-written `slug:`:

```
assets/courses/intro-ml/lecture-01.pdf  ->  /v/courses/intro-ml/lecture-01/
```

Materials go in modules, and each one can name a `type` so it renders with the
right icon and label. **Upload the files first** — the example below is a shape
to fill in, not something to paste as-is: every `pdf:` must name a file that
actually exists, or the build stops with `PDF not found` and the site stays on
its last good version rather than publishing a broken reader page.

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
          pdf: syllabus.pdf
      modules:
        - title: Week 1 — Linear regression
          summary: Optional line under the module heading.
          materials:
            - title: Lecture slides
              pdf: wk1-slides.pdf
              type: slides
            - title: Problem set 1
              pdf: ps1.pdf
              type: assignment
              description: Due at the end of week two.
```

`type` is one of `slides`, `notes`, `assignment`, `reading`, `video`, `code`,
`dataset`. Anything else still renders, just without an icon. A course with no
`modules` yet shows an empty state rather than a blank page.

## How the build works

The pages are build output, not repository content. Nothing generated is
committed: `.github/workflows/build.yml` renders the whole site into `_site/`
and hands that to Pages, so the repository holds only what a person writes.

It runs on a push touching `data/`, `assets/`, `scripts/`, `static/` or
`viewer/` — adding a PDF is a change to `assets/`, so uploading one is enough to
trigger a deploy:

1. `python3 -m unittest discover -s scripts` — the PDF model.
2. `scripts/build.py --validate` — every PDF resolves, every route is unique,
   and every URL in the YAML reached the page it belongs on.
3. `scripts/build.py --output-dir _site` — the pages, plus `assets/`, `static/`,
   `viewer/`, `sw.js`, the manifests and the icons.
4. The artifact deploys to Pages.

The build needs no network access and is deterministic: same inputs, byte-identical
output. `_site/` is deleted and rebuilt every run, so a route that is no longer
declared disappears instead of lingering.

`viewer/` is the pdf.js distribution and is maintained on its own by
`.github/workflows/update-pdfjs.yml`. Adding or removing a PDF never touches it.

That workflow tracks the **legacy** pdf.js build (`pdfjs-<v>-legacy-dist.zip`),
and it should stay that way. Every release also ships a plain `-dist.zip` that
is roughly 1MB smaller across the whole viewer, but from v6 on it calls
`Map.prototype.getOrInsertComputed` — an ES2026 method that needs Chrome 145,
Firefox 144 or Safari 18.4. Below those the viewer throws before drawing
anything, so every PDF on the site is a blank page. The legacy build is the
same version with core-js polyfills. The workflow checks for the polyfill and
fails rather than publishing a reader without it.

To run it locally:

```bash
pip install pyyaml
python3 scripts/build.py                          # renders into _site/
python3 scripts/build.py --validate               # checks, writes nothing
python3 -m unittest discover -s scripts           # the tests
python3 scripts/make_favicon.py                   # only after editing the icon
python3 -m http.server --directory _site          # then open http://localhost:8000
```

### Working on it without the PDFs

`assets/` is 387 MB, and a full clone pulls all of it. To work on the build, the
styles or the front end without that, ask git for a checkout that skips it:

```bash
git clone --filter=blob:none --sparse https://github.com/KiarashS/directory.git
cd directory
git sparse-checkout set --no-cone '/*' '!/assets'
```

`--filter=blob:none` leaves file contents on the server until something asks for
them, and the sparse rule keeps `assets/` out of the working tree. The PDFs stay
in the repository and in its history either way — this changes only what your
own checkout pulls down, so it is safe and reversible.

Note that adding `assets/` to a `.gitignore` would *not* do this. Those files
are tracked, and `.gitignore` has no effect on tracked files: they would still
arrive with every clone. Its one real effect would be to make a newly added PDF
invisible to `git add`.

The build needs the PDFs, so in this mode it stops with `PDF not found`. Fetch
them when you need to run it:

```bash
git sparse-checkout disable      # brings assets/ back
```

GitHub Actions is unaffected — `actions/checkout` takes everything, so the
deployed site always has every file.

## Layout

| Path | What it is |
| --- | --- |
| `data/links.yml` | Every entry on the site. The file you edit. |
| `assets/` | The PDFs. Drop one in and name it from `links.yml`. |
| `assets/courses/<slug>/` | One folder per course, holding that course's material. |
| `scripts/build.py` | Renders the site, and validates it. |
| `scripts/test_build.py` | Tests for the PDF model. |
| `scripts/make_favicon.py` | Regenerates the icon set from `static/icon.svg`. |
| `static/css/directory.css`, `static/js/directory.js` | The front end. |
| `viewer/` | The pdf.js distribution. Updated by its own workflow. |
| `_site/` | Generated. Git-ignored, rebuilt from scratch every run. |
