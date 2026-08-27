# My Directory

The site behind [directory.kiarashs.ir](https://directory.kiarashs.ir/): a hand-kept
collection of PDFs, reading links, web tools and open datasets.

## Adding or changing a link

Everything on the site comes from [`data/links.yml`](data/links.yml). Edit that file —
in the GitHub web editor is fine — and the site rebuilds and republishes itself.
Nothing else needs touching; `index.html` is generated and should never be edited
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

### Descriptions

Leave `description` out and the build fetches one from the page itself: its
`og:description`, then its `<meta name="description">`, then its `<title>`. A
`github.com/owner/repo` link uses the repository's own description instead.
Results are cached in `data/descriptions.json` so the site builds without
hitting the network.

Write a `description` in and it is pinned — the fetcher skips that URL and never
overwrites what you wrote:

```yaml
- title: Simple Icons
  url: https://simpleicons.org/
  description: 3052 free SVG icons for popular brands.
```

A description that got fetched badly is fixed the same way: write the right one
into `links.yml`.

## How the build works

`.github/workflows/build.yml` runs on any push that touches `data/links.yml`,
`scripts/`, or `static/`:

1. `scripts/fetch_descriptions.py` fills in descriptions it does not already have.
2. `scripts/build.py` renders `index.html` from the YAML and the cache.
3. A check asserts every URL in the YAML appears in the rendered page.
4. The regenerated `index.html` and cache are committed, and the site deploys to Pages.

Because the workflow only triggers on its *inputs*, its own commit does not set
off another run. A weekly job re-tries links that previously failed.

To run it locally:

```bash
pip install pyyaml requests beautifulsoup4
python3 scripts/fetch_descriptions.py   # optional; network
python3 scripts/build.py                # writes index.html
python3 scripts/build.py --check        # exits 1 if index.html is stale
python3 -m http.server                  # then open http://localhost:8000
```

## Layout

| Path | What it is |
| --- | --- |
| `data/links.yml` | Every entry on the site. The only file you edit. |
| `data/descriptions.json` | Fetched descriptions, cached. Generated. |
| `scripts/build.py` | Renders `index.html`. |
| `scripts/fetch_descriptions.py` | Fills the description cache. |
| `static/css/directory.css`, `static/js/directory.js` | The front end. |
| `index.html` | Generated output. Do not edit. |
| `assets/`, `v/`, `viewer/` | The PDFs and the pdf.js viewer that displays them. |
