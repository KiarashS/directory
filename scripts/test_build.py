#!/usr/bin/env python3
"""Tests for the PDF model in build.py.

    python3 -m unittest discover -s scripts -p 'test_*.py'

Each case builds a throwaway assets/ directory and points build.ASSETS at it,
so nothing here reads or writes the real repository content.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build  # noqa: E402

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF\n"


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

    def test_course_material_pdf(self):
        self.write("lecture-01.pdf")
        doc, routes = self.normalize([], courses=[{
            "slug": "c", "title": "C",
            "modules": [{"title": "M", "materials": [
                {"title": "Slides", "pdf": "lecture-01.pdf", "type": "slides"}]}]}])
        mat = doc["categories"][0]["courses"][0]["modules"][0]["materials"][0]
        self.assertEqual(mat["url"], "./v/lecture-01/")
        self.assertEqual(routes["lecture-01"]["target"], "assets/lecture-01.pdf")

    def test_nested_asset_directory(self):
        self.write("books/python/fluent.pdf")
        _, routes = self.normalize(
            [{"title": "F", "pdf": "books/python/fluent.pdf"}])
        self.assertEqual(routes["fluent"]["target"], "assets/books/python/fluent.pdf")

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


class TestViewerPage(PdfCase):
    def test_end_to_end(self):
        """data -> normalization -> page -> the PDF.js URL -> the file."""
        self.write("ai-cheat-sheet.pdf")
        doc, routes = self.normalize([{"title": "AI Cheat Sheet",
                                       "pdf": "ai-cheat-sheet.pdf"}])
        page = build.render_viewer(routes["ai-cheat-sheet"]["title"],
                                   routes["ai-cheat-sheet"]["target"])
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
        page = build.render_viewer("TOEFL & Brainstorm", routes["toefl"]["target"])
        self.assertNotIn(" ", page.split('src="')[1].split('"')[0])
        self.assertIn("&amp;", page)          # the title is HTML-escaped
        self.assertIn("%26", page)            # the filename is URL-encoded

    def test_embed_page_points_at_the_external_site(self):
        page = build.render_viewer("Cambridge", "https://dictionary.cambridge.org/x",
                                   embed=True)
        self.assertIn('src="https://dictionary.cambridge.org/x"', page)
        self.assertNotIn("viewer.html", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
