# readproof · 读证

> *Every paper leaves a receipt. No receipt, no conclusion.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

**A research-assistant agent that refuses to pretend it read something.**

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
| State machine + capability gating | ✅ implemented (`readproof/states.py`), tested |
| Reading receipt / spot-check | designed, not implemented |
| Controlled vocabulary + graph build | designed, not implemented |
| Gap queries G1–G6 | designed, not implemented |

Design rationale: [`docs/design.md`](./docs/design.md).

## Ecosystem

`readproof` is the engine. It reuses two separately versioned pieces rather than absorbing them:

- [`paper-trawl`](https://github.com/rrdongdong/paper-trawl) — one pipeline stage: search → tier → deep read → ledger
- [`dsh-pdf`](https://github.com/rrdongdong/dsh-pdf) — the reading capability: PDF extraction with `%%EOF` integrity checks

```
readproof      engine: state machine, evidence gates, problem graph, gap queries
├── paper-trawl    a stage it runs
└── dsh-pdf        how it reads
```

## License

MIT
