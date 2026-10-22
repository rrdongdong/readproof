# Changelog

## 0.2.0 — unreleased

Runnable. The gates are now reachable from a shell, and every refusal is an exit code.

### Added
- `readproof/store.py` — JSON ledger, the single source of truth for reading state
  - `add()` registers at `UNREAD` and rejects duplicates on id, folded title, arXiv id or DOI
    (`DuplicatePaper`, exit 2)
  - `advance()` validates the state edge and, for `READ_FULL`, requires a complete receipt
    (`IllegalTransition` exit 5 / `IncompleteReceipt` exit 6)
  - `set_receipt()` refuses to store an incomplete receipt — a partial receipt must not sit in the
    ledger looking like progress
  - atomic `save()`; per-paper `history` records every transition with timestamp, source and `via`
- `readproof/cli.py` + `readproof/__main__.py` — commands `init`, `add`, `advance`, `receipt`,
  `check`, `status`, `list`, `demo`; `--json` for machine output; `--ledger` / `$READPROOF_LEDGER`
- `pyproject.toml` — installable, `readproof` console script, no runtime dependencies
- 24 new tests (42 total): dedup folding, transition gates, receipt rejection, persistence round-trip,
  CLI exit codes for all four failure classes
- CI: CLI end-to-end step asserting exit codes 2 / 5 / 6, then the full path to `VERIFIED`

### Changed
- `normalize_identifier()` now folds `arXiv:` / `doi:` prefixes and version suffixes, so
  `arXiv:2601.00001v2` and `2601.00001` collide instead of slipping past dedup

### Fixed
- arXiv/DOI dedup could be bypassed by writing the same identifier in a different form
  (caught by a test, never shipped)

## 0.1.0 — first cut

The part everything else depends on: the state machine.

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
