import json
import os
import shutil
import tempfile
import unittest

from readproof import cli
from readproof import states as s
from readproof.store import (
    DuplicatePaper,
    IncompleteReceipt,
    Ledger,
    normalize_identifier,
    normalize_title,
)

RECEIPT = {
    "number_with_locator": "Table II: 41.2 / 38.7 / 35.1 dB (p.5)",
    "hyperparameters": "lr=2e-4, iters=20k (sec IV-A, p.4)",
    "negative_quote": "we do not report results under motion blur (sec V-D, p.7)",
    "body_detail": "cosine schedule appears only in a p.3 footnote",
}


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-test-")
        self.path = os.path.join(self.dir, "ledger.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class NormalizationTests(unittest.TestCase):
    def test_title_folding_ignores_case_and_punctuation(self):
        self.assertEqual(
            normalize_title("A Paper: Title!"), normalize_title("a  paper title")
        )

    def test_title_folding_keeps_cjk(self):
        self.assertNotEqual(normalize_title("水下重建"), normalize_title("多机建图"))

    def test_identifier_folding_handles_arxiv_forms(self):
        self.assertEqual(
            normalize_identifier("arXiv:2601.00001"), normalize_identifier("2601.00001v2")
        )


class DedupTests(LedgerTestCase):
    def test_duplicate_id_rejected(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "A Paper Title")
        with self.assertRaises(DuplicatePaper) as ctx:
            ledger.add("07", "Something Else")
        self.assertEqual(ctx.exception.exit_code, 2)

    def test_duplicate_title_rejected_across_ids(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "A Paper: Title")
        with self.assertRaises(DuplicatePaper):
            ledger.add("08", "a paper title")

    def test_duplicate_arxiv_rejected(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "First", arxiv="2601.00001")
        with self.assertRaises(DuplicatePaper):
            ledger.add("08", "Second", arxiv="arXiv:2601.00001v2")

    def test_duplicate_doi_rejected(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "First", doi="10.1109/LRA.2099.1")
        with self.assertRaises(DuplicatePaper):
            ledger.add("08", "Second", doi="10.1109/lra.2099.1")


class TransitionGateTests(LedgerTestCase):
    def test_advance_rejects_illegal_jump(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "T")
        ledger.advance("07", s.FETCHED)
        with self.assertRaises(s.IllegalTransition):
            ledger.advance("07", s.VERIFIED)

    def test_read_full_blocked_without_receipt(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "T")
        ledger.advance("07", s.FETCHED)
        with self.assertRaises(IncompleteReceipt) as ctx:
            ledger.advance("07", s.READ_FULL)
        self.assertEqual(ctx.exception.exit_code, 6)

    def test_read_full_allowed_with_receipt(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "T")
        ledger.advance("07", s.FETCHED)
        ledger.set_receipt("07", RECEIPT)
        paper = ledger.advance("07", s.READ_FULL)
        self.assertEqual(paper["state"], s.READ_FULL)

    def test_incomplete_receipt_is_not_stored(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "T")
        with self.assertRaises(IncompleteReceipt):
            ledger.set_receipt("07", {"number_with_locator": "x"})
        self.assertIsNone(ledger.find("07")["receipt"])

    def test_manual_upload_cannot_jump_states(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "T")
        with self.assertRaises(s.IllegalTransition) as ctx:
            ledger.advance("07", s.READ_FULL, via=s.MANUAL_UPLOAD)
        self.assertEqual(ctx.exception.exit_code, 5)

    def test_manual_upload_marks_source(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "T")
        paper = ledger.advance("07", s.FETCHED, via=s.MANUAL_UPLOAD)
        self.assertEqual(paper["source"], s.MANUAL_UPLOAD)


class PersistenceTests(LedgerTestCase):
    def test_round_trip(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "T", venue="CVPR 2026")
        ledger.advance("07", s.FETCHED)
        ledger.set_receipt("07", RECEIPT)
        ledger.advance("07", s.READ_FULL)
        ledger.save()

        again = Ledger.open(self.path)
        paper = again.find("07")
        self.assertEqual(paper["state"], s.READ_FULL)
        self.assertEqual(paper["venue"], "CVPR 2026")
        self.assertEqual(paper["receipt"]["negative_quote"], RECEIPT["negative_quote"])
        self.assertEqual(len(paper["history"]), 3)

    def test_missing_ledger_is_an_error_unless_creating(self):
        with self.assertRaises(Exception):
            Ledger.open(self.path)

    def test_counts(self):
        ledger = Ledger.open(self.path, create=True)
        ledger.add("07", "A")
        ledger.add("08", "B")
        ledger.advance("07", s.FETCHED)
        self.assertEqual(ledger.counts()[s.FETCHED], 1)
        self.assertEqual(ledger.counts()[s.UNREAD], 1)


class CliTests(LedgerTestCase):
    def run_cli(self, *args):
        return cli.main(["--ledger", self.path] + list(args))

    def test_demo_needs_no_ledger(self):
        self.assertEqual(cli.main(["demo"]), 0)

    def test_end_to_end(self):
        self.assertEqual(self.run_cli("init"), 0)
        self.assertEqual(self.run_cli("add", "07", "--title", "A Paper Title"), 0)
        self.assertEqual(self.run_cli("advance", "07", s.FETCHED), 0)
        self.assertEqual(self.run_cli("advance", "07", s.READ_FULL), 6)

        receipt_path = os.path.join(self.dir, "receipt.json")
        with open(receipt_path, "w", encoding="utf-8") as handle:
            json.dump(RECEIPT, handle)

        self.assertEqual(self.run_cli("receipt", "07", "--file", receipt_path), 0)
        self.assertEqual(self.run_cli("advance", "07", s.READ_FULL), 0)
        self.assertEqual(self.run_cli("advance", "07", s.VERIFIED), 0)
        self.assertEqual(self.run_cli("status", "07"), 0)
        self.assertEqual(self.run_cli("list"), 0)

    def test_duplicate_exit_code(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "A Paper Title")
        self.assertEqual(self.run_cli("add", "08", "--title", "a paper title"), 2)

    def test_illegal_transition_exit_code(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "T")
        self.assertEqual(self.run_cli("advance", "07", s.VERIFIED), 5)

    def test_unknown_paper_exit_code(self):
        self.run_cli("init")
        self.assertEqual(self.run_cli("status", "nope"), 1)

    def test_check_incomplete_exit_code(self):
        path = os.path.join(self.dir, "partial.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"number_with_locator": "x"}, handle)
        self.assertEqual(cli.main(["check", "--file", path]), 6)

    def test_check_complete_exit_code(self):
        path = os.path.join(self.dir, "full.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(RECEIPT, handle)
        self.assertEqual(cli.main(["check", "--file", path]), 0)

    def test_json_output(self):
        self.run_cli("init")
        self.run_cli("add", "07", "--title", "T")
        self.assertEqual(cli.main(["--ledger", self.path, "--json", "status", "07"]), 0)


if __name__ == "__main__":
    unittest.main()
