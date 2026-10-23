import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from readproof import cli  # noqa: F401  (imported so PYTHONPATH resolution is obvious)
from readproof import states as s
from readproof.store import Ledger

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB = os.path.join(HERE, "fixtures", "vocab.tsv")


class EncodingTests(unittest.TestCase):
    """The CLI must not die because a console cannot encode a glyph.

    On a Chinese Windows install a piped stdout is cp936/GBK, and the gap table contains
    U+27C2. GBK cannot encode it, so `graph build` used to exit 1 with a
    UnicodeEncodeError — a crash caused by one character.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-enc-")
        self.ledger = os.path.join(self.dir, "ledger.json")
        store = Ledger.open(self.ledger, create=True)
        for paper_id in ("01", "02"):
            store.add(paper_id, "Paper %s" % paper_id)
            store.advance(paper_id, s.FETCHED)
            store.advance(paper_id, s.READ_PARTIAL)
        # two contradictory assumptions, so the output contains U+27C2
        store.set_card("01", {"assumes": [{"node": "A-ASSUME-01", "loc": "sec III"}]})
        store.set_card("02", {"assumes": [{"node": "A-ASSUME-02", "loc": "sec III"}]})
        store.save()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_with_encoding(self, encoding, *args):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = encoding
        env["PYTHONPATH"] = os.path.dirname(HERE) + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", "readproof", "--ledger", self.ledger] + list(args),
            env=env,
            capture_output=True,
        )

    def test_graph_build_survives_a_gbk_pipe(self):
        result = self.run_with_encoding("cp936", "graph", "build", "--vocab", VOCAB,
                                        "-o", self.dir, "--lenient")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        output = result.stdout.decode("utf-8", "replace")
        self.assertIn("G4", output)
        self.assertIn("\u27c2", output)  # written as UTF-8, not replaced away

    def test_output_is_utf8_even_on_ascii_console(self):
        result = self.run_with_encoding("ascii", "graph", "query", "--vocab", VOCAB)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        # nothing may be escaped into \uXXXX literals or lost to a traceback
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertTrue(result.stdout.decode("utf-8", "replace").strip())

    def test_unrepresentable_console_does_not_crash(self):
        """errors="replace" is the backstop: a hostile codec still cannot kill the run."""
        result = self.run_with_encoding("cp936:strict", "status", "01")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
