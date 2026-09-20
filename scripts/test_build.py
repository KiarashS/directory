#!/usr/bin/env python3
"""Tests for the PDF model in build.py.

    python3 -m unittest discover -s scripts -p 'test_*.py'

Each case builds a throwaway assets/ directory and points build.ASSETS at it,
so nothing here reads or writes the real repository content.
"""
from __future__ import annotations

import contextlib
import json
import math
import pathlib
import re
import struct
import sys
import tempfile
import unittest
import urllib.parse

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build  # noqa: E402

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF\n"

def _one_page_pdf() -> bytes:
    """A real one-page PDF. Hand-written bytes lack an xref and will not parse."""
    import io as _io
    import pypdf
    w = pypdf.PdfWriter()
    w.add_blank_page(width=612, height=792)
    buf = _io.BytesIO()
    w.write(buf)
    return buf.getvalue()


MINIMAL_PDF = _one_page_pdf()


class PdfCase(unittest.TestCase):
    """A temporary assets/ directory, with build.ASSETS pointed at it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.assets = root / "assets"
        self.assets.mkdir()
        self._saved = build.ASSETS
        build.ASSETS = self.assets
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: setattr(build, "ASSETS", self._saved))
        # ROOT is what pdf_path() makes the returned path relative to.
        self._saved_root = build.ROOT
        build.ROOT = root
        self.addCleanup(lambda: setattr(build, "ROOT", self._saved_root))

    def write(self, name: str, data: bytes = PDF_BYTES) -> None:
        path = self.assets / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def normalize(self, entries: list[dict], **kw) -> tuple[dict, dict]:
        doc = {"categories": [dict({"slug": "pdfs", "entries": entries}, **kw)]}
        return build.normalize(doc)


class TestSlug(unittest.TestCase):
    def test_derived_from_filename(self):
        self.assertEqual(build.pdf_slug("machine learning cheat sheet.pdf"),
                         "machine-learning-cheat-sheet")

    def test_collapses_runs_and_trims_ends(self):
        self.assertEqual(build.pdf_slug("  a --  b !!.pdf"), "a-b")

    def test_keeps_case_and_underscores(self):
        self.assertEqual(build.pdf_slug("Probability_Statistics.pdf"),
                         "Probability_Statistics")

    def test_extension_is_case_insensitive(self):
        self.assertEqual(build.pdf_slug("Notes.PDF"), "Notes")

    def test_empty_slug_is_refused(self):
        with self.assertRaises(SystemExit):
            build.pdf_slug("!!!.pdf")


class TestNormalization(PdfCase):
    def test_pdf_becomes_a_viewer_url(self):
        self.write("test.pdf")
        doc, routes = self.normalize([{"title": "T", "pdf": "test.pdf"}])
        entry = doc["categories"][0]["entries"][0]
        self.assertEqual(entry["url"], "./v/test/")
        self.assertEqual(routes["test"]["target"], "assets/test.pdf")

    def test_custom_slug_wins(self):
        self.write("test.pdf")
        doc, routes = self.normalize(
            [{"title": "T", "pdf": "test.pdf", "slug": "my-document"}])
        self.assertEqual(doc["categories"][0]["entries"][0]["url"], "./v/my-document/")
        self.assertIn("my-document", routes)

    def test_existing_mixed_case_slug_is_preserved(self):
        self.write("cheatsheet_probability_and_statistics.pdf")
        doc, _ = self.normalize([{
            "title": "Probability & Statistics",
            "pdf": "cheatsheet_probability_and_statistics.pdf",
            "slug": "Probability_Statistics"}])
        self.assertEqual(doc["categories"][0]["entries"][0]["url"],
                         "./v/Probability_Statistics/")

    def test_nested_link_pdf(self):
        self.write("a.pdf"), self.write("b.pdf")
        doc, routes = self.normalize([{
            "title": "A", "pdf": "a.pdf",
            "links": [{"text": "B", "pdf": "b.pdf", "slug": "bee"}]}])
        link = doc["categories"][0]["entries"][0]["links"][0]
        self.assertEqual(link["url"], "./v/bee/")
        self.assertEqual(routes["bee"]["target"], "assets/b.pdf")

    def course(self, slug, materials, links=None):
        return {"slug": slug, "title": slug.upper(), "links": links or [],
                "modules": [{"title": "M", "materials": materials}]}

    def test_course_material_resolves_under_its_own_folder(self):
        self.write("courses/intro-ml/lecture-01.pdf")
        doc, routes = self.normalize([], courses=[
            self.course("intro-ml",
                        [{"title": "Slides", "pdf": "lecture-01.pdf",
                          "type": "slides"}])])
        mat = doc["categories"][0]["courses"][0]["modules"][0]["materials"][0]
        self.assertEqual(mat["url"], "./v/courses/intro-ml/lecture-01/")
        self.assertEqual(routes["courses/intro-ml/lecture-01"]["target"],
                         "assets/courses/intro-ml/lecture-01.pdf")

    def test_two_courses_may_share_a_filename(self):
        self.write("courses/intro-ml/lecture-01.pdf")
        self.write("courses/algorithms/lecture-01.pdf")
        _, routes = self.normalize([], courses=[
            self.course("intro-ml", [{"title": "S", "pdf": "lecture-01.pdf"}]),
            self.course("algorithms", [{"title": "S", "pdf": "lecture-01.pdf"}]),
        ])
        self.assertEqual(routes["courses/intro-ml/lecture-01"]["target"],
                         "assets/courses/intro-ml/lecture-01.pdf")
        self.assertEqual(routes["courses/algorithms/lecture-01"]["target"],
                         "assets/courses/algorithms/lecture-01.pdf")

    def test_a_courses_own_links_resolve_there_too(self):
        self.write("courses/intro-ml/syllabus.pdf")
        doc, routes = self.normalize([], courses=[
            self.course("intro-ml", [],
                        links=[{"text": "Syllabus", "pdf": "syllabus.pdf"}])])
        link = doc["categories"][0]["courses"][0]["links"][0]
        self.assertEqual(link["url"], "./v/courses/intro-ml/syllabus/")

    def test_material_outside_its_course_folder_fails(self):
        self.write("lecture-01.pdf")          # in assets/, not the course folder
        with self.assertRaises(SystemExit) as cm:
            self.normalize([], courses=[
                self.course("intro-ml", [{"title": "S", "pdf": "lecture-01.pdf"}])])
        self.assertIn("assets/courses/intro-ml/lecture-01.pdf", str(cm.exception))

    def test_material_cannot_climb_out_of_assets(self):
        (self.assets.parent / "secret.pdf").write_bytes(PDF_BYTES)
        with self.assertRaises(SystemExit) as cm:
            self.normalize([], courses=[
                self.course("intro-ml",
                            [{"title": "S", "pdf": "../../../secret.pdf"}])])
        self.assertIn("escapes assets/", str(cm.exception))

    def test_nested_asset_directory_slug_mirrors_the_path(self):
        # The derived slug follows the file's path under assets/, which is what
        # keeps two courses' lecture-01.pdf apart without a hand-written slug.
        self.write("books/python/fluent.pdf")
        doc, routes = self.normalize(
            [{"title": "F", "pdf": "books/python/fluent.pdf"}])
        self.assertEqual(routes["books/python/fluent"]["target"],
                         "assets/books/python/fluent.pdf")
        self.assertEqual(doc["categories"][0]["entries"][0]["url"],
                         "./v/books/python/fluent/")

    def test_plain_url_is_left_alone(self):
        doc, routes = self.normalize([{"title": "X", "url": "https://example.com"}])
        self.assertEqual(doc["categories"][0]["entries"][0]["url"],
                         "https://example.com")
        self.assertEqual(routes, {})

    def test_legacy_viewer_url_still_works(self):
        doc, routes = self.normalize([{"title": "X", "url": "./v/action-verbs/"}])
        self.assertEqual(doc["categories"][0]["entries"][0]["url"], "./v/action-verbs/")
        self.assertEqual(routes, {})

    def test_embed_needs_a_slug(self):
        with self.assertRaises(SystemExit):
            self.normalize([{"title": "D", "embed": "https://example.com"}])


class TestValidationFailures(PdfCase):
    def test_missing_pdf(self):
        with self.assertRaises(SystemExit) as cm:
            self.normalize([{"title": "M", "pdf": "nope.pdf"}])
        self.assertIn("PDF not found", str(cm.exception))

    def test_wrong_extension(self):
        self.write("thing.zip")
        with self.assertRaises(SystemExit) as cm:
            self.normalize([{"title": "Z", "pdf": "thing.zip"}])
        self.assertIn(".pdf", str(cm.exception))

    def test_bad_signature(self):
        self.write("fake.pdf", b"<html>not a pdf</html>")
        with self.assertRaises(SystemExit) as cm:
            self.normalize([{"title": "F", "pdf": "fake.pdf"}])
        self.assertIn("%PDF-", str(cm.exception))

    def test_path_traversal_is_refused(self):
        # A real file, really outside assets/ — so this proves containment
        # rather than that a string happened to contain "..".
        (self.assets.parent / "secret.pdf").write_bytes(PDF_BYTES)
        with self.assertRaises(SystemExit) as cm:
            self.normalize([{"title": "S", "pdf": "../secret.pdf"}])
        self.assertIn("escapes assets/", str(cm.exception))

    def test_absolute_path_is_refused(self):
        with self.assertRaises(SystemExit):
            self.normalize([{"title": "S", "pdf": "/etc/passwd.pdf"}])

    def test_duplicate_slug(self):
        self.write("one.pdf"), self.write("two.pdf")
        with self.assertRaises(SystemExit) as cm:
            self.normalize([{"title": "Python Cheat Sheet", "pdf": "one.pdf",
                             "slug": "python"},
                            {"title": "Python Reference", "pdf": "two.pdf",
                             "slug": "python"}])
        message = str(cm.exception)
        self.assertIn("Duplicate PDF viewer slug: python", message)
        self.assertIn("Python Cheat Sheet", message)
        self.assertIn("Python Reference", message)

    def test_pdf_and_url_together(self):
        self.write("both.pdf")
        with self.assertRaises(SystemExit) as cm:
            self.normalize([{"title": "Example", "pdf": "both.pdf",
                             "url": "https://example.com"}])
        self.assertIn("cannot contain both", str(cm.exception))


class TestSlugValidation(PdfCase):
    """An explicit slug becomes a directory path, so it has to be checked."""

    def bad(self, slug):
        self.write("x.pdf")
        with self.assertRaises(SystemExit, msg=f"{slug!r} should be refused") as cm:
            self.normalize([{"title": "X", "pdf": "x.pdf", "slug": slug}])
        self.assertIn("slug", str(cm.exception))

    def test_parent_segment(self):        self.bad("../escape")
    def test_dot_segment(self):           self.bad("a/./b")
    def test_empty_segment(self):         self.bad("a//b")
    def test_leading_slash(self):         self.bad("/a")
    def test_trailing_slash(self):        self.bad("a/")
    def test_space(self):                 self.bad("my slug")

    def test_a_nested_slug_is_allowed(self):
        self.write("x.pdf")
        doc, routes = self.normalize(
            [{"title": "X", "pdf": "x.pdf", "slug": "courses/c/x"}])
        self.assertEqual(doc["categories"][0]["entries"][0]["url"], "./v/courses/c/x/")


class TestViewerDepth(unittest.TestCase):
    """A deeper page needs more '../' to reach the site root."""

    def test_depth_by_slug(self):
        self.assertEqual(build.viewer_depth("action-verbs"), 2)
        self.assertEqual(build.viewer_depth("courses/intro-ml/lecture-01"), 4)

    def test_flat_route_is_byte_for_byte_what_it_was(self):
        page = build.render_viewer("Action Verbs", "assets/action-verbs.pdf",
                                   "action-verbs")
        self.assertIn('src="../../viewer/web/viewer.html?file=', page)

    def test_nested_route_reaches_the_root(self):
        page = build.render_viewer("Slides", "assets/courses/c/l1.pdf",
                                   "courses/c/l1")
        self.assertIn('src="../../../../viewer/web/viewer.html?file=', page)
        target = urllib.parse.unquote(page.split("file=", 1)[1].split('"')[0])
        self.assertEqual(target, "../../../../assets/courses/c/l1.pdf")


class TestWeight(PdfCase):
    """What a card says about a PDF's length and size."""

    def test_human_size(self):
        self.assertEqual(build.human_size(39 * 1024), "39 KB")
        self.assertEqual(build.human_size(int(2.35 * 1048576)), "2.3 MB")
        self.assertEqual(build.human_size(39 * 1048576), "39 MB")   # no decimal when large

    def test_meta_reads_size_and_pages(self):
        self.write("doc.pdf", MINIMAL_PDF)
        build.pdf_meta.cache_clear()
        size, pages = build.pdf_meta("assets/doc.pdf")
        self.assertEqual(size, len(MINIMAL_PDF))
        self.assertEqual(pages, 1)

    def test_unreadable_pdf_falls_back_to_size(self):
        # A valid signature but nothing pypdf can parse: the build must still
        # produce a card, showing what it does know.
        self.write("broken.pdf", b"%PDF-1.4\nnot really a pdf\n")
        build.pdf_meta.cache_clear()
        size, pages = build.pdf_meta("assets/broken.pdf")
        self.assertEqual(size, 26)
        self.assertIsNone(pages)
        self.assertIn("25 KB" if size > 1024 else "1 KB",
                      build.weight_badge("assets/broken.pdf"))

    def test_encrypted_pdf_still_reports_its_pages(self):
        """Seven PDFs in assets/ are encrypted, and pypdf needs `cryptography`
        to open them. Without it they silently lose their page count — which
        happened in CI while passing locally, because the package was already
        installed here. This fails loudly instead."""
        import io as _io
        import pypdf
        w = pypdf.PdfWriter()
        w.add_blank_page(width=612, height=792)
        w.encrypt("", algorithm="AES-128")
        buf = _io.BytesIO()
        w.write(buf)
        self.write("locked.pdf", buf.getvalue())
        build.pdf_meta.cache_clear()
        _, pages = build.pdf_meta("assets/locked.pdf")
        self.assertEqual(pages, 1,
                         "encrypted PDF lost its page count — is cryptography installed?")

    def test_badge_wording(self):
        self.write("doc.pdf", MINIMAL_PDF)
        build.pdf_meta.cache_clear()
        self.assertIn("1 page ·", build.weight_badge("assets/doc.pdf"))


class TestSitemap(unittest.TestCase):
    def test_lists_content_pages_and_skips_readers(self):
        doc = {"site": {"url": "https://example.com/d/"},
               "categories": [{"slug": "pdfs", "name": "PDFs", "entries": []}]}
        pages = {"index.html": "", "pdfs/index.html": "",
                 "v/a/index.html": "", "v/courses/c/l1/index.html": ""}
        base = doc["site"]["url"]
        urls = sorted(p[: -len("index.html")] for p in pages
                      if p.endswith("index.html") and not p.startswith("v/"))
        self.assertEqual(urls, ["", "pdfs/"])
        self.assertNotIn("v/", " ".join(urls))

    def test_real_build_sitemap_is_wellformed(self):
        import xml.dom.minidom
        doc, _, pages = build.load()
        dom = xml.dom.minidom.parseString(pages["sitemap.xml"])
        locs = [n.firstChild.data for n in dom.getElementsByTagName("loc")]
        # One per enabled section, plus the front page. Derived rather than
        # hardcoded, so switching a section off does not fail this test for
        # doing exactly what it is meant to do.
        self.assertEqual(len(locs), len(doc["categories"]) + 1)
        self.assertTrue(all(u.startswith("https://") for u in locs))
        self.assertFalse(any("/v/" in u for u in locs))
        self.assertIn("Sitemap:", pages["robots.txt"])


class TestTagVocabulary(unittest.TestCase):
    """Word boundaries, because an unanchored 'ui' tags 'Building' as design."""

    def setUp(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import suggest_tags
        self.st = suggest_tags

    def tags(self, title, links=()):
        return self.st.tags_for({"title": title,
                                 "links": [{"text": t} for t in links]})

    def test_building_is_not_design(self):
        self.assertEqual(self.tags("Building Grammar Skills For the TOEFL"),
                         ["english", "toefl"])

    def test_guide_is_not_design(self):
        # "Guide" must not mean design; and the underscores must not hide "GRE",
        # since \b sees no boundary inside GRE_Equation.
        self.assertEqual(self.tags("GRE_Equation_Guide_TTP"), ["gre"])

    def test_real_design_still_matches(self):
        self.assertIn("design", self.tags("Laws of UX"))

    def test_sublink_text_counts(self):
        self.assertIn("python", self.tags("Assorted notes", ["Pandas tricks"]))

    def test_no_match_is_empty(self):
        self.assertEqual(self.tags("Miscellaneous"), [])


class TestCategorySwitch(PdfCase):
    """`enabled: false` removes a section rather than hiding it."""

    def doc(self, **flags):
        return {"site": {"url": "https://example.com/d/", "title": "T",
                         "heading": "H", "heading_accent": "A", "tagline": "t",
                         "author": "me", "author_url": "https://example.com",
                         "suggest_form": "https://example.com/f"},
                "categories": [dict({"slug": s, "name": s.title(), "entries": []},
                                    **({"enabled": flags[s]} if s in flags else {}))
                               for s in ("pdfs", "links", "tools", "datasets",
                                         "talks", "courses")]}

    def enabled(self, doc):
        return [c["slug"] for c in doc["categories"] if c.get("enabled", True)]

    def test_absent_field_means_on(self):
        self.assertEqual(len(self.enabled(self.doc())), 6)

    def test_false_removes_the_section(self):
        self.assertNotIn("courses", self.enabled(self.doc(courses=False)))

    def test_true_is_the_same_as_absent(self):
        self.assertEqual(self.enabled(self.doc(courses=True)), self.enabled(self.doc()))

    def test_a_disabled_section_is_never_validated(self):
        """Its PDFs are not checked, so it can be drafted before it is ready."""
        doc = self.doc(courses=False)
        doc["categories"][-1]["entries"] = [
            {"title": "Not uploaded yet", "pdf": "does-not-exist.pdf"}]
        kept = [c for c in doc["categories"] if c.get("enabled", True)]
        doc["categories"] = kept
        build.normalize(doc)          # would raise "PDF not found" if it looked

    def test_a_missing_pdf_in_an_enabled_section_still_fails(self):
        doc = self.doc()
        doc["categories"][0]["entries"] = [
            {"title": "Missing", "pdf": "does-not-exist.pdf"}]
        with self.assertRaises(SystemExit):
            build.normalize(doc)


class TestServiceWorkerShell(unittest.TestCase):
    def test_shell_names_the_enabled_sections(self):
        _, _, pages = build.load()
        sw = pages["sw.js"]
        self.assertNotIn("__SHELL_PAGES__", sw)
        self.assertNotIn("__SHELL_HASH__", sw)
        shell = re.search(r"var SHELL = \[(.*?)\];", sw, re.S).group(1)
        listed = set(re.findall(r"'\./([a-z]+)/'", shell))
        _, _, _ = None, None, None
        doc = yaml.safe_load(build.LINKS.read_text(encoding="utf-8"))
        on = {c["slug"] for c in doc["categories"] if c.get("enabled", True)}
        off = {c["slug"] for c in doc["categories"] if not c.get("enabled", True)}
        self.assertTrue(on <= listed, f"{on - listed} missing from the shell")
        self.assertFalse(listed & off, f"{listed & off} still precached")

    def test_cache_name_follows_the_shell(self):
        _, _, pages = build.load()
        self.assertRegex(pages["sw.js"], r"var CACHE = 'directory-v4-[0-9a-f]{8}'")


class TestViewerPage(PdfCase):
    def test_end_to_end(self):
        """data -> normalization -> page -> the PDF.js URL -> the file."""
        self.write("ai-cheat-sheet.pdf")
        doc, routes = self.normalize([{"title": "AI Cheat Sheet",
                                       "pdf": "ai-cheat-sheet.pdf"}])
        page = build.render_viewer(routes["ai-cheat-sheet"]["title"],
                                   routes["ai-cheat-sheet"]["target"],
                                   "ai-cheat-sheet")
        self.assertIn("<title>AI Cheat Sheet</title>", page)

        import re
        src = re.search(r'src="([^"]+viewer\.html[^"]*)"', page).group(1)
        target = urllib.parse.unquote(src.split("file=", 1)[1])
        self.assertEqual(target, "../../assets/ai-cheat-sheet.pdf")
        # Resolve it the way a browser would, from v/<slug>/.
        landed = (self.assets.parent / "v" / "ai-cheat-sheet" / target).resolve()
        self.assertTrue(landed.is_file())
        self.assertEqual(landed.read_bytes()[:5], b"%PDF-")

    def test_special_characters_are_encoded(self):
        self.write("Toefl Expressions&Brainstorm (Speak&Write).pdf")
        _, routes = self.normalize([{
            "title": "TOEFL & Brainstorm",
            "pdf": "Toefl Expressions&Brainstorm (Speak&Write).pdf",
            "slug": "toefl"}])
        page = build.render_viewer("TOEFL & Brainstorm", routes["toefl"]["target"],
                                   "toefl")
        self.assertNotIn(" ", page.split('src="')[1].split('"')[0])
        self.assertIn("&amp;", page)          # the title is HTML-escaped
        self.assertIn("%26", page)            # the filename is URL-encoded

    def test_embed_page_points_at_the_external_site(self):
        page = build.render_viewer("Cambridge", "https://dictionary.cambridge.org/x",
                                   "cambridge-dictionary", embed=True)
        self.assertIn('src="https://dictionary.cambridge.org/x"', page)
        self.assertNotIn("viewer.html", page)


class TestManifestIcons(unittest.TestCase):
    """--validate refuses a manifest that names an icon the build won't ship."""

    @contextlib.contextmanager
    def manifest(self, icons):
        """Point build.ROOT at a throwaway tree holding just this manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "static").mkdir()
            (root / "static" / "icon.svg").write_text("<svg/>")
            (root / "android-chrome-512x512.png").write_bytes(b"\x89PNG")
            (root / "stray.png").write_bytes(b"\x89PNG")
            (root / "manifest.webmanifest").write_text(json.dumps({"icons": icons}))
            real, build.ROOT = build.ROOT, root
            try:
                yield
            finally:
                build.ROOT = real

    ANY = {"src": "android-chrome-512x512.png", "purpose": "any"}
    MASK = {"src": "android-chrome-512x512.png", "purpose": "maskable"}

    def test_the_real_manifest_passes(self):
        self.assertEqual(build.validate_manifest_icons(), [])

    def test_a_missing_file_fails(self):
        with self.manifest([self.MASK, {"src": "not-there.png"}]):
            self.assertIn("does not exist",
                          " ".join(build.validate_manifest_icons()))

    def test_a_file_outside_runtime_fails(self):
        """The file is there, but nothing copies it into _site."""
        with self.manifest([self.MASK, {"src": "stray.png"}]):
            self.assertIn("not in RUNTIME",
                          " ".join(build.validate_manifest_icons()))

    def test_a_root_absolute_src_fails(self):
        """The site lives on a subpath, so /icon.png is a 404."""
        with self.manifest([self.MASK, {"src": "/android-chrome-512x512.png"}]):
            self.assertIn("not a relative", " ".join(build.validate_manifest_icons()))

    def test_a_file_inside_a_runtime_directory_passes(self):
        with self.manifest([self.MASK, {"src": "static/icon.svg"}]):
            self.assertEqual(build.validate_manifest_icons(), [])

    def test_no_maskable_icon_fails(self):
        with self.manifest([self.ANY]):
            self.assertIn("no maskable icon",
                          " ".join(build.validate_manifest_icons()))


class TestMaskableArtwork(unittest.TestCase):
    """The maskable icon has to survive the launcher's crop.

    Android masks an adaptive icon to its own shape and guarantees only the
    centre 72 of 108dp -- 66.7%, not the 80% usually quoted. These read the
    generator's source rather than importing it, so they run without cairosvg.
    """

    SOURCE = (pathlib.Path(__file__).resolve().parent / "make_favicon.py"
              ).read_text(encoding="utf-8")

    # The mark, traced from its path data: the outer folder spans x 112..432
    # and y 124..388, and every corner is rounded with r=30, so no ink reaches
    # a bare corner of that box.
    BOX = (112, 124, 432, 388)
    CORNER_R = 30
    SAFE_FRACTION = 72 / 108

    def scale(self):
        return float(re.search(r"^MASKABLE_SCALE = ([\d.]+)",
                               self.SOURCE, re.M).group(1))

    def test_the_mark_fits_the_safe_circle(self):
        x0, y0, x1, y1 = self.BOX
        # Furthest painted point: the centre of a corner's arc, plus its radius.
        dx = (x1 - x0) / 2 - self.CORNER_R
        dy = (y1 - y0) / 2 - self.CORNER_R
        reach = math.hypot(dx, dy) + self.CORNER_R
        safe = 512 * self.SAFE_FRACTION / 2
        self.assertLessEqual(reach * self.scale(), safe,
                             "the mark would be cropped by a circular mask")

    def test_it_reads_at_the_same_size_as_the_ordinary_icon(self):
        """Fitting is the floor; looking right is the point.

        The launcher does not just crop to the safe zone, it magnifies it to
        fill the tile, so artwork drawn here appears 108/72 larger than the
        same artwork in an ordinary icon. The scale has to cancel that.
        """
        x0, _, x1, _ = self.BOX
        plain = (x1 - x0) / 512                     # of the whole canvas
        viewport = 512 * self.SAFE_FRACTION
        masked = (x1 - x0) * self.scale() / viewport   # of what the phone shows
        self.assertAlmostEqual(masked, plain, delta=0.005,
                               msg="the maskable mark is a different apparent "
                                   "size from the mark everywhere else")

    def test_the_ordinary_icon_would_not_have_fitted(self):
        """Which is why this is a second image and not a relabelling."""
        x0, y0, x1, y1 = self.BOX
        # Unscaled and drawn where it is, the mark's box is centred at x=272.
        reach = math.hypot(max(abs(x0 - 256), abs(x1 - 256)) - self.CORNER_R,
                           max(abs(y0 - 256), abs(y1 - 256)) - self.CORNER_R)
        self.assertGreater(reach + self.CORNER_R, 512 * self.SAFE_FRACTION / 2)

    def test_the_mark_is_recentred(self):
        """Its box is centred at x=272, so it is moved before it is scaled."""
        x0, _, x1, _ = self.BOX
        self.assertIn(f"translate(-{(x0 + x1) // 2} -256)", self.SOURCE,
                      "the maskable mark is not re-centred")

    def test_the_background_bleeds_to_the_edge(self):
        """No baked rx: the launcher supplies the shape."""
        rect = re.search(r'<rect width="512" height="512"[^>]*>',
                         self.SOURCE.split("MASKABLE = ")[1]).group(0)
        self.assertNotIn("rx", rect)

    def test_both_sizes_are_generated_at_the_size_they_claim(self):
        for size in (192, 512):
            png = build.ROOT / f"maskable-{size}x{size}.png"
            self.assertTrue(png.is_file(), f"{png.name} is missing")
            head = png.read_bytes()[:24]
            self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", head[16:24])
            self.assertEqual((width, height), (size, size))


class TestGeneratedManifest(unittest.TestCase):
    """The manifest ships with hashed icon URLs, and one hash everywhere.

    An installed Android app takes its icon from the manifest it was installed
    with, and refreshes both lazily. A manifest answered from a cache names the
    icons that were cached alongside it, so a corrected icon never lands.
    """

    @classmethod
    def setUpClass(cls):
        _, _, cls.pages = build.load()
        cls.manifest = json.loads(cls.pages["manifest.webmanifest"])

    def test_every_icon_url_carries_a_content_hash(self):
        for icon in self.manifest["icons"]:
            self.assertRegex(icon["src"], r"\?v=[0-9a-f]{8}$")

    def test_every_icon_still_resolves_once_the_query_is_stripped(self):
        for icon in self.manifest["icons"]:
            name = icon["src"].split("?")[0]
            self.assertTrue((build.ROOT / name).is_file(), f"{name} is missing")

    def test_a_changed_icon_changes_its_url(self):
        one = build.render_manifest()
        self.assertEqual(one, build.render_manifest())      # same bytes, same URL
        icon = build.ROOT / "maskable-512x512.png"
        keep = icon.read_bytes()
        try:
            icon.write_bytes(keep + b"\0")
            self.assertNotEqual(build.render_manifest(), one)
        finally:
            icon.write_bytes(keep)

    def test_the_page_and_the_service_worker_agree_on_the_url(self):
        url = build.manifest_url(0)
        self.assertIn(f'<link rel="manifest" href="{url}">', self.pages["index.html"])
        self.assertIn(f"'{url}'", self.pages["sw.js"])

    def test_the_service_worker_does_not_precache_the_bare_path(self):
        """An entry nothing requests only shadows the one that is asked for."""
        shell = re.search(r"var SHELL = \[(.*?)\];", self.pages["sw.js"],
                          re.S).group(1)
        self.assertNotIn("'./manifest.webmanifest'", shell)
        self.assertIn("manifest.webmanifest?v=", shell)

    def test_the_cache_name_follows_the_manifest(self):
        before = re.search(r"var CACHE = '([^']+)'", self.pages["sw.js"]).group(1)
        icon = build.ROOT / "maskable-512x512.png"
        keep = icon.read_bytes()
        try:
            icon.write_bytes(keep + b"\0")
            _, _, pages = build.load()
            after = re.search(r"var CACHE = '([^']+)'", pages["sw.js"]).group(1)
        finally:
            icon.write_bytes(keep)
        self.assertNotEqual(before, after,
                            "a new icon has to roll the cache, or the old "
                            "manifest survives in it")

    def test_the_manifest_is_not_also_copied_over_the_generated_one(self):
        self.assertNotIn("manifest.webmanifest", build.RUNTIME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
