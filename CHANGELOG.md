# Changelog

## 0.3.0 — unreleased

Receipt extraction. The gate that was only a validator now has a producer — and the
producer can refuse.

### Added
- `readproof/receipt.py` — find the four fingerprints in extracted paper text
  - `assess()` classifies the input as `full` / `partial` / `abstract_only` using page
    count, character count, presence of an experiment section and a reference list;
    thresholds are named constants and injectable
  - `extract_receipt()` returns the four fingerprints with page and section
    provenance, or raises `ReceiptExtractionError` (exit 6) — **it will not manufacture
    fingerprints from an abstract**
  - finders: caption + unit-bearing numbers (`number_with_locator`), hyperparameter
    statements (`hyperparameters`), limitation sentences in the authors' own voice
    (`negative_quote`), setup/implementation sentences (`body_detail`)
  - does **not** parse PDFs: text extraction stays with `dsh-pdf`, whose pdfjs-dist
    backend handles subsetted CID fonts that a stdlib parser cannot
- `readproof receipt --from-text paper.txt` and `readproof extract paper.txt` (preview,
  stores nothing); `--allow-partial` to inspect a refused input without accepting it
- synthetic fixtures + generator (`tests/fixtures/make_fixtures.py`): a full 7-page
  paper, an abstract-only paper, and a three-page excerpt
- 21 new tests (63 total), including "abstract-only yields exit 6 and does not move the
  paper" and "turning off the verdict gate must not invent fingerprints"
- CI: extract a full paper, assert an abstract is refused with 6, then walk a second
  paper to `READ_FULL` via extracted fingerprints

### Fixed
- `ReceiptExtractionError` was not caught by the CLI, so a refused receipt surfaced as
  a traceback instead of exit 6
- short excerpts were labelled `abstract_only`; a three-page excerpt of a real paper is
  a `partial` read and the message now says so
- section labels in `body_detail` came out lowercased

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
