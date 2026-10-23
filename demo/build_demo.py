#!/usr/bin/env python3
"""Build the demo ledger, the demo graph and the demo gap table.

Everything here is synthetic. The papers are the fixtures from the test suite, and the
vocabulary is a generic one, so the demo can live in a public repository without
publishing anybody's reading list or research direction.

Run it from anywhere:

    python demo/build_demo.py
    python demo/build_demo.py --serve        # build, then serve http://127.0.0.1:8010

The output is committed on purpose (``demo/ledger.json``, ``demo/gap-table.md``,
``demo/graph.json``) so that a fresh clone can start the UI without running anything
first. Re-running this script regenerates them; the ledger's timestamps will change.
"""

import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
LEDGER = os.path.join(HERE, "ledger.json")
VOCAB = os.path.join(HERE, "vocab.tsv")
WEB_DIR = os.path.join(ROOT, "web", "dist")

#: Fixed clock. The ledger's history records timestamps, so without this the committed
#: demo files would change on every run and `git pull` would hit a conflict after any
#: demo. Reproducible output is also what lets CI assert `git diff --exit-code demo/`.
PINNED_NOW = "2026-01-01T00:00:00+00:00"

PAPERS = [
    ("07", "[synthetic] Dense Reconstruction of Degraded Scenes", "CVPR 2026 (fixture)"),
    ("08", "[synthetic] Short Excerpt Without A Receipt", ""),
    ("09", "[synthetic] Paywalled Paper Waiting For Upload", ""),
    ("10", "[synthetic] Second Excerpt, Same Open Question", ""),
    ("11", "[synthetic] Not Read Yet", ""),
]


def cli(*args, expect=(0,)):
    """Run the readproof CLI against the demo ledger."""
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env["READPROOF_NOW"] = PINNED_NOW
    command = [sys.executable, "-m", "readproof", "--ledger", LEDGER] + list(args)
    # readproof writes UTF-8 by design; decoding with the Windows locale (cp936) would
    # fail on the same symbols that used to break encoding.
    result = subprocess.run(
        command, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode not in expect:
        sys.stderr.write("command failed (%d): %s\n%s%s\n"
                         % (result.returncode, " ".join(args), result.stdout, result.stderr))
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def add_paper(paper_id, title, venue=""):
    args = ["add", paper_id, "--title", title]
    if venue:
        args += ["--venue", venue]
    return cli(*args)


def build():
    if os.path.exists(LEDGER):
        os.unlink(LEDGER)

    cli("init")

    # 1. the full path: fetch → read → verify → a problem card
    add_paper(*PAPERS[0])
    cli("intake", "07", os.path.join(FIXTURES, "valid.pdf"))
    cli("receipt", "07", "--from-text", os.path.join(FIXTURES, "full_paper.txt"))
    cli("advance", "07", "READ_FULL")
    cli("advance", "07", "VERIFIED")

    # 2. a partial read: the state that exists so "three of fifteen pages" can be reported
    add_paper(*PAPERS[1])
    cli("advance", "08", "FETCHED")
    cli("advance", "08", "READ_PARTIAL")
    cli("card", "08",
        "--leaves-open", "P-EVAL-01@sec III",
        "--admits", "L-ENGINEER-01@sec IV",
        "--admits", "L-EVAL-01@sec IV",
        "--assumes", "A-ASSUME-02@sec III")

    # 3. a failed fetch: the upload queue (no card — nothing has been read)
    add_paper(*PAPERS[2])
    cli("advance", "09", "FETCH_FAILED")

    # 4. a second partial read, so the demo can show a consensus gap (G1 needs three)
    add_paper(*PAPERS[3])
    cli("advance", "10", "FETCHED")
    cli("advance", "10", "READ_PARTIAL")
    cli("card", "10",
        "--leaves-open", "P-EVAL-01@sec V",
        "--admits", "L-EVAL-01@sec IV")

    # 5. untouched
    add_paper(*PAPERS[4])

    # a criticism that was never benchmarked (G3) and an unexplained number (G6)
    cli("card", "07",
        "--solves", "P-SCALE-01@sec III-A",
        "--leaves-open", "P-EVAL-01@sec V-D",
        "--admits", "L-ENGINEER-01@sec V-C",
        "--assumes", "A-ASSUME-01@sec III-A",
        "--criticizes-uncompared", "M-SCALE-01@sec II-A",
        "--anomaly", "sec V Table 4=accuracy rises while cost falls, unexplained")

    print(cli("list"))
    print()
    print(cli("graph", "build", "--vocab", VOCAB, "-o", HERE, "--lenient"))
    return 0


def serve():
    if not os.path.isdir(WEB_DIR):
        sys.stderr.write(
            "web/dist is missing — run:\n  cd web && npm install && npm run build\n"
        )
        return 10
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env["READPROOF_NOW"] = PINNED_NOW
    command = [
        sys.executable, "-m", "readproof", "--ledger", LEDGER, "serve",
        "--port", "8010", "--vocab", VOCAB, "--web-dir", WEB_DIR,
    ]
    print("serving http://127.0.0.1:8010  (Ctrl-C to stop)")
    return subprocess.call(command, env=env)


def _utf8_streams():
    """The demo prints gap tables, which contain symbols a cp936 pipe cannot encode."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main():
    _utf8_streams()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serve", action="store_true", help="serve the UI after building")
    args = parser.parse_args()

    code = build()
    if code:
        return code
    if args.serve:
        return serve()
    print("\nnext:  python -m readproof --ledger demo/ledger.json serve \\")
    print("         --port 8010 --vocab demo/vocab.tsv --web-dir web/dist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
