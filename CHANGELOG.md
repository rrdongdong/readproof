# Changelog

## 0.1.0 — unreleased

First cut. Only the part that everything else depends on: the state machine.

### Added
- `readproof/states.py` — six-state paper reading state machine
  (`UNREAD`, `FETCH_FAILED`, `FETCHED`, `READ_PARTIAL`, `READ_FULL`, `VERIFIED`)
  - transitions are validated, not suggested; an illegal jump raises
    `IllegalTransition` with `exit_code == 5`
  - capability gating: `can_write(state, artefact)` decides whether a paper may
    emit metadata / abstract notes / the 8-question note / a gap entry
  - manual upload is a first-class path that can only ever reach `FETCHED`,
    so it can never shortcut the reading receipt
  - reading receipt: four non-abstract fingerprints
    (`number_with_locator`, `hyperparameters`, `negative_quote`, `body_detail`)
    and `receipt_is_complete()`
  - `may_promote_to_read_full()` combines the state edge with the receipt
- 18 unit tests covering illegal jumps, manual-upload limits, capability gating and
  abstract-only receipts
- CI: Python 3.9/3.11/3.12, syntax gate, unit tests, gate smoke test, stdlib-only check

### Not yet
Reading receipt extraction, spot-check challenge, controlled vocabulary, graph build
and gap queries G1–G6 are designed in `docs/design.md` but not implemented.
