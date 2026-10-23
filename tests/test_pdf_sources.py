import hashlib
import os
import sys
import pathlib
import shutil
import tempfile
import unittest

from readproof import cli
from readproof import pdf
from readproof import sources
from readproof import states as s

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
FAKE_EXTRACTOR = FIXTURES / "fake_extractor.py"


class PdfInspectionTests(unittest.TestCase):
    def test_valid_pdf_passes(self):
        report = pdf.inspect_file(str(FIXTURES / "valid.pdf"))
        self.assertTrue(report["ok"], report["problems"])
        self.assertTrue(report["has_magic"])
        self.assertTrue(report["has_eof"])
        self.assertGreaterEqual(report["page_objects"], 1)

    def test_truncated_pdf_is_refused(self):
        report = pdf.inspect_file(str(FIXTURES / "truncated.pdf"))
        self.assertFalse(report["ok"])
        self.assertTrue(any("EOF" in problem for problem in report["problems"]))
        with self.assertRaises(pdf.PdfError) as ctx:
            pdf.require_valid(str(FIXTURES / "truncated.pdf"))
        self.assertEqual(ctx.exception.exit_code, 8)

    def test_non_pdf_is_refused(self):
        with self.assertRaises(pdf.PdfError):
            pdf.require_valid(str(FIXTURES / "not_a_pdf.pdf"))

    def test_sha256_is_stable_and_distinguishing(self):
        one = pdf.inspect_file(str(FIXTURES / "valid.pdf"))["sha256"]
        two = pdf.inspect_file(str(FIXTURES / "valid.pdf"))["sha256"]
        other = pdf.inspect_file(str(FIXTURES / "truncated.pdf"))["sha256"]
        self.assertEqual(one, two)
        self.assertNotEqual(one, other)
        self.assertEqual(
            one, hashlib.sha256((FIXTURES / "valid.pdf").read_bytes()).hexdigest()
        )

    def test_pages_tree_is_not_counted_as_a_page(self):
        data = (FIXTURES / "valid.pdf").read_bytes()
        report = pdf.inspect_bytes(data)
        self.assertEqual(report["page_objects"], 1)

    def test_size_floor(self):
        report = pdf.inspect_bytes(b"%PDF-1.4\n%%EOF\n")
        self.assertFalse(report["ok"])
        self.assertTrue(any("bytes" in problem for problem in report["problems"]))

    def test_non_http_url_is_refused_before_network(self):
        with self.assertRaises(pdf.PdfError):
            pdf.download("file:///etc/passwd", "/tmp/should-not-exist.pdf")


class IdentityTests(unittest.TestCase):
    def test_matching_title(self):
        text = (FIXTURES / "full_paper.txt").read_text(encoding="utf-8")
        ok, detail = pdf.identity_matches(
            "Dense Reconstruction of Degraded Scenes", text
        )
        self.assertTrue(ok, detail)

    def test_unrelated_title(self):
        text = (FIXTURES / "full_paper.txt").read_text(encoding="utf-8")
        ok, detail = pdf.identity_matches(
            "A Completely Different Paper About Something Else Entirely", text
        )
        self.assertFalse(ok)
        self.assertIn("title words", detail)

    def test_empty_inputs_do_not_crash(self):
        self.assertFalse(pdf.identity_matches("", "text")[0])
        self.assertFalse(pdf.identity_matches("title", "")[0])


class ExtractorTests(unittest.TestCase):
    def set_command(self, value):
        self._previous = os.environ.get(sources.ENV_OVERRIDE)
        os.environ[sources.ENV_OVERRIDE] = value

    def tearDown(self):
        if getattr(self, "_previous", None) is None:
            os.environ.pop(sources.ENV_OVERRIDE, None)
        else:
            os.environ[sources.ENV_OVERRIDE] = self._previous

    def test_configured_extractor_is_used(self):
        self.set_command("%s %s {} " % (sys.executable, FAKE_EXTRACTOR))
        found = sources.available()
        self.assertIsNotNone(found)
        self.assertEqual(found[0], "python3")

    def test_missing_configured_extractor_raises(self):
        self.set_command("/nonexistent/definitely-not-here {}")
        with self.assertRaises(sources.ExtractorUnavailable) as ctx:
            sources.available()
        self.assertEqual(ctx.exception.exit_code, 7)

    def test_extract_text_returns_pages_and_meta(self):
        self.set_command("%s %s {}" % (sys.executable, FAKE_EXTRACTOR))
        text, meta = sources.extract_text(str(FIXTURES / "valid.pdf"))
        self.assertIn("Table II", text)
        self.assertEqual(meta["pages"], 7)
        self.assertGreater(meta["chars"], 10000)

    def test_placeholder_is_optional(self):
        """A command without {pdf} gets the path appended, so plain CLIs work."""
        self.set_command("%s %s" % (sys.executable, FAKE_EXTRACTOR))
        text, _ = sources.extract_text(str(FIXTURES / "valid.pdf"))
        self.assertIn("Abstract", text)

    def test_failing_extractor_reports_failure(self):
        self.set_command("%s -c 'import sys; sys.exit(3)'" % sys.executable)
        with self.assertRaises(sources.ExtractionFailed):
            sources.extract_text(str(FIXTURES / "valid.pdf"))

    def test_silent_extractor_reports_no_text_layer(self):
        self.set_command("%s -c 'print()'" % sys.executable)
        with self.assertRaises(sources.ExtractionFailed) as ctx:
            sources.extract_text(str(FIXTURES / "valid.pdf"))
        self.assertIn("no text layer", str(ctx.exception))


class IntakeCliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-intake-")
        self.ledger = os.path.join(self.dir, "ledger.json")
        self._previous = os.environ.get(sources.ENV_OVERRIDE)
        os.environ[sources.ENV_OVERRIDE] = "%s %s {}".strip() % (sys.executable, FAKE_EXTRACTOR)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        if self._previous is None:
            os.environ.pop(sources.ENV_OVERRIDE, None)
        else:
            os.environ[sources.ENV_OVERRIDE] = self._previous

    def run_cli(self, *args):
        return cli.main(["--ledger", self.ledger] + list(args))

    def test_intake_reaches_fetched_and_records_provenance(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "Dense Reconstruction of Degraded Scenes")
        self.assertEqual(self.run_cli("intake", "07", str(FIXTURES / "valid.pdf")), 0)
        from readproof.store import Ledger

        paper = Ledger.open(self.ledger).find("07")
        self.assertEqual(paper["state"], s.FETCHED)
        self.assertEqual(paper["source"], s.MANUAL_UPLOAD)
        self.assertTrue(paper["intake"]["identity"]["ok"])
        self.assertEqual(len(paper["intake"]["sha256"]), 64)

    def test_intake_never_passes_fetched(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "Dense Reconstruction of Degraded Scenes")
        self.run_cli("intake", "07", str(FIXTURES / "valid.pdf"))
        # READ_FULL still needs a receipt, even though the PDF was accepted
        self.assertEqual(self.run_cli("advance", "07", s.READ_FULL), 6)

    def test_truncated_intake_is_refused(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "Dense Reconstruction of Degraded Scenes")
        self.assertEqual(self.run_cli("intake", "07", str(FIXTURES / "truncated.pdf")), 8)
        from readproof.store import Ledger

        self.assertEqual(Ledger.open(self.ledger).find("07")["state"], s.UNREAD)

    def test_identity_mismatch_is_refused_then_allowed(self):
        self.run_cli("init")
        self.run_cli("add", "09", "--title", "Something Else Entirely Different Here")
        self.assertEqual(self.run_cli("intake", "09", str(FIXTURES / "valid.pdf")), 9)
        self.assertEqual(
            self.run_cli(
                "intake", "09", str(FIXTURES / "valid.pdf"), "--accept-mismatch"
            ),
            0,
        )

    def test_unknown_paper_needs_title(self):
        self.run_cli("init")
        self.assertEqual(self.run_cli("intake", "99", str(FIXTURES / "valid.pdf")), 1)

    def test_receipt_from_pdf_then_read_full(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "Dense Reconstruction of Degraded Scenes")
        self.run_cli("intake", "07", str(FIXTURES / "valid.pdf"))
        self.assertEqual(
            self.run_cli("receipt", "07", "--from-pdf", str(FIXTURES / "valid.pdf")), 0
        )
        self.assertEqual(self.run_cli("advance", "07", s.READ_FULL), 0)


class NoExtractorTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-noext-")
        self.ledger = os.path.join(self.dir, "ledger.json")
        self._previous = os.environ.pop(sources.ENV_OVERRIDE, None)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        if self._previous is not None:
            os.environ[sources.ENV_OVERRIDE] = self._previous
        else:
            os.environ.pop(sources.ENV_OVERRIDE, None)

    def test_pdf_without_extractor_exits_7(self):
        if sources.available() is not None:
            self.skipTest("an extractor is installed here; covered by CI matrix")
        code = cli.main(["--ledger", self.ledger, "extract", str(FIXTURES / "valid.pdf")])
        self.assertEqual(code, 7)


if __name__ == "__main__":
    unittest.main()
