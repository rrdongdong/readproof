# Design

Why this project exists, and the two failure modes it is built around.

Free of implementation detail: [`README.md`](../README.md) has the summary, this file has the reasoning.

---

## 1. The two failure modes

### 1.1 Fake reading

An agent is asked about a paper. It cannot obtain the full text — paywalled, CID-encoded, a scan with
no text layer, a network failure. It answers anyway, from the abstract and from memory. Nothing in the
system records that the full text was never seen, so the answer is indistinguishable from a real one.

**The root cause is not laziness, it is missing expressive power.** If the system offers only "read"
and "not read", and "not read" produces nothing, then the shortest path to a deliverable is to write
"read". Fake reading is the inevitable result of a system that cannot say *"I got three pages of fifteen."*

So the fix is a state, not an instruction:

```
UNREAD ─▶ FETCH_FAILED ─▶ FETCHED ─▶ READ_PARTIAL ─▶ READ_FULL ─▶ VERIFIED
```

`FETCH_FAILED` and `READ_PARTIAL` exist so that partial success has somewhere to be reported. Once
"I only read pp. 1–3" is a legitimate, storable outcome, there is nothing to gain from claiming more.

### 1.2 Graph fragmentation

Thirty papers, thirty sets of notes, and the question *"what is still unsolved?"* is unanswerable —
because the answer is not inside any paper. It lives in the seams:

- paper A admits a limitation in its future work; nobody has since addressed it
- paper B calls method X insufficient; paper C uses X and never benchmarks against B
- paper D reports a number that contradicts the trend the other two assume, and does not explain it

None of these facts appear in any single paper. They only appear **between** papers, so they need a
structure that spans papers: nodes for problems, assumptions and limitations, edges carrying evidence.

The naive attempt fails immediately. Free-text problem names mean one concept becomes four nodes
("bandwidth bottleneck" / "uplink saturation" / "通信开销大" / "上行带宽受限"), the graph becomes 120
disconnected points, and every gap query returns nothing. **The root cause is that free node creation
is allowed.**

So node creation goes through a controlled vocabulary, and the build step never invents a canonical id.

---

## 2. States as capabilities

A label records where something is. A capability decides what can be written. This project needs the
latter, so each state maps to the artefacts it permits:

| State | Permitted artefacts |
|---|---|
| `UNREAD` | — (title only) |
| `FETCH_FAILED` | — (upload queue) |
| `FETCHED` | metadata |
| `READ_PARTIAL` | metadata, abstract-level note (must declare page range) |
| `READ_FULL` | + the 8-question reading note |
| `VERIFIED` | + gap entries, citable claims |

Implemented in `readproof/states.py` as `can_write(state, artefact)`. The point is that a report
generator asks the state machine whether a paper may contribute a claim, rather than trusting whoever
wrote the report.

## 3. The reading receipt

The state machine governs *whether* a paper may be written about. The receipt governs *why it counts as
read*. A `READ_FULL` paper must produce four fingerprints that an abstract cannot contain:

| Field | Why an abstract cannot supply it |
|---|---|
| `number_with_locator` | abstracts cite no table numbers or page numbers |
| `hyperparameters` | rarely stated at all, never with a section reference |
| `negative_quote` | abstracts do not say "we do not report results under motion blur" |
| `body_detail` | setup, baseline config and failure cases live in the body |

This is a format gate rather than a judgement gate: it cannot be argued with, only satisfied or not.
`receipt_is_complete()` in `readproof/states.py` implements it.

## 4. Manual upload

Paywalled papers exist. If there is no sanctioned path, users route around the system — and fake
reading returns through the back door. So manual upload is a first-class transition, with two
constraints that keep it from becoming that back door:

1. **It can only reach `FETCHED`.** Never `READ_FULL`. `check_transition(..., via=MANUAL_UPLOAD)`
   enforces this with exit code 5.
2. **It passes the same intake checks.** Non-empty, `%%EOF` present, at least two pages, not HTML
   masquerading as PDF, and an identity check (ledger title vs. first-page title, or DOI/arXiv id).

An upload also introduces a version hazard: what arrives is often a preprint, while the ledger cites the
camera-ready. Numbers may differ. So `version` is recorded, the receipt states which version was read,
and citations carry it. Conflicting numbers are logged as a version discrepancy rather than silently
resolved.

## 5. Evidence grading

Every claim carries a location and a grade. The grade constrains the wording, which is the part people
get wrong when reading quickly:

| Grade | Source | Permitted phrasing |
|---|---|---|
| `E1` | the paper's own limitation / future-work section | "the authors admit …" |
| `E2` | the paper's related-work criticism of prior work | "this paper claims … (possible straw man)" |
| `E3` | what the experimental design avoids | "**we observe** that it does not cover …" |
| `E4` | a later survey's assessment | "as [survey] notes …" |
| `E5` | our own inference | "**inference**: …" |

Writing E3–E5 as "the authors admit" is the single easiest way to produce an integrity problem while
feeling honest. `check` scans for that pattern.

## 6. Gap queries

| Query | Condition | What it means |
|---|---|---|
| G1 consensus | ≥3 papers `leaves_open` the same problem | the field agrees it is unsolved |
| G2 silent | ≥2 papers hit a limitation, no `solves` edge | everyone knows, nobody fixes |
| G3 contested | A calls B insufficient, B never benchmarks A | one experiment would settle it |
| G4 assumption | two methods assume mutually exclusive things | best fit for a small project |
| G5 isolated | one mention, no follow-up | possibly not a problem — listed only |
| G6 anomaly | reported numbers contradict intuition, unexplained | most likely to yield real novelty |

G6 is the most valuable and the most expensive: the other five can be approximated by searching, but an
anomaly is only visible by actually reading the tables.

## 7. What it deliberately does not output

Not "innovation ideas". Three reasons:

1. A model without knowledge of the available hardware, datasets and advisor direction produces
   recombination ("apply A to B"), which reads like novelty and is not.
2. Presenting generated novelty as one's own is an integrity violation, not a feature.
3. The judgement is the valuable part of research; outsourcing it removes the reason to do the reading.

The deliverable is a gap table — problem statement, evidence chain with page/section, what has been
tried, what has not, validation cost — plus a worksheet of questions for the human to answer.

## 8. Health metrics

Thresholds are checked at build time; exceeding one fails the build (`exit 4`) rather than printing a
warning. A messy graph produces a gap table that is confidently wrong, and — this is the dangerous part —
nothing in the output reveals that it is wrong.

| Metric | Threshold |
|---|---|
| orphan nodes | < 10% |
| triage-pool entries / total | < 15% |
| connected components | ≤ 2 |
| mean aliases per canonical | ≥ 1.0 |
| edges missing `evidenced_by` | must be 0 |

## 9. Known limits

- **Straw-man risk stays high.** Whether a paper's criticism of prior work is fair cannot be automated.
- **Over-merging is the twin risk of fragmentation.** Merging two distinct problems to connect the graph
  yields a plausible-looking but false gap table. Merges need human confirmation, a log, and the old id
  kept as an alias.
- **A small graph is legitimately sparse.** The goal is no orphans and full evidence, not density.
- **Below ~30 papers there is not enough signal** for G1 (which needs three independent mentions).
- **Paper↔code alignment has no reliable automated solution** in the literature; anchoring on
  hyperparameters, module names and metric keys works, inference does not. Any inferred mapping is
  labelled as such.

## 10. What "done" looks like

- any conclusion can be pointed at a page, table or line
- no paper is read twice; no problem becomes two nodes
- the gap table eventually contains one entry that survives the question *"has nobody really done this?"*
