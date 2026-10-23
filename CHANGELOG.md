# Changelog

## 0.7.1 — unreleased

Answers "how do I install it?" without requiring anybody's PyPI credential.

### Added
- CI `package` job: builds sdist + wheel, asserts `readproof/static/index.html` and the
  built assets are really inside the wheel (publishing without them would serve 503),
  installs the wheel into a clean virtualenv, and serves the app from it with no Node and
  no `--web-dir`. The wheel is attached to the run as an artifact.
- README (en/zh): three installation paths, starting with the one that works today —
  `pip install "readproof @ git+https://github.com/rrdongdong/readproof.git"`.
- RELEASE.md: what a PyPI API token is, why it cannot be shared or pasted into a chat, and
  what to do instead if you would rather not publish at all.

### Note
Nothing here needs a token, which was the point: the token only shortens the command.

## 0.7.0 — unreleased

Hard problem from the self-assessment: the UI needed Node. It no longer does.

### Changed
- **The built frontend now ships inside the package**, at `readproof/static/`, and is
  committed. `readproof serve` finds it by itself, so a clone, a wheel or a `pip install`
  all have a working UI. Before this, "one command to see it" actually meant
  `cd web && npm install && npm run build` first — 65 packages for a demo.
- Vite builds straight into the package (`build.outDir: '../readproof/static'`) so there is
  exactly one copy of the built assets, not one in `web/dist` and another in the package.

### Added
- `readproof bundle` — rebuild the frontend and stamp `readproof/static/BUILD.json` with a
  hash of `web/src`; `readproof bundle check` fails when the committed build is stale
  (exit 1) and `bundle` itself exits 11 with instructions when npm is absent
- `serve` resolves the web directory in a documented order: `--web-dir`, `$READPROOF_WEB_DIR`,
  the bundled copy, then a development `web/dist`. An explicit `--web-dir` is honoured or
  refused, never silently replaced — a typo should say so
- 10 tests (186 total): fingerprint stability and change detection, staleness before and
  after a source edit, explicit-dir precedence, and a guard that the committed bundle
  matches the current `web/src`
- CI: `bundle check` in the test job; the web job rebuilds and asserts the committed build
  is byte-identical, checks the bundle makes no remote requests, and serves the app with
  **no `--web-dir`** while asserting content types
- `RELEASE.md` — the three pre-release checks, how to rebuild the frontend, and the PyPI
  steps including a check that the wheel really contains `static/`

### Fixed
- `BUILD.json` listed the built files as **absolute paths**, so the manifest changed per
  machine and published a home directory — the same mistake the demo ledger had. It is
  relative now, and a test asserts it.
- the source hash folded in raw bytes, so a Windows checkout with `core.autocrlf` looked
  stale. Line endings are normalised to LF before hashing, `.gitattributes` pins LF for
  the repo, and the built directory is marked `-text`.

### Note
`pip install readproof` still 404s: publishing needs a PyPI token, so the release path is
documented and prepared rather than executed.

## 0.6.5 — unreleased

Blank page with the stylesheet applied — the worst kind of failure, because it looks
like a broken build and reports nothing.

### Fixed
- **Content types no longer come from `mimetypes`.** On Windows, `mimetypes` reads the
  registry, and `HKEY_CLASSES_ROOT\.js` commonly maps to `text/plain`. A module script
  served as text/plain is refused by the browser, and because the stylesheet (`text/css`)
  still loads, the result is a dark page with nothing on it. `serve` now uses an explicit
  extension table, and sends `X-Content-Type-Options: nosniff` so a wrong type is a loud
  console error instead of a silent one.
- **A missing asset is now a 404, not the SPA fallback.** Answering a missing `.js` with
  `index.html` produced "Expected a JavaScript module script but the server responded
  with a MIME type of text/html" — an error message that never mentions the missing file.
  Extensionless paths still fall back to the app.

### Added
- `index.html` carries a static explanation that disappears once React mounts, plus
  `window.onerror` / `unhandledrejection` reporting — a blank page can now say why
- a React error boundary, so a render crash shows the exception instead of nothing
- 6 tests: wrong-`mimetypes` regression, asset 404 for `.js` and `.css`, extensionless
  route still served, `nosniff` header, boot explanation present
- CI asserts the served content type of the real built bundle, and that a missing asset
  is 404 while `/paper/07` is 200

### Note
Reported by the user as "上面是黑屏的呀，什么都没有" — with the API working and the demo
output printing correctly, which is exactly what made a silent MIME failure the prime
suspect.

## 0.6.4 — unreleased

The demo ledger no longer turns `git pull` into a conflict.

### Fixed
- Committed demo outputs changed on every run, because the ledger stamps each paper's
  `history` with the wall clock. Any `python demo/build_demo.py` left `demo/ledger.json`
  dirty and the next `git pull` refused to merge. Reported from a real pull on Windows.
  - `store` now honours `READPROOF_NOW`, a pinned clock for reproducible artefacts
  - `demo/build_demo.py` pins it and passes relative fixture paths
  - `intake` records the source **exactly as given** instead of rewriting it to an
    absolute path — an absolute path both changed per machine and published the author's
    home directory in a public repository
  - CI asserts `git diff --exit-code -- demo/` after a rebuild, which is what caught the
    absolute-path problem immediately after the clock was pinned
- 4 tests: pinned clock, real clock by default, verbatim source, relative source

### Note
Committing generated files is a deliberate trade: a fresh clone can start the UI with no
build step. That only works if generation is deterministic — now enforced on every run,
not assumed.

## 0.6.3 — unreleased

Two more Windows bugs, both found by the new windows CI job rather than by guessing.

### Fixed
- `$READPROOF_PDF_COMMAND` mangled Windows paths: `shlex.split` applies POSIX rules where
  a backslash escapes the next character, so `C:\tools\python.exe` became
  `C:toolspython.exe` and `shutil.which` failed on a path that exists. `sources.split_command()`
  now splits without POSIX escaping on Windows and strips quotes itself; quoted paths with
  spaces work too.
- tests assumed the interpreter is called `python3`; a GitHub runner calls it `python`.

### Added
- 2 regression tests for command splitting (Windows paths, quoted paths with spaces)
- CI unit-test failures are now published as **annotations** (`::error::`), because job logs
  need authentication while annotations are public. The first attempt pushed the verbose
  tail and the annotation cap swallowed the failure; it now sends only the failure block.

## 0.6.2 — unreleased

Windows fix: a single glyph could kill a build.

### Fixed
- `graph build` exited 1 on a Chinese Windows install with
  `'gbk' codec can't encode character '\u27c2'` — the U+27C2 in the assumption-gap
  heading. Python uses UTF-8 for an interactive console but the locale encoding (cp936)
  for a pipe, and GBK cannot encode that character, so the process died while printing a
  finding. Reported from a real run on Windows.
  - `cli.main()` now reconfigures its own stdout/stderr to UTF-8 with
    `errors="replace"`, so no console codec can stop the work; `errors` also covers the
    case where a glyph genuinely cannot be shown
  - `demo/build_demo.py` decodes its child as UTF-8 (it was reading the child with the
    locale) and applies the same reconfigure to its own output
- 3 regression tests: a cp936 pipe, an ascii console, and a strict cp936 codec, each
  asserting exit 0 and UTF-8 output

### Note
This was found by the user running `python demo/build_demo.py --serve` on Windows, not by
CI — the CI matrix only had Linux. The fix is covered by tests now; the Windows matrix
remains the honest gap.

## 0.6.1 — unreleased

A committed demo, and a gate the demo made obvious.

### Added
- `demo/` — a five-paper synthetic ledger, a seven-term vocabulary, and the outputs they
  produce (`ledger.json`, `gap-table.md`, `graph.json`), committed so a fresh clone can start
  the UI without running anything first
  - covers four states and **one instance of every gap query**, G1 through G6
  - `demo/build_demo.py` regenerates everything; `--serve` builds then serves
  - entirely synthetic, with `[synthetic]` titles: a public repository should not publish
    anybody's reading list or research direction
- `Makefile` — `make test`, `make web`, `make demo`, `make serve-demo`, `make clean`
- CI: the demo must build, produce all six gap kinds, and keep every card on a readable paper

### Fixed
- **A problem card could be recorded for an unread paper.** Cards are reading artefacts —
  every entry carries a page and an evidence grade, and neither can exist before some of the
  text has been read. `set_card()` now requires at least `READ_PARTIAL` and says why. The
  test suite and the demo both had to advance papers before recording cards, which is the
  proof the gate bites.

## 0.6.0 — unreleased

A web interface: the discipline becomes visible instead of requiring `cat ledger.json`.

### Added
- `readproof/serve.py` — read-only API on the standard library's `http.server`
  - `GET /api/papers`, `/api/papers/{id}`, `/api/gaps`, `/api/meta`, `/api/health`
  - payloads carry what the gate actually permits: `receipt.present/missing` per field and
    `may_write` per state, so the UI can show "this paper cannot become READ_FULL" instead of
    a colour nobody can explain
  - `/api/gaps` reports `available: false` with a hint when no vocabulary is loaded, rather than
    an empty table that looks like "no gaps found"
  - unresolved phrases appear in the UI's triage pool with their similarity suggestions
  - SPA fallback, path-traversal refusal, `no-store` caching, 503 with build instructions when
    `web/dist` is missing
- `web/` — Vite + React frontend (papers / paper detail / gaps / state machine), hash routing,
  dark theme, evidence grades colour-coded E1 green · E2 blue · E3 amber · E4/E5 grey
- CLI: `readproof serve --host --port --vocab --web-dir`
- `tests/test_serve.py` — 16 tests, including a real HTTP round trip, traversal refusal and the
  missing-frontend hint
- CI: a second job installs the frontend, builds it, asserts the bundle makes **no remote
  requests** (the interface has to work offline during a demo), then starts the server and
  checks the API and the app are served

### Why not FastAPI
The target machine has no `pip`, and a framework would break the property that makes the engine
testable: no third-party dependencies. The routing is a dozen lines. The frontend is a real
build chain because that is where a build earns its keep.

### Also
- 161 tests total
- `readproof` stays writable only through the CLI: every gate keeps its exit code and is tested
  without a socket

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
