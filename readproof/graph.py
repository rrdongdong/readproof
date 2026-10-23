"""Build the problem graph and ask it where nothing has been done.

The graph is deliberately thin: nodes come from the controlled vocabulary, edges come
from problem cards, and every edge carries the paper and location that justify it. An
edge without a location is not evidence, it is a recollection.

The six queries are the point of the whole exercise. They are answered by counting,
not by inference, which is why the output can be checked by hand.
"""

from __future__ import annotations

import os

from . import vocab as vocab_mod

EXIT_GRAPH_UNHEALTHY = vocab_mod.EXIT_GRAPH_UNHEALTHY

#: Relations a card may declare, and what each means.
RELATIONS = {
    "solves": "paper claims to solve this problem",
    "leaves_open": "paper admits this problem remains open",
    "assumes": "paper's method rests on this assumption",
    "admits": "paper admits this limitation of its own method",
    "criticizes": "paper says this method is insufficient",
    "anomaly": "reported result contradicts intuition and is unexplained",
}

THRESHOLDS = {
    # Health is only meaningful once the graph is big enough to be fragmented. Judging
    # a five-node bootstrap graph for orphans produces a failing build on day one, which
    # teaches people to pass --lenient forever.
    "min_nodes_for_health": 10,
    "orphan_ratio": 0.10,
    "triage_ratio": 0.15,
    "max_components": 2,
    "min_aliases_per_term": 1.0,
    "edges_without_loc": 0,
}


class GraphError(Exception):
    exit_code = EXIT_GRAPH_UNHEALTHY


class Edge(object):
    __slots__ = ("paper", "relation", "node", "loc", "compared", "note", "evidence")

    def __init__(self, paper, relation, node, loc="", compared=None, note="", evidence=""):
        self.paper = paper
        self.relation = relation
        self.node = node
        self.loc = loc
        self.compared = compared
        self.note = note
        self.evidence = evidence

    def to_dict(self):
        data = {"paper": self.paper, "relation": self.relation, "node": self.node}
        if self.loc:
            data["loc"] = self.loc
        if self.compared is not None:
            data["compared"] = self.compared
        if self.note:
            data["note"] = self.note
        if self.evidence:
            data["evidence"] = self.evidence
        return data

    def __repr__(self):
        return "<Edge %s %s %s>" % (self.paper, self.relation, self.node)


class Graph(object):
    def __init__(self, vocabulary):
        self.vocabulary = vocabulary
        self.edges = []
        self.triage = []  # (paper, relation, raw phrase)
        self.papers = {}  # paper id -> title

    # -------------------------------------------------------------- building

    def add_edge(self, edge):
        self.edges.append(edge)

    def node_ids(self):
        """Vocabulary nodes only: anomalies are records, not concepts."""
        return sorted(
            {edge.node for edge in self.edges if edge.relation != "anomaly"}
        )

    def anomalies(self):
        return [edge for edge in self.edges if edge.relation == "anomaly"]

    def papers_for(self, node_id, relation=None):
        seen = []
        for edge in self.edges:
            if edge.node != node_id:
                continue
            if relation is not None and edge.relation != relation:
                continue
            if edge.paper not in seen:
                seen.append(edge.paper)
        return seen

    def edges_for(self, node_id, relation=None):
        return [
            edge
            for edge in self.edges
            if edge.node == node_id and (relation is None or edge.relation == relation)
        ]

    def relations_of(self, paper_id):
        return [edge for edge in self.edges if edge.paper == paper_id]

    # ----------------------------------------------------------------- stats

    def stats(self):
        node_ids = self.node_ids()
        referenced = set(node_ids)
        orphan = [n for n in node_ids if len(self.papers_for(n)) < 2]
        total_refs = len(self.edges) - len(self.anomalies()) + len(self.triage)
        no_loc = [edge for edge in self.edges if not edge.loc]
        alias_counts = [
            len(term.aliases) for term in self.vocabulary if term.id in referenced
        ]
        return {
            "papers": len(self.papers),
            "edges": len(self.edges),
            "nodes_referenced": len(node_ids),
            "nodes_in_vocabulary": len(self.vocabulary),
            "triage": len(self.triage),
            "triage_ratio": round(len(self.triage) / total_refs, 4) if total_refs else 0.0,
            "orphans": orphan,
            "orphan_ratio": round(len(orphan) / len(node_ids), 4) if node_ids else 0.0,
            "components": len(self.components()),
            "edges_without_loc": len(no_loc),
            "anomalies": len(self.anomalies()),
            "mean_aliases": round(
                sum(alias_counts) / float(len(alias_counts)), 3
            ) if alias_counts else 0.0,
            "category_blanks": self.vocabulary.category_blank(),
            "health_applies": len(node_ids) >= THRESHOLDS["min_nodes_for_health"],
        }

    def components(self):
        """Connected components over nodes, joined when one paper touches both."""
        parent = {node: node for node in self.node_ids()}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        by_paper = {}
        for edge in self.edges:
            if edge.relation == "anomaly":
                continue
            by_paper.setdefault(edge.paper, set()).add(edge.node)
        for nodes in by_paper.values():
            nodes = sorted(nodes)
            for other in nodes[1:]:
                union(nodes[0], other)

        groups = {}
        for node in parent:
            groups.setdefault(find(node), []).append(node)
        return [sorted(group) for group in groups.values()]

    def health(self, thresholds=None):
        """Check the thresholds; a messy graph must fail, not warn.

        A fragmented graph produces a gap table that is confidently wrong, and nothing
        in the output reveals it. So the build refuses instead.
        """
        limits = dict(THRESHOLDS)
        if thresholds:
            limits.update(thresholds)
        report = self.stats()
        failures = []
        big_enough = report["nodes_referenced"] >= limits["min_nodes_for_health"]
        if big_enough and report["orphan_ratio"] > limits["orphan_ratio"]:
            failures.append(
                "orphan ratio %.2f > %.2f (%d node(s) touched by one paper)"
                % (report["orphan_ratio"], limits["orphan_ratio"], len(report["orphans"]))
            )
        if big_enough and report["triage_ratio"] > limits["triage_ratio"]:
            failures.append(
                "triage ratio %.2f > %.2f (%d unresolved reference(s))"
                % (report["triage_ratio"], limits["triage_ratio"], report["triage"])
            )
        if big_enough and report["components"] > limits["max_components"]:
            failures.append(
                "graph split into %d components (max %d)"
                % (report["components"], limits["max_components"])
            )
        if report["edges_without_loc"] > limits["edges_without_loc"]:
            failures.append(
                "%d edge(s) carry no location; an edge without evidence is a recollection"
                % report["edges_without_loc"]
            )
        if report["mean_aliases"] < limits["min_aliases_per_term"]:
            failures.append(
                "mean aliases per referenced term %.2f < %.2f (vocabulary unused)"
                % (report["mean_aliases"], limits["min_aliases_per_term"])
            )
        return {"ok": not failures, "failures": failures, "stats": report}


def build(ledger, vocabulary, lenient=False):
    """Turn ledger problem cards into a graph.

    Unresolved phrases go to ``graph.triage`` and **not** into the graph. Adding a node
    for every unmatched phrase is exactly how a graph fragments.
    """
    graph = Graph(vocabulary)
    for paper in ledger.papers:
        graph.papers[paper["id"]] = paper.get("title", "")

    for card in ledger.cards:
        paper_id = card.get("paper")
        if paper_id not in graph.papers:
            raise GraphError("card references unknown paper %r" % paper_id)
        for relation in RELATIONS:
            for entry in card.get(relation, []) or []:
                raw = entry.get("node", "") if isinstance(entry, dict) else entry
                loc = entry.get("loc", "") if isinstance(entry, dict) else ""
                if relation == "anomaly":
                    graph.add_edge(
                        Edge(
                            paper_id,
                            "anomaly",
                            raw or "unlabelled-anomaly",
                            loc=loc,
                            note=entry.get("note", "") if isinstance(entry, dict) else "",
                        )
                    )
                    continue
                term = vocabulary.resolve(raw)
                if term is None:
                    if not lenient:
                        graph.triage.append((paper_id, relation, raw))
                        continue
                    graph.triage.append((paper_id, relation, raw))
                    continue
                graph.add_edge(
                    Edge(
                        paper_id,
                        relation,
                        term.id,
                        loc=loc,
                        compared=entry.get("compared") if isinstance(entry, dict) else None,
                        note=entry.get("note", "") if isinstance(entry, dict) else "",
                        evidence=entry.get("evidence", "") if isinstance(entry, dict) else "",
                    )
                )
    return graph


# --------------------------------------------------------------------- queries


def _describe(graph, node_id):
    term = graph.vocabulary.get(node_id)
    return term.name if term else node_id


def query_g1(graph, minimum=3):
    """Consensus gap: several papers say this problem is still open."""
    findings = []
    for node_id in graph.node_ids():
        if not node_id.startswith("P-"):
            continue
        papers = graph.papers_for(node_id, "leaves_open")
        if len(papers) >= minimum:
            findings.append(
                {
                    "kind": "G1",
                    "label": "consensus",
                    "node": node_id,
                    "statement": _describe(graph, node_id),
                    "papers": papers,
                    "evidence": [
                        "%s %s" % (edge.paper, edge.loc)
                        for edge in graph.edges_for(node_id, "leaves_open")
                    ],
                    "meaning": "the field agrees it is unsolved — lowest risk",
                }
            )
    return findings


def query_g2(graph, minimum=2):
    """Silent gap: everyone hits the limitation, nobody claims to solve it."""
    findings = []
    for node_id in graph.node_ids():
        hit_by = graph.papers_for(node_id, "admits")
        solved_by = graph.papers_for(node_id, "solves")
        if len(hit_by) >= minimum and not solved_by:
            findings.append(
                {
                    "kind": "G2",
                    "label": "silent",
                    "node": node_id,
                    "statement": _describe(graph, node_id),
                    "papers": hit_by,
                    "evidence": ["%s %s" % (e.paper, e.loc) for e in graph.edges_for(node_id, "admits")],
                    "meaning": "known to break, nobody fixes it — best effort/reward",
                }
            )
    return findings


def query_g3(graph):
    """Contested gap: criticised, but the criticism was never benchmarked."""
    findings = []
    by_node = {}
    for edge in graph.edges:
        if edge.relation != "criticizes" or edge.compared is not False:
            continue
        by_node.setdefault(edge.node, []).append(edge)
    for node_id, edges in sorted(by_node.items()):
        findings.append(
            {
                "kind": "G3",
                "label": "contested",
                "node": node_id,
                "statement": _describe(graph, node_id),
                "papers": [edge.paper for edge in edges],
                "evidence": [
                    "%s %s (%s)" % (e.paper, e.loc, e.evidence or "E2")
                    for e in edges
                ],
                "meaning": "one experiment would settle it — largest headroom",
            }
        )
    return findings


def query_g4(graph):
    """Assumption gap: two methods rest on contradictory premises."""
    findings = []
    assumptions = [edge for edge in graph.edges if edge.relation == "assumes"]
    assumed_by_paper = {}
    for edge in assumptions:
        assumed_by_paper.setdefault(edge.paper, set()).add(edge.node)

    reported = set()
    for term in graph.vocabulary:
        if term.kind != "Assumption":
            continue
        for other_id in term.excludes:
            other = graph.vocabulary.get(other_id)
            if other is None:
                continue
            pair = tuple(sorted((term.id, other_id)))
            if pair in reported:
                continue
            reported.add(pair)
            left = graph.papers_for(term.id, "assumes")
            right = graph.papers_for(other_id, "assumes")
            if not left or not right:
                continue
            bridged = [
                paper
                for paper in left
                if paper in assumed_by_paper and other_id in assumed_by_paper[paper]
            ]
            if bridged:
                continue
            findings.append(
                {
                    "kind": "G4",
                    "label": "assumption",
                    "node": term.id,
                    "nodes": [term.id, other_id],
                    "statement": "%s  ⟂  %s" % (term.name, other.name),
                    "papers": sorted(set(left) | set(right)),
                    "evidence": [
                        "%s assumes %s" % (edge.paper, edge.node)
                        for edge in assumptions
                        if edge.node in (term.id, other_id)
                    ],
                    "meaning": "nobody crosses the assumption — good fit for a small project",
                }
            )
    return findings


def query_g5(graph):
    """Isolated gap: a single mention and no follow-up. Listed, never recommended."""
    findings = []
    already = set()
    for query in (query_g1, query_g2, query_g3, query_g4):
        for finding in query(graph):
            for node in finding.get("nodes") or [finding["node"]]:
                already.add(node)
    for node_id in graph.node_ids():
        if node_id in already:
            continue
        papers = graph.papers_for(node_id)
        if len(papers) == 1:
            edge = graph.edges_for(node_id)[0]
            findings.append(
                {
                    "kind": "G5",
                    "label": "isolated",
                    "node": node_id,
                    "statement": _describe(graph, node_id),
                    "papers": papers,
                    "evidence": ["%s %s (%s)" % (edge.paper, edge.loc, edge.relation)],
                    "meaning": "may be a non-problem — listed only, needs a human",
                }
            )
    return findings


def query_g6(graph):
    """Anomaly gap: the numbers disagree with the intuition, and nobody explains it."""
    findings = []
    for edge in graph.edges:
        if edge.relation != "anomaly":
            continue
        findings.append(
            {
                "kind": "G6",
                "label": "anomaly",
                "node": edge.node,
                "statement": edge.note or _describe(graph, edge.node),
                "papers": [edge.paper],
                "evidence": ["%s %s" % (edge.paper, edge.loc)],
                "meaning": "mechanism gap — most likely to yield real novelty",
            }
        )
    return findings


QUERIES = {
    "G1": query_g1,
    "G2": query_g2,
    "G3": query_g3,
    "G4": query_g4,
    "G5": query_g5,
    "G6": query_g6,
}


def run_queries(graph, only=None):
    findings = []
    for name, query in sorted(QUERIES.items()):
        if only and name not in only:
            continue
        findings.extend(query(graph))
    return findings


def gap_table(findings, stats=None):
    """Render the gap table.

    Problem statements and evidence only. No "innovation ideas": a generated novelty is
    worthless without knowing the hardware, the data and the advisor, and presenting one
    as your own is an integrity problem rather than a feature.
    """
    lines = ["# Gap candidates", ""]
    if stats:
        lines.append(
            "Built from %d paper(s), %d edge(s), %d node(s); triage %d, orphans %d, "
            "components %d."
            % (
                stats["papers"],
                stats["edges"],
                stats["nodes_referenced"],
                stats["triage"],
                len(stats["orphans"]),
                stats["components"],
            )
        )
        if stats["category_blanks"]:
            lines.append("")
            lines.append("Empty categories: %s" % ", ".join(stats["category_blanks"]))
        lines.append("")
    if not findings:
        lines.append("No gaps found. With a small graph that is the expected answer —")
        lines.append("the queries need overlapping mentions across papers.")
        lines.append("")
        return "\n".join(lines)

    order = {"G1": 0, "G3": 1, "G4": 2, "G2": 3, "G6": 4, "G5": 5}
    findings = sorted(findings, key=lambda f: (order.get(f["kind"], 9), f["node"]))
    for index, finding in enumerate(findings, start=1):
        lines.append("## G-%02d [%s %s] %s" % (index, finding["kind"], finding["label"], finding["statement"]))
        lines.append("")
        nodes = finding.get("nodes") or [finding["node"]]
        lines.append(
            "Node: %s  ·  papers: %s"
            % (", ".join("`%s`" % n for n in nodes), ", ".join(finding["papers"]))
        )
        lines.append("")
        lines.append("Evidence:")
        for item in finding["evidence"]:
            lines.append("- %s" % item)
        lines.append("")
        lines.append("Meaning: %s" % finding["meaning"])
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("A gap is a question, not an idea. Before treating one as yours, answer:")
    lines.append("")
    lines.append("1. Which assumption of this problem can you falsify?")
    lines.append("2. If you may change exactly one variable, which one?")
    lines.append("3. What is the smallest experiment that produces a number in one day?")
    lines.append("4. If the result is negative, is the work still worth reporting?")
    lines.append("5. What about your data or hardware makes this answerable by you and not others?")
    lines.append("")
    return "\n".join(lines)


def write_outputs(graph, findings, directory):
    """Write ``gap-table.md`` and ``graph.json`` (derived files; never hand-edited)."""
    if not os.path.isdir(directory):
        raise GraphError("output directory does not exist: %s" % directory)
    stats = graph.stats()
    table_path = os.path.join(directory, "gap-table.md")
    with open(table_path, "w", encoding="utf-8") as handle:
        handle.write(gap_table(findings, stats))

    json_path = os.path.join(directory, "graph.json")
    import json

    payload = {
        "nodes": [
            dict(term.to_dict(), referenced=term.id in graph.node_ids())
            for term in graph.vocabulary
        ],
        "edges": [edge.to_dict() for edge in graph.edges],
        "triage": [
            {"paper": paper, "relation": relation, "phrase": phrase}
            for paper, relation, phrase in graph.triage
        ],
        "findings": findings,
        "stats": stats,
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return table_path, json_path
