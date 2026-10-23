# Changelog

## 0.5.0 — unreleased

The semantic layer: a controlled vocabulary, problem cards, a graph, and six gap queries.
This is the step from "read correctly" to "connect correctly".

### Added
- `readproof/vocab.py` — the only place a node may be created
  - TSV with `id / name / kind / aliases / parent / excludes`; ids are
    `<KIND>-<CATEGORY>-<NN>` (`P` problem, `L` limitation, `A` assumption, `M` method;
    categories `SCALE ROBUST ASSUME THEORY EVAL ENGINEER`)
  - nine validation rules, each with a test: id format, category membership, id-prefix vs kind,
    parent consistency, duplicate id, **one concept under two ids**, alias collisions,
    `excludes` pointing at unknown ids, self-exclusion
  - longest-alias resolution; `suggestions()` uses character similarity so a triage entry
    like "uplink bandwith" still finds its concept
  - `category_blank()` reports categories with no problem yet — the skeleton's visible blanks
- `readproof/graph.py` — build, health, six queries, output
  - every edge carries paper + location; **an edge without a location fails the health check**
  - unresolved phrases go to `triage`, never into the graph
  - anomalies are records, not vocabulary nodes, and are excluded from node/component stats
  - G1 consensus · G2 silent · G3 contested (criticised but never benchmarked) · G4 assumption
    (one finding per contradictory pair, silent when a paper assumes both) · G5 isolated
    (suppressed when a stronger query already reported the node) · G6 anomaly
  - health thresholds with a **scale guard**: a graph smaller than 10 referenced nodes is not
    judged for orphans, so a bootstrap graph does not fail on day one
  - `gap_table()` renders statements + evidence + counting, and ends with five questions for the
    human — deliberately not "innovation ideas"
- `ledger.set_card()` / `card_for()` — cards live next to the papers they describe; unknown
  relations are rejected
- CLI: `vocab`, `card` (with `--solves/--leaves-open/--assumes/--admits/--criticizes/
  --criticizes-uncompared/--anomaly`), `graph build|check|query|stats`
- 59 new tests (145 total), including "one concept two ids is rejected", "unknown node lands in
  triage, not the graph", "edge without location exits 4", "compared criticism is not contested"
- CI: a graph stage building from four cards, asserting gap types are present, that a missing
  location exits 4, and that an unknown vocabulary id lands in triage

### Fixed
- `category_blank()` compared full kind names against short ones, so every category looked empty
- G4 reported each contradictory pair twice (once per direction)
- G5 repeated nodes already surfaced by G1–G4

## 0.4.0 — unreleased

A PDF can come in now — and be refused before it influences anything.

### Added
- `readproof/pdf.py` — byte-level inspection, no parser
  - `inspect_bytes()`: `%PDF-` header, `%%EOF` trailer, size floor (64 B), page-object count
    (`/Type /Page` only, so the `/Pages` tree node is not miscounted), SHA-256
  - `require_valid()` raises `PdfError` (exit 8) — a truncated download looks like a successful
    fetch and would otherwise produce a receipt from half a paper
  - `download()`: http(s) only, 30 MB cap, no redirect to `file://`
  - `identity_matches()`: ledger title vs. the first pages, so an upload of the wrong paper is
    caught before it becomes a receipt (exit 9, overridable with `--accept-mismatch`)
- `readproof/sources.py` — extractor discovery without shipping one
  - tries `pdftotext`, then `mutool`, then `$READPROOF_PDF_COMMAND`
  - contract: PDF path is the last argument, page-separated text on stdout; `{pdf}` placeholder
    optional, so plain CLIs work unchanged
  - no extractor ⇒ `ExtractorUnavailable` (exit 7) with four concrete options, rather than a
    silent empty read
  - distinguishes "extractor failed" from "PDF has no text layer (scanned)"
- CLI: `intake <id> <pdf-or-url>`, `receipt --from-pdf`, and `extract` now auto-detects a PDF
  - `intake` records `{source, bytes, sha256, page_objects, identity, accepted_mismatch}` on the
    paper and moves it to `FETCHED` with `via=manual_upload` — never further
- fixtures: a synthetic valid PDF, a truncated one, a non-PDF, and a fake extractor that doubles
  as executable documentation of the contract
- 23 new tests (86 total)
- CI: a PDF intake stage asserting exit 8 (truncated, non-PDF), 9 (title mismatch) and 6
  (`READ_FULL` after an accepted intake), then the full path to `VERIFIED`

### Notes
- Still zero runtime dependencies; the extractor is external by design, not vendored.

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
