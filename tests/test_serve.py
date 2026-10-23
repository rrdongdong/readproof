import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.request

from readproof import serve
from readproof import states as s
from readproof.store import Ledger

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
VOCAB = os.path.join(FIXTURES, "vocab.tsv")


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-serve-")
        self.ledger_path = os.path.join(self.dir, "ledger.json")
        self.ledger = Ledger.open(self.ledger_path, create=True)
        self.ledger.add("01", "First paper about mapping", venue="CVPR 2026")
        self.ledger.add("02", "Second paper about mapping")
        # a card needs text behind it: FETCHED -> READ_PARTIAL is legal without a receipt
        self.ledger.advance("01", s.FETCHED)
        self.ledger.advance("01", s.READ_PARTIAL)
        self.ledger.set_card(
            "01",
            {
                "solves": [{"node": "P-SCALE-01", "loc": "sec III-A"}],
                "leaves_open": [{"node": "P-THEORY-01", "loc": "sec V-D"}],
            },
        )
        self.ledger.save()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def api(self, web_dir=None):
        return serve.Api(self.ledger_path, VOCAB, web_dir)


class PayloadTests(Base):
    def test_papers_payload(self):
        status, payload = self.api().resolve("GET", "/api/papers")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["counts"], {s.READ_PARTIAL: 1, s.UNREAD: 1})
        first = payload["papers"][0]
        self.assertEqual(first["state"], s.READ_PARTIAL)
        self.assertEqual(first["receipt"]["present"], [])
        self.assertEqual(len(first["receipt"]["missing"]), 4)
        self.assertEqual(first["receipt"]["total"], 4)
        self.assertTrue(first["has_card"])
        self.assertIn("metadata", first["may_write"])
        self.assertNotIn("eight_questions", first["may_write"])

    def test_paper_payload_includes_history_and_card(self):
        status, payload = self.api().resolve("GET", "/api/papers/01")
        self.assertEqual(status, 200)
        transitions = [event["to"] for event in payload["history"]]
        self.assertEqual(transitions, [s.UNREAD, s.FETCHED, s.READ_PARTIAL])
        self.assertEqual(payload["card"]["solves"][0]["node"], "P-SCALE-01")

    def test_unknown_paper_is_404(self):
        status, payload = self.api().resolve("GET", "/api/papers/99")
        self.assertEqual(status, 404)
        self.assertIn("unknown paper", payload["error"])

    def test_meta_payload_describes_the_machine(self):
        status, payload = self.api().resolve("GET", "/api/meta")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["state_machine"]), len(s.STATES))
        self.assertEqual(payload["receipt_fields"], list(s.RECEIPT_FIELDS))
        self.assertEqual(payload["manual_upload_target"], s.FETCHED)
        self.assertIn("6", payload["exit_codes"])
        self.assertEqual(sorted(payload["gap_types"]), ["G1", "G2", "G3", "G4", "G5", "G6"])

    def test_gaps_payload_without_vocabulary_states_why(self):
        api = serve.Api(self.ledger_path, None, None)
        status, payload = api.resolve("GET", "/api/gaps")
        self.assertEqual(status, 200)
        self.assertFalse(payload["available"])
        self.assertIn("hint", payload)
        self.assertEqual(payload["findings"], [])

    def test_gaps_payload_with_vocabulary(self):
        status, payload = self.api().resolve("GET", "/api/gaps")
        self.assertEqual(status, 200)
        self.assertTrue(payload["available"])
        self.assertIn("stats", payload)
        self.assertIn("health", payload)
        self.assertIn("findings", payload)
        self.assertEqual(payload["triage"], [])

    def test_unresolved_phrase_lands_in_triage_with_suggestions(self):
        ledger = Ledger.open(self.ledger_path)
        ledger.advance("02", s.FETCHED)
        ledger.advance("02", s.READ_PARTIAL)
        ledger.set_card("02", {"leaves_open": [{"node": "uplink bandwith", "loc": "sec V"}]})
        ledger.save()
        _, payload = self.api().resolve("GET", "/api/gaps")
        self.assertEqual(len(payload["triage"]), 1)
        self.assertIn("P-SCALE-01", payload["triage"][0]["suggestions"])

    def test_health_failure_is_reported_not_hidden(self):
        _, payload = self.api().resolve("GET", "/api/gaps")
        self.assertIn("ok", payload["health"])
        self.assertIn("failures", payload["health"])

    def test_non_api_path_returns_none(self):
        self.assertIsNone(self.api().resolve("GET", "/index.html"))


class HttpTests(Base):
    def setUp(self):
        super().setUp()
        self.web = os.path.join(self.dir, "dist")
        os.makedirs(os.path.join(self.web, "assets"))
        with open(os.path.join(self.web, "index.html"), "w", encoding="utf-8") as handle:
            handle.write("<html><body>readproof</body></html>")
        with open(os.path.join(self.web, "assets", "app.js"), "w", encoding="utf-8") as handle:
            handle.write("console.log('ok')")

        self.httpd = serve.serve(
            ledger_path=self.ledger_path, vocab_path=VOCAB, web_dir=self.web, port=0
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def fetch(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, response.headers.get("Content-Type"), response.read()

    def test_api_over_http(self):
        status, content_type, body = self.fetch("/api/papers")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body)["count"], 2)

    def test_index_is_served(self):
        status, content_type, body = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"readproof", body)

    def test_unknown_path_falls_back_to_index(self):
        status, _, body = self.fetch("/some/spa/route")
        self.assertEqual(status, 200)
        self.assertIn(b"readproof", body)

    def test_asset_is_served_with_javascript_type(self):
        status, content_type, _ = self.fetch("/assets/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", content_type)

    def test_path_traversal_is_refused(self):
        request = urllib.request.Request(self.base + "/../ledger.json")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
        self.assertNotIn(b'"papers"', body)

    def test_missing_frontend_says_how_to_build_it(self):
        httpd = serve.serve(
            ledger_path=self.ledger_path, vocab_path=VOCAB, web_dir=None, port=0
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base = "http://127.0.0.1:%d" % httpd.server_address[1]
            try:
                with urllib.request.urlopen(base + "/", timeout=5) as response:
                    status = response.status
                    body = response.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read()
            self.assertEqual(status, 503)
            self.assertIn(b"npm install", body)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_missing_web_dir_is_refused_at_startup(self):
        with self.assertRaises(serve.ServeError) as ctx:
            serve.serve(
                ledger_path=self.ledger_path,
                vocab_path=VOCAB,
                web_dir=os.path.join(self.dir, "nope"),
                port=0,
            )
        self.assertEqual(ctx.exception.exit_code, 10)


if __name__ == "__main__":
    unittest.main()
