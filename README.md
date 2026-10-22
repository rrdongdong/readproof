# readproof · 读证

> *Every paper leaves a receipt. No receipt, no conclusion.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**A research-assistant agent that refuses to pretend it read something.**

Built on [DSH](https://github.com/deepseek-ai/deepseek-harness) (DeepSeek Harness, Cordis plugin
architecture) — it is the engine of a DSH research-assistant stack, not a standalone chatbot.
See [Built on DSH](#built-on-dsh) for exactly which layer is DSH and which is this repo.

English | [中文](./README.zh.md)

---

## The problem it solves

Ask any LLM "summarise this paper" and you get a fluent answer. Ask it *"which page says that?"* and it
falls apart. That failure has a name here: **fake reading** — the agent could not get the full text, so
it answered from the abstract and from memory, and nothing in the system made that visible.

A second failure shows up later: you read 30 papers, take 30 sets of notes, and still cannot answer
*"what is still unsolved in this field?"* — because the answer is not in any single paper. It lives in
the **seams between papers**: one admits a limitation, another never cites it, a third reports a number
that contradicts both. Free-text notes cannot hold seams. That failure is **graph fragmentation**.

Most of this repo exists to make those two failures impossible.

## Quickstart

No dependencies — Python 3.9+ and the standard library only.

```console
$ pip install -e .                 # or skip install: export PYTHONPATH=$PWD
$ readproof demo                   # the state machine; needs no ledger
$ readproof init
created /path/readproof-ledger.json
$ readproof add 07 --title "A Paper Title" --venue "CVPR 2026" --arxiv 2601.00001
07 added at UNREAD
$ readproof advance 07 FETCHED
07 -> FETCHED
$ readproof advance 07 READ_FULL
readproof: refusing FETCHED -> READ_FULL: missing reading-receipt fingerprints:
  number_with_locator, hyperparameters, negative_quote, body_detail
$ echo $?
6
$ readproof receipt 07 --from-text paper.txt     # find the four fingerprints for me
verdict : full
  pages : 7
  chars : 13869
  [v] number_with_locator  Table II: 41.2 dB / 38.7 dB / 36.4 dB (p.5)
  [v] hyperparameters      lr=1e-4, batch=4, iters=30000 (sec Experiments, p.5)
  [v] negative_quote       We do not evaluate on real underwater sequences ... (sec Limitations, p.6)
  [v] body_detail          We implement the residual weighting as a small module ... (sec Implementation, p.4)
receipt stored for 07 (4 fingerprints)
$ readproof advance 07 READ_FULL
07 -> READ_FULL
$ readproof status 07
07  READ_FULL
  may write: metadata, abstract_note, eight_questions
  receipt : complete
  history :
    2026-10-22T13:37:50+00:00  None -> UNREAD (pipeline)
    2026-10-22T13:37:50+00:00  UNREAD -> FETCHED (pipeline)
    2026-10-22T13:38:53+00:00  FETCHED -> READ_FULL (pipeline)
```

`paper.txt` is text with form-feed page breaks — what `pdftotext`, most extractors and
[`dsh-pdf`](https://github.com/rrdongdong/dsh-pdf) emit. `readproof` does not parse PDFs itself; a stdlib
PDF parser fails exactly where CVF/IEEE files are hardest (subsetted CID fonts, pages inside `/ObjStm`),
and garbage text is worse than an honest failure.

You can also pass the four fingerprints by hand (`--number/--hyper/--negative/--body`) or from JSON
(`--file`). `readproof extract paper.txt` shows what would be found without storing anything.

`python -m readproof …` behaves identically if you would rather not install.

### Exit codes are the contract

The gates are only real if a caller cannot ignore them, so failure is an exit code, not a warning:

| Code | Meaning |
|---|---|
| `0` | ok |
| `1` | generic error (unknown paper, unreadable ledger, bad input) |
| `2` | duplicate paper — **blocked, not merged** |
| `5` | illegal state transition (including manual upload skipping ahead) |
| `6` | incomplete reading receipt |

Commands: `init`, `add`, `advance`, `receipt`, `extract`, `check`, `status`, `list`, `demo`. The ledger is a plain
JSON file (`--ledger`, or `$READPROOF_LEDGER`); state changes are appended to a per-paper `history`, so
every jump is auditable after the fact.

## How it works

```
                       ┌── auto-fetch ─────┐
UNREAD ────────────────┤                   ├──▶ FETCHED ──▶ READ_PARTIAL ──▶ READ_FULL ──▶ VERIFIED
                       └── manual upload ──┘         │              │             │          │
   │                                           file + EOF +      coverage       coverage    spot-check
   │                                           identity check      < 90%         ≥ 90%      passed
   └──▶ FETCH_FAILED ──▶ ask the user to upload the PDF
```

Each state **grants capabilities**; it is not a label:

| State | What may be written |
|---|---|
| `UNREAD` | nothing but a title |
| `FETCH_FAILED` | nothing content-bearing; goes to the upload queue |
| `FETCHED` | metadata only (title / venue / DOI) |
| `READ_PARTIAL` | abstract-level notes — **must** state "read only pp. X–Y" |
| `READ_FULL` | the full 8-question reading note |
| `VERIFIED` | may enter the gap table, may be cited in reports |

Jumping a state is an error, not a warning. Manual upload can only ever reach `FETCHED` — it relaxes
*how you obtain the file*, never *what counts as evidence*.

### The reading receipt

A `READ_FULL` paper must leave four fingerprints that an abstract cannot contain:

1. a concrete number, with table/number **and** page
2. a set of hyperparameters, with section number
3. one negative statement quoted verbatim (`"we do not …"`)
4. one non-conclusory body detail (setup, baseline config, failure case)

If you only have the abstract, you cannot fill these in — so the state stays `READ_PARTIAL`, the
8 questions stay unwritable, and no report gets produced. **The format is the gate.**

### Four gates

| Gate | Mechanism | Failure |
|---|---|---|
| ① dedup | ledger short-name / DOI / arXiv ID | `exit 2` — **blocks** |
| ② full text | `%%EOF` + coverage ≥ 90% + receipt fields | refuses to write the reading note |
| ③ evidence | every claim carries `{location, E1–E5}`; E3–E5 may **not** be phrased as "the authors admit" | `check` errors out |
| ④ verify | citation allow-list + line-number existence + locatable section | sentence removed or downgraded |

All four are code. None is a prompt instruction.

## The semantic layer

Papers are nodes; so are the problems they solve, the assumptions they rest on, and the limitations they
admit. Edges carry evidence, and **an edge without `evidenced_by` never enters the graph**.

Free-text problem names are what breaks this: one concept becomes four nodes and the graph never
connects. So node creation goes through a **controlled vocabulary** — canonical id + aliases, `object@condition`
naming, six fixed categories (`SCALE / ROBUST / ASSUME / THEORY / EVAL / ENGINEER`). The build step
**never auto-creates a canonical id**; unmatched items go to a triage pool instead.

Gap queries over that graph:

| Query | Condition | Meaning |
|---|---|---|
| G1 consensus | ≥3 papers `leaves_open` the same problem | real problem, lowest risk |
| G2 silent | ≥2 papers hit a limitation, nobody solves it | best effort/reward |
| G3 contested | A calls B insufficient, B never benchmarks A | largest headroom |
| G4 assumption | two methods rest on contradictory assumptions | best fit for a course project |
| G5 isolated | 1 mention, no follow-up | may be a non-problem — list only |
| G6 anomaly | reported numbers contradict intuition, unexplained | most likely to yield real novelty |

The output is a **gap table**, deliberately not "innovation ideas". Inventing ideas needs a human who
knows the hardware, the data and the advisor; and an AI-generated "novelty" passed off as one's own is a
research-integrity problem. So the table gives: problem statement, evidence chain with page/section, what
has been tried, what has not, validation cost — plus a worksheet of questions for the human.

## What counts as success

- pull any conclusion and point at the page/table it came from
- no paper is read twice, no problem becomes two nodes
- after ~30 papers the gap table contains at least one entry that makes you think *"nobody has done this"*

## Non-goals

Not a paper summariser. Not an auto-writer. Not an all-field literature reviewer. Not a chat box — it
emits files, and its value accumulates in a ledger, not in a conversation history.

## Status

| Piece | State |
|---|---|
| State machine + capability gating (`readproof/states.py`) | ✅ implemented, 18 tests |
| JSON ledger + CLI with gated exit codes (`store.py`, `cli.py`) | ✅ runnable, 24 tests |
| Reading receipt **validation** | ✅ implemented (rejects abstract-only receipts) |
| Reading receipt **extraction** from extracted text (`receipt.py`) | ✅ implemented, 19 tests |
| PDF → text (delegated to `dsh-pdf`) | out of scope by design |
| Spot-check challenge | designed, not implemented |
| Controlled vocabulary + graph build | designed, not implemented |
| Gap queries G1–G6 | designed, not implemented |

What `readproof` can do today, end to end: keep a deduplicated ledger; extract the four receipt
fingerprints from a paper's text and refuse when the text is only an abstract or an excerpt; refuse to
advance a paper past `FETCHED` without a complete receipt; fail with a specific exit code for each rule
broken. What it cannot do yet: fetch or extract the PDF itself (delegated to `dsh-pdf`), or build the
problem graph.

Design rationale: [`docs/design.md`](./docs/design.md).

## Built on DSH

[DSH](https://github.com/deepseek-ai/deepseek-harness) is a Cordis-based agent harness: it supplies the
tool contract, the skill/plugin model, the sandbox, session persistence and the chat channels. `readproof`
is the **engine** that plugs into it. The stack is layered, and the pieces are versioned separately on
purpose:

| Layer | What it settles | Where |
|---|---|---|
| **capability** | reading a PDF: extraction, `%%EOF` integrity, download retries | [`dsh-pdf`](https://github.com/rrdongdong/dsh-pdf) — a DSH **plugin** (v0.4.2) |
| **pipeline** | how to read: search → tier → deep read → ledger → summary | [`paper-trawl`](https://github.com/rrdongdong/paper-trawl) — a DSH **skill** (v1.0.1) |
| **engine** | what counts as read, what may be written, how gaps are found | **this repo** |
| **discipline** | the rules themselves: evidence grades, forbidden phrasings, gate semantics | this repo + the skill's prompts |

```
DSH  (harness: tools, skills, sandbox, sessions, channels)
└── readproof   engine: state machine, evidence gates, problem graph, gap queries
    ├── paper-trawl   a pipeline stage it runs   (DSH skill)
    └── dsh-pdf       how it reads               (DSH plugin)
```

### The engine itself is framework-free

`readproof/states.py` is **stdlib-only and imports nothing from DSH**. That is deliberate, not incidental:

> the part that decides *whether a claim may be written* must be testable without a running agent —
> in CI, on every commit, on three Python versions.

A gate that can only be exercised by talking to a live agent is a gate nobody exercises. DSH supplies the
tool and skill boundary; it does not supply the rules, so the rules stay portable Python that CI can hammer.

> **Not affiliated with DeepSeek.** "DeepSeek Harness (DSH)" and "Cordis" are used descriptively.

## License

MIT
