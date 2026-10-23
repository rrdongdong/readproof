import os
import pathlib
import shutil
import tempfile
import unittest

from readproof import cli
from readproof import graph as g
from readproof import states as s
from readproof import vocab as v
from readproof.store import Ledger

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
VOCAB = FIXTURES / "vocab.tsv"


def load_vocab():
    return v.Vocabulary.load(str(VOCAB))


class VocabParsingTests(unittest.TestCase):
    def test_fixture_parses(self):
        vocabulary = load_vocab()
        self.assertEqual(len(vocabulary), 10)
        self.assertEqual(len(vocabulary.by_kind("Problem")), 3)
        self.assertEqual(len(vocabulary.by_kind("Assumption")), 2)

    def test_alias_resolution(self):
        vocabulary = load_vocab()
        self.assertEqual(vocabulary.resolve("P-SCALE-01").id, "P-SCALE-01")
        self.assertEqual(vocabulary.resolve("uplink saturation").id, "P-SCALE-01")
        self.assertEqual(vocabulary.resolve("通信开销大").id, "P-SCALE-01")

    def test_longest_alias_wins(self):
        vocabulary = v.Vocabulary.from_text(
            "P-SCALE-01\tbandwidth\tProblem\tbandwidth\tP-SCALE\t\n"
            "P-SCALE-02\tbandwidth saturation\tProblem\tbandwidth saturation ratio\tP-SCALE\t\n"
        )
        self.assertEqual(vocabulary.resolve("bandwidth saturation ratio").id, "P-SCALE-02")

    def test_unknown_phrase_resolves_to_none(self):
        self.assertIsNone(load_vocab().resolve("a phrase nobody defined"))

    def test_suggestions_are_offered_for_triage(self):
        guesses = load_vocab().suggestions("uplink bandwith")  # typo on purpose
        self.assertTrue(guesses)
        self.assertEqual(guesses[0].id, "P-SCALE-01")

    def test_category_blank_lists_empty_skeleton_slots(self):
        blanks = load_vocab().category_blank()
        self.assertIn("ROBUST", blanks)
        self.assertNotIn("SCALE", blanks)


class VocabValidationTests(unittest.TestCase):
    def expect_error(self, text, fragment):
        with self.assertRaises(v.VocabError) as ctx:
            v.Vocabulary.from_text(text)
        self.assertIn(fragment, str(ctx.exception))
        self.assertEqual(ctx.exception.exit_code, 4)

    def test_kind_must_match_id_prefix(self):
        self.expect_error(
            "P-SCALE-01\tname\tLimitation\ta\tP-SCALE\t\n", "id prefix says Problem"
        )

    def test_unknown_category_rejected(self):
        self.expect_error(
            "P-WHATEVER-01\tname\tProblem\ta\tP-WHATEVER\t\n", "unknown category"
        )

    def test_duplicate_id_rejected(self):
        self.expect_error(
            "P-SCALE-01\ta\tProblem\tx\tP-SCALE\t\n"
            "P-SCALE-01\tb\tProblem\ty\tP-SCALE\t\n",
            "duplicate id",
        )

    def test_same_concept_two_ids_rejected(self):
        self.expect_error(
            "P-SCALE-01\tuplink bandwidth\tProblem\tbw\tP-SCALE\t\n"
            "P-SCALE-02\tUplink Bandwidth!\tProblem\tbw2\tP-SCALE\t\n",
            "one concept, two ids",
        )

    def test_alias_collision_rejected(self):
        self.expect_error(
            "P-SCALE-01\tfirst\tProblem\tshared alias\tP-SCALE\t\n"
            "P-SCALE-02\tsecond\tProblem\tshared alias\tP-SCALE\t\n",
            "already belongs to",
        )

    def test_excludes_must_reference_known_ids(self):
        self.expect_error(
            "A-ASSUME-01\tknown\tAssumption\tk\tA-ASSUME\tA-ASSUME-99\n",
            "excludes unknown id",
        )

    def test_self_exclusion_rejected(self):
        self.expect_error(
            "A-ASSUME-01\tknown\tAssumption\tk\tA-ASSUME\tA-ASSUME-01\n",
            "excludes itself",
        )


class GraphBuildTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-graph-")
        self.path = os.path.join(self.dir, "ledger.json")
        self.ledger = Ledger.open(self.path, create=True)
        for index in ("01", "02", "03", "04"):
            self.ledger.add(index, "Paper %s on multi-robot mapping" % index)
            # a card needs text behind it; READ_PARTIAL is reachable without a receipt
            self.ledger.advance(index, s.FETCHED)
            self.ledger.advance(index, s.READ_PARTIAL)
        self.ledger.set_card(
            "01",
            {
                "solves": [{"node": "P-SCALE-01", "loc": "sec III-A"}],
                "leaves_open": [{"node": "P-THEORY-01", "loc": "sec V-D"}],
                "admits": [{"node": "L-ROBUST-01", "loc": "sec V-C"}],
                "assumes": [{"node": "A-ASSUME-01", "loc": "sec III-A"}],
            },
        )
        self.ledger.set_card(
            "02",
            {
                "solves": [{"node": "P-SCALE-01", "loc": "sec IV"}],
                "leaves_open": [{"node": "P-THEORY-01", "loc": "sec VI"}],
                "admits": [{"node": "L-ROBUST-01", "loc": "sec V-B"}],
                "assumes": [{"node": "A-ASSUME-01", "loc": "sec III"}],
            },
        )
        self.ledger.set_card(
            "03",
            {
                "leaves_open": [{"node": "P-THEORY-01", "loc": "sec V"}],
                "admits": [{"node": "L-ROBUST-01", "loc": "sec IV-D"}],
                "assumes": [{"node": "A-ASSUME-02", "loc": "sec III-B"}],
                "criticizes": [
                    {"node": "M-SCALE-01", "loc": "sec II-A", "compared": False, "evidence": "E2"}
                ],
                "anomaly": [{"loc": "sec V-C Table 4", "note": "more agents, less uplink"}],
            },
        )
        self.ledger.set_card(
            "04",
            {
                "leaves_open": [{"node": "P-SCALE-02", "loc": "sec V"}],
                "admits": [{"node": "L-EVAL-01", "loc": "sec IV"}],
            },
        )
        self.ledger.save()
        self.vocabulary = load_vocab()
        self.graph = g.build(self.ledger, self.vocabulary)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_edges_are_built(self):
        self.assertEqual(len(self.graph.edges), 15)
        self.assertEqual(self.graph.triage, [])

    def test_anomalies_are_not_vocabulary_nodes(self):
        self.assertEqual(len(self.graph.anomalies()), 1)
        self.assertNotIn("unlabelled-anomaly", self.graph.node_ids())
        self.assertEqual(len(self.graph.node_ids()), 8)

    def test_stats_report_the_skeleton_blanks(self):
        stats = self.graph.stats()
        self.assertEqual(stats["papers"], 4)
        self.assertIn("ROBUST", stats["category_blanks"])
        self.assertGreater(stats["mean_aliases"], 1.0)

    def test_unresolved_phrases_go_to_triage_not_the_graph(self):
        self.ledger.set_card(
            "04", {"leaves_open": [{"node": "P-SCALE-99", "loc": "sec V"}]}
        )
        built = g.build(self.ledger, self.vocabulary)
        self.assertEqual(len(built.triage), 1)
        self.assertEqual(built.triage[0][2], "P-SCALE-99")
        self.assertNotIn("P-SCALE-99", built.node_ids())

    def test_health_applies_only_to_large_enough_graphs(self):
        health = self.graph.health()
        self.assertFalse(health["stats"]["health_applies"])
        self.assertTrue(health["ok"], health["failures"])

    def test_health_fails_a_fragmented_graph(self):
        health = self.graph.health({"min_nodes_for_health": 2, "orphan_ratio": 0.10})
        self.assertFalse(health["ok"])
        self.assertTrue(any("orphan ratio" in f for f in health["failures"]))

    def test_edges_without_location_fail_the_health_check(self):
        self.ledger.set_card("04", {"leaves_open": ["P-SCALE-02"]})
        built = g.build(self.ledger, self.vocabulary)
        health = built.health({"min_nodes_for_health": 99})
        self.assertFalse(health["ok"])
        self.assertTrue(any("no location" in f for f in health["failures"]))


class QueryTests(GraphBuildTests):
    def test_g1_consensus_needs_three_papers(self):
        findings = g.query_g1(self.graph)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["node"], "P-THEORY-01")
        self.assertEqual(findings[0]["papers"], ["01", "02", "03"])

    def test_g2_silent_needs_hits_and_no_solver(self):
        findings = g.query_g2(self.graph)
        nodes = [f["node"] for f in findings]
        self.assertIn("L-ROBUST-01", nodes)

    def test_g2_ignores_limitations_with_a_solver(self):
        self.ledger.set_card("04", {"solves": [{"node": "L-ROBUST-01", "loc": "sec IV"}]})
        built = g.build(self.ledger, self.vocabulary)
        self.assertNotIn("L-ROBUST-01", [f["node"] for f in g.query_g2(built)])

    def test_g3_reports_only_unbenchmarked_criticism(self):
        findings = g.query_g3(self.graph)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["node"], "M-SCALE-01")

    def test_g3_ignores_compared_criticism(self):
        """A criticism that was actually benchmarked is settled, not contested."""
        self.ledger.set_card(
            "03",
            {"criticizes": [{"node": "M-SCALE-01", "loc": "sec II", "compared": True}]},
        )
        built = g.build(self.ledger, self.vocabulary)
        self.assertEqual(g.query_g3(built), [])

    def test_g4_reports_one_finding_per_pair(self):
        findings = g.query_g4(self.graph)
        self.assertEqual(len(findings), 1)
        self.assertEqual(sorted(findings[0]["nodes"]), ["A-ASSUME-01", "A-ASSUME-02"])

    def test_g4_silent_when_one_paper_assumes_both(self):
        self.ledger.set_card(
            "04",
            {
                "assumes": [
                    {"node": "A-ASSUME-01", "loc": "sec III"},
                    {"node": "A-ASSUME-02", "loc": "sec IV"},
                ]
            },
        )
        built = g.build(self.ledger, self.vocabulary)
        self.assertEqual(g.query_g4(built), [])

    def test_g5_excludes_nodes_already_reported(self):
        nodes = [f["node"] for f in g.query_g5(self.graph)]
        self.assertNotIn("P-THEORY-01", nodes)
        self.assertNotIn("A-ASSUME-02", nodes)
        self.assertIn("L-EVAL-01", nodes)

    def test_g6_returns_the_anomaly_with_its_location(self):
        findings = g.query_g6(self.graph)
        self.assertEqual(len(findings), 1)
        self.assertIn("more agents", findings[0]["statement"])
        self.assertEqual(findings[0]["evidence"], ["03 sec V-C Table 4"])

    def test_run_queries_can_be_restricted(self):
        findings = g.run_queries(self.graph, only=["G1"])
        self.assertEqual({f["kind"] for f in findings}, {"G1"})


class OutputTests(GraphBuildTests):
    def test_gap_table_contains_no_innovation_ideas(self):
        findings = g.run_queries(self.graph)
        table = g.gap_table(findings, self.graph.stats())
        self.assertIn("G1 consensus", table)
        self.assertIn("A gap is a question, not an idea", table)
        self.assertNotIn("we propose", table.lower())

    def test_outputs_are_written(self):
        findings = g.run_queries(self.graph)
        table_path, json_path = g.write_outputs(self.graph, findings, self.dir)
        self.assertTrue(os.path.exists(table_path))
        self.assertTrue(os.path.exists(json_path))
        import json

        with open(json_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertEqual(payload["stats"]["papers"], 4)
        self.assertTrue(payload["edges"])
        self.assertTrue(payload["findings"])


class CliGraphTests(GraphBuildTests):
    def run_cli(self, *args):
        return cli.main(["--ledger", self.path] + list(args))

    def test_vocab_command(self):
        self.assertEqual(self.run_cli("vocab", "--file", str(VOCAB)), 0)

    def test_vocab_command_rejects_bad_file(self):
        bad = os.path.join(self.dir, "bad.tsv")
        with open(bad, "w", encoding="utf-8") as handle:
            handle.write("P-SCALE-01\tname\tLimitation\ta\tP-SCALE\t\n")
        self.assertEqual(self.run_cli("vocab", "--file", bad), 4)

    def test_graph_stats_and_query(self):
        self.assertEqual(self.run_cli("graph", "stats", "--vocab", str(VOCAB)), 0)
        self.assertEqual(self.run_cli("graph", "query", "--vocab", str(VOCAB)), 0)

    def test_graph_build_writes_outputs(self):
        out = os.path.join(self.dir, "out")
        os.mkdir(out)
        code = self.run_cli("graph", "build", "--vocab", str(VOCAB), "-o", out)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(out, "gap-table.md")))

    def test_graph_check_flags_missing_location(self):
        self.run_cli("card", "04", "--leaves-open", "P-SCALE-02")
        code = self.run_cli("graph", "check", "--vocab", str(VOCAB))
        self.assertEqual(code, 4)

    def test_card_command_rejects_unknown_relation(self):
        path = os.path.join(self.dir, "card.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"villainizes": ["P-SCALE-01"]}')
        self.assertEqual(self.run_cli("card", "04", "--file", path), 1)


if __name__ == "__main__":
    unittest.main()
