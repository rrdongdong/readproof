import os
import pathlib
import unittest

from readproof import cli
from readproof import receipt as r
from readproof import states as s

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class PageTests(unittest.TestCase):
    def test_form_feed_splits_pages(self):
        text = load("full_paper.txt")
        pages = r.split_pages(text)
        self.assertEqual(len(pages), 7)
        self.assertIn("Abstract", pages[0])

    def test_single_page_text(self):
        self.assertEqual(len(r.split_pages("just one page")), 1)


class AssessmentTests(unittest.TestCase):
    def test_full_paper(self):
        verdict = r.assess(load("full_paper.txt"))
        self.assertEqual(verdict["verdict"], r.VERDICT_FULL)
        self.assertTrue(verdict["has_experiment_section"])
        self.assertTrue(verdict["has_references"])
        self.assertEqual(verdict["reasons"], [])

    def test_abstract_only(self):
        verdict = r.assess(load("abstract_only.txt"))
        self.assertEqual(verdict["verdict"], r.VERDICT_ABSTRACT_ONLY)
        self.assertFalse(verdict["has_experiment_section"])
        self.assertFalse(verdict["has_references"])

    def test_short_excerpt_is_partial_not_abstract(self):
        """Three pages of a real paper is a partial read, and should be named that."""
        verdict = r.assess(load("partial_paper.txt"))
        self.assertEqual(verdict["verdict"], r.VERDICT_PARTIAL)
        self.assertTrue(any("characters" in reason for reason in verdict["reasons"]))

    def test_thresholds_are_injectable(self):
        text = load("partial_paper.txt")
        lenient = r.assess(text, min_full_chars=100, min_full_pages=1)
        self.assertNotEqual(lenient["verdict"], r.VERDICT_ABSTRACT_ONLY)


class FingerprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt, cls.assessment = r.extract_receipt(load("full_paper.txt"))

    def test_all_four_present(self):
        self.assertEqual(s.missing_receipt_fields(self.receipt), [])

    def test_number_carries_value_and_page(self):
        value = self.receipt["number_with_locator"]
        self.assertIn("Table II", value)
        self.assertIn("41.2", value)
        self.assertIn("(p.5)", value)

    def test_hyperparameters_carry_values_and_section(self):
        value = self.receipt["hyperparameters"]
        self.assertIn("lr=1e-4", value)
        self.assertIn("batch=4", value)
        self.assertIn("p.5", value)

    def test_negative_quote_is_the_limitation_sentence(self):
        value = self.receipt["negative_quote"]
        self.assertIn("do not evaluate", value)
        self.assertIn("p.6", value)

    def test_body_detail_is_not_from_the_abstract(self):
        value = self.receipt["body_detail"]
        self.assertIn("p.4", value)
        self.assertNotIn("We present a dense reconstruction", value)

    def test_receipt_passes_the_state_machine(self):
        self.assertTrue(s.receipt_is_complete(self.receipt))

    def test_extra_records_provenance(self):
        extra = self.receipt["extra"]
        self.assertEqual(extra["verdict"], r.VERDICT_FULL)
        self.assertEqual(extra["pages"], 7)
        self.assertEqual(extra["extractor"], "readproof-text-v1")


class RefusalTests(unittest.TestCase):
    def test_abstract_only_is_refused(self):
        with self.assertRaises(r.ReceiptExtractionError) as ctx:
            r.extract_receipt(load("abstract_only.txt"))
        self.assertEqual(ctx.exception.exit_code, 6)
        self.assertEqual(len(ctx.exception.missing), 4)

    def test_partial_is_refused(self):
        with self.assertRaises(r.ReceiptExtractionError) as ctx:
            r.extract_receipt(load("partial_paper.txt"))
        self.assertEqual(ctx.exception.exit_code, 6)

    def test_require_full_false_still_fails_on_missing_fingerprints(self):
        """Turning off the verdict gate must not manufacture fingerprints."""
        with self.assertRaises(r.ReceiptExtractionError) as ctx:
            r.extract_receipt(load("abstract_only.txt"), require_full=False)
        self.assertIn("could not find", str(ctx.exception))

    def test_empty_text_is_refused(self):
        with self.assertRaises(r.ReceiptExtractionError):
            r.extract_receipt("")


class CliExtractTests(unittest.TestCase):
    def setUp(self):
        import shutil
        import tempfile

        self.dir = tempfile.mkdtemp(prefix="readproof-extract-")
        self.ledger = os.path.join(self.dir, "ledger.json")
        self._shutil = shutil

    def tearDown(self):
        self._shutil.rmtree(self.dir, ignore_errors=True)

    def run_cli(self, *args):
        return cli.main(["--ledger", self.ledger] + list(args))

    def test_extract_ok(self):
        self.assertEqual(self.run_cli("extract", str(FIXTURES / "full_paper.txt")), 0)

    def test_extract_refuses_abstract(self):
        self.assertEqual(self.run_cli("extract", str(FIXTURES / "abstract_only.txt")), 6)

    def test_receipt_from_text_then_read_full(self):
        self.assertEqual(self.run_cli("init"), 0)
        self.assertEqual(self.run_cli("add", "07", "--title", "A Full Paper"), 0)
        self.assertEqual(self.run_cli("advance", "07", s.FETCHED), 0)
        self.assertEqual(
            self.run_cli("receipt", "07", "--from-text", str(FIXTURES / "full_paper.txt")),
            0,
        )
        self.assertEqual(self.run_cli("advance", "07", s.READ_FULL), 0)

    def test_receipt_from_abstract_is_refused(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "An Abstract")
        self.run_cli("advance", "07", s.FETCHED)
        self.assertEqual(
            self.run_cli(
                "receipt", "07", "--from-text", str(FIXTURES / "abstract_only.txt")
            ),
            6,
        )
        # and the paper must not have moved
        self.assertEqual(self.run_cli("advance", "07", s.READ_FULL), 6)


if __name__ == "__main__":
    unittest.main()
