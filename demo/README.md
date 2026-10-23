# demo

A five-paper ledger, a seven-term vocabulary, and the outputs they produce — enough to
look at every screen of the interface without reading a paper first.

**Everything here is synthetic.** The papers are the fixtures from `tests/fixtures/`
(titles start with `[synthetic]`) and the vocabulary is a generic one. That is
deliberate: a demo that mixes invented papers into a real reading ledger is exactly the
kind of thing this project exists to prevent, and a public repository should not publish
anybody's reading list or research direction.

```console
$ python demo/build_demo.py          # regenerate ledger.json, gap-table.md, graph.json
$ python demo/build_demo.py --serve  # …and start http://127.0.0.1:8010
```

## What the demo shows

| Paper | State | Why it is there |
|---|---|---|
| 07 | `VERIFIED` | the full path: fetched → receipt → read → verified, with a four-word receipt |
| 08 | `READ_PARTIAL` | read three pages of fifteen; may write abstract-level notes only |
| 09 | `FETCH_FAILED` | paywalled; waiting for a manual upload, no card because nothing was read |
| 10 | `READ_PARTIAL` | second partial read, so the graph can show a consensus gap |
| 11 | `UNREAD` | nothing known but the title |

The vocabulary is sized so all six gap queries fire:

| Query | Shown by |
|---|---|
| `G1` consensus | three papers leave "no shared protocol" open |
| `G2` silent | two papers admit "not real time", nobody claims to solve it |
| `G3` contested | paper 07 criticises a method it never benchmarks |
| `G4` assumption | "labels are noise free" versus "labels contain noise" |
| `G5` isolated | one paper touches the scaling problem, nobody follows up |
| `G6` anomaly | a table where accuracy rises while cost falls, unexplained |

## Making a demo from your own ledger

Point `build_demo.py` at your own paths, or just run the CLI by hand:

```console
$ readproof init
$ readproof add 01 --title "Your Paper" 
$ readproof advance 01 FETCHED
$ readproof intake 01 paper.pdf                  # or receipt --from-text paper.txt
$ readproof card 01 --leaves-open "P-SCALE-01@sec V-D"
$ readproof graph build --vocab your-vocab.tsv -o out
```

A card needs at least `READ_PARTIAL`: every entry carries a page and an evidence grade,
and neither exists before some of the text has been read.
