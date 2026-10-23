# Gap candidates

Built from 5 paper(s), 12 edge(s), 7 node(s); triage 0, orphans 4, components 1.

Empty categories: ROBUST, ASSUME, THEORY, ENGINEER

## G-01 [G1 consensus] no shared protocol for comparing results

Node: `P-EVAL-01`  ·  papers: 08, 10, 07

Evidence:
- 08 sec III
- 10 sec V
- 07 sec V-D

Meaning: the field agrees it is unsolved — lowest risk

## G-02 [G3 contested] knowledge distillation

Node: `M-SCALE-01`  ·  papers: 07

Evidence:
- 07 sec II-A (E2)

Meaning: one experiment would settle it — largest headroom

## G-03 [G4 assumption] training labels are noise free  ⟂  training labels contain noise

Node: `A-ASSUME-01`, `A-ASSUME-02`  ·  papers: 07, 08

Evidence:
- 08 assumes A-ASSUME-02
- 07 assumes A-ASSUME-01

Meaning: nobody crosses the assumption — good fit for a small project

## G-04 [G2 silent] not real time

Node: `L-ENGINEER-01`  ·  papers: 08, 07

Evidence:
- 08 sec IV
- 07 sec V-C

Meaning: known to break, nobody fixes it — best effort/reward

## G-05 [G2 silent] evaluation on a single dataset only

Node: `L-EVAL-01`  ·  papers: 08, 10

Evidence:
- 08 sec IV
- 10 sec IV

Meaning: known to break, nobody fixes it — best effort/reward

## G-06 [G6 anomaly] accuracy rises while cost falls, unexplained

Node: `unlabelled-anomaly`  ·  papers: 07

Evidence:
- 07 sec V Table 4

Meaning: mechanism gap — most likely to yield real novelty

## G-07 [G5 isolated] cost grows faster than accuracy with model size

Node: `P-SCALE-01`  ·  papers: 07

Evidence:
- 07 sec III-A (solves)

Meaning: may be a non-problem — listed only, needs a human

---

A gap is a question, not an idea. Before treating one as yours, answer:

1. Which assumption of this problem can you falsify?
2. If you may change exactly one variable, which one?
3. What is the smallest experiment that produces a number in one day?
4. If the result is negative, is the work still worth reporting?
5. What about your data or hardware makes this answerable by you and not others?
