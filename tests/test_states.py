import unittest

from readproof import states as s


class TransitionTests(unittest.TestCase):
    def test_happy_path(self):
        chain = [s.UNREAD, s.FETCHED, s.READ_PARTIAL, s.READ_FULL, s.VERIFIED]
        for current, target in zip(chain, chain[1:]):
            self.assertEqual(s.check_transition(current, target), target)

    def test_unread_cannot_jump_to_read_full(self):
        with self.assertRaises(s.IllegalTransition) as ctx:
            s.check_transition(s.UNREAD, s.READ_FULL)
        self.assertEqual(ctx.exception.exit_code, 5)

    def test_fetch_failed_cannot_jump_to_read_full(self):
        with self.assertRaises(s.IllegalTransition):
            s.check_transition(s.FETCH_FAILED, s.READ_FULL)

    def test_verified_is_terminal(self):
        self.assertEqual(s.next_states(s.VERIFIED), ())
        with self.assertRaises(s.IllegalTransition):
            s.check_transition(s.VERIFIED, s.READ_FULL)

    def test_download_failure_is_a_real_state(self):
        self.assertEqual(s.check_transition(s.UNREAD, s.FETCH_FAILED), s.FETCH_FAILED)

    def test_read_partial_can_be_upgraded(self):
        self.assertEqual(s.check_transition(s.READ_PARTIAL, s.READ_FULL), s.READ_FULL)


class ManualUploadTests(unittest.TestCase):
    def test_manual_upload_reaches_fetched(self):
        self.assertEqual(
            s.check_transition(s.UNREAD, s.FETCHED, via=s.MANUAL_UPLOAD), s.FETCHED
        )
        self.assertEqual(
            s.check_transition(s.FETCH_FAILED, s.FETCHED, via=s.MANUAL_UPLOAD),
            s.FETCHED,
        )

    def test_manual_upload_cannot_skip_the_receipt(self):
        for target in (s.READ_PARTIAL, s.READ_FULL, s.VERIFIED):
            with self.assertRaises(s.IllegalTransition) as ctx:
                s.check_transition(s.FETCH_FAILED, target, via=s.MANUAL_UPLOAD)
            self.assertEqual(ctx.exception.exit_code, 5)

    def test_unknown_source_rejected(self):
        with self.assertRaises(s.IllegalTransition):
            s.check_transition(s.UNREAD, s.FETCHED, via="telepathy")


class CapabilityTests(unittest.TestCase):
    def test_metadata_only_after_fetch(self):
        self.assertFalse(s.can_write(s.UNREAD, "metadata"))
        self.assertFalse(s.can_write(s.FETCH_FAILED, "metadata"))
        self.assertTrue(s.can_write(s.FETCHED, "metadata"))

    def test_reading_note_requires_full_text(self):
        self.assertFalse(s.can_write(s.FETCHED, "eight_questions"))
        self.assertFalse(s.can_write(s.READ_PARTIAL, "eight_questions"))
        self.assertTrue(s.can_write(s.READ_FULL, "eight_questions"))

    def test_gap_entry_requires_verification(self):
        self.assertFalse(s.can_write(s.READ_FULL, "gap_entry"))
        self.assertTrue(s.can_write(s.VERIFIED, "gap_entry"))

    def test_unknown_artefact_rejected(self):
        with self.assertRaises(ValueError):
            s.can_write(s.VERIFIED, "vibes")


class ReceiptTests(unittest.TestCase):
    def complete(self):
        return {
            "number_with_locator": "Table II: 41.2 / 38.7 / 35.1 dB (p.5)",
            "hyperparameters": "lr=2e-4, iters=20k (sec IV-A, p.4)",
            "negative_quote": "we do not report results under motion blur (sec V-D, p.7)",
            "body_detail": "cosine schedule appears only in a p.3 footnote",
        }

    def test_complete_receipt(self):
        self.assertTrue(s.receipt_is_complete(self.complete()))
        self.assertEqual(s.missing_receipt_fields(self.complete()), [])

    def test_abstract_only_receipt_is_rejected(self):
        receipt = self.complete()
        del receipt["negative_quote"]
        del receipt["hyperparameters"]
        self.assertFalse(s.receipt_is_complete(receipt))
        self.assertEqual(
            s.missing_receipt_fields(receipt), ["hyperparameters", "negative_quote"]
        )

    def test_blank_strings_do_not_count(self):
        receipt = self.complete()
        receipt["body_detail"] = "   "
        self.assertEqual(s.missing_receipt_fields(receipt), ["body_detail"])

    def test_non_dict_receipt_is_entirely_missing(self):
        self.assertEqual(s.missing_receipt_fields(None), list(s.RECEIPT_FIELDS))

    def test_promotion_needs_both_state_and_receipt(self):
        ok, reasons = s.may_promote_to_read_full(s.FETCHED, self.complete())
        self.assertTrue(ok, reasons)

        ok, reasons = s.may_promote_to_read_full(s.FETCHED, {})
        self.assertFalse(ok)
        self.assertTrue(any("receipt" in r for r in reasons))

        ok, reasons = s.may_promote_to_read_full(s.UNREAD, self.complete())
        self.assertFalse(ok)
        self.assertTrue(any("state" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
