"""A small HTTP API over the ledger and the problem graph.

Why stdlib ``http.server`` and not FastAPI: the machine that has to run this has no
``pip``, and adding a web framework would also break the property that makes the
engine testable — that it has no third-party dependencies. The routing here is a
dozen lines; a framework would not earn its keep.

The API only reads. Writing still goes through the CLI, where every gate has an exit
code and can be tested without a socket.
"""

from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import graph as graph_mod
from . import states
from . import vocab as vocab_mod
from .store import Ledger

DEFAULT_PORT = 8000
DEFAULT_WEB_DIR = os.path.join("web", "dist")

EXIT_NO_WEB = 10


class ServeError(Exception):
    exit_code = EXIT_NO_WEB


# --------------------------------------------------------------------- payloads


def receipt_status(paper):
    receipt = paper.get("receipt") or {}
    missing = states.missing_receipt_fields(receipt)
    return {
        "complete": not missing,
        "present": [f for f in states.RECEIPT_FIELDS if f not in missing],
        "missing": missing,
        "total": len(states.RECEIPT_FIELDS),
        "values": {f: receipt.get(f, "") for f in states.RECEIPT_FIELDS},
        "extra": receipt.get("extra", {}),
    }


def paper_summary(ledger, paper):
    return {
        "id": paper.get("id"),
        "title": paper.get("title", ""),
        "state": paper.get("state", states.UNREAD),
        "venue": paper.get("venue", ""),
        "arxiv": paper.get("arxiv", ""),
        "doi": paper.get("doi", ""),
        "source": paper.get("source", ""),
        "receipt": receipt_status(paper),
        "may_write": [
            artefact
            for artefact in states.ARTEFACTS
            if states.can_write(paper.get("state", states.UNREAD), artefact)
        ],
        "has_card": ledger.card_for(paper.get("id")) is not None,
        "intake": paper.get("intake"),
    }


def papers_payload(ledger):
    papers = [paper_summary(ledger, paper) for paper in ledger.papers]
    tally = ledger.counts()
    return {
        "count": len(papers),
        "counts": {state: count for state, count in tally.items() if count},
        "papers": papers,
    }


def paper_payload(ledger, paper_id):
    paper = ledger.require(paper_id)
    summary = paper_summary(ledger, paper)
    summary["history"] = paper.get("history", [])
    summary["card"] = ledger.card_for(paper_id)
    return summary


def meta_payload():
    return {
        "state_machine": [
            {
                "state": state,
                "next": list(states.next_states(state)),
                "may_write": [
                    artefact
                    for artefact in states.ARTEFACTS
                    if states.can_write(state, artefact)
                ],
            }
            for state in states.STATES
        ],
        "receipt_fields": list(states.RECEIPT_FIELDS),
        "manual_upload_target": states.FETCHED,
        "exit_codes": {
            "0": "ok",
            "1": "generic error",
            "2": "duplicate paper (blocked)",
            "4": "graph or vocabulary unhealthy",
            "5": "illegal state transition",
            "6": "incomplete reading receipt",
            "7": "no PDF text extractor",
            "8": "PDF failed integrity checks",
            "9": "manual upload does not match the title",
        },
        "gap_types": {
            "G1": "consensus — several papers say it is still open",
            "G2": "silent — everyone hits it, nobody solves it",
            "G3": "contested — criticised but never benchmarked",
            "G4": "assumption — contradictory premises, nobody bridges",
            "G5": "isolated — one mention, may be a non-problem",
            "G6": "anomaly — numbers contradict intuition, unexplained",
        },
    }


def graph_payload(ledger, vocab_path):
    """Gaps and stats, or a stated reason why there are none."""
    if not vocab_path or not os.path.exists(vocab_path):
        return {
            "available": False,
            "reason": "no vocabulary loaded",
            "hint": "pass --vocab vocab.tsv, or create one (the build refuses to invent nodes)",
            "stats": None,
            "health": None,
            "findings": [],
        }
    vocabulary = vocab_mod.Vocabulary.load(vocab_path)
    built = graph_mod.build(ledger, vocabulary)
    health = built.health()
    findings = graph_mod.run_queries(built)
    return {
        "available": True,
        "vocab": vocab_path,
        "stats": health["stats"],
        "health": {"ok": health["ok"], "failures": health["failures"]},
        "findings": findings,
        "triage": [
            {
                "paper": paper,
                "relation": relation,
                "phrase": phrase,
                "suggestions": [t.id for t in vocabulary.suggestions(phrase)],
            }
            for paper, relation, phrase in built.triage
        ],
        "nodes": [term.to_dict() for term in vocabulary],
        "edges": [edge.to_dict() for edge in built.edges],
    }


# ---------------------------------------------------------------------- serving


class Api(object):
    """Route table and the payloads behind it."""

    def __init__(self, ledger_path, vocab_path=None, web_dir=None):
        self.ledger_path = ledger_path
        self.vocab_path = vocab_path
        self.web_dir = web_dir

    def ledger(self):
        return Ledger.open(self.ledger_path)

    def routes(self):
        return [
            ("GET", "/api/health", self.health),
            ("GET", "/api/meta", self.meta),
            ("GET", "/api/papers", self.papers),
            ("GET", "/api/gaps", self.gaps),
        ]

    # ----- handlers

    def health(self, _match, _query):
        return 200, {"ok": True, "ledger": os.path.abspath(self.ledger_path)}

    def meta(self, _match, _query):
        return 200, meta_payload()

    def papers(self, _match, _query):
        return 200, papers_payload(self.ledger())

    def gaps(self, _match, _query):
        return 200, graph_payload(self.ledger(), self.vocab_path)

    # ----- dispatch

    def resolve(self, method, path):
        """Return ``(status, payload)`` for an API path, or ``None`` if not an API path."""
        if not path.startswith("/api/"):
            return None
        for route_method, pattern, handler in self.routes():
            if method != route_method:
                continue
            if pattern.endswith("/{id}"):
                prefix = pattern[: -len("/{id}")]
                if path.startswith(prefix + "/") and len(path) > len(prefix) + 1:
                    return handler(path[len(prefix) + 1 :], {})
            elif path == pattern:
                return handler({}, {})
        if path.startswith("/api/papers/"):
            paper_id = path[len("/api/papers/") :]
            try:
                return 200, paper_payload(self.ledger(), paper_id)
            except Exception as exc:  # unknown paper
                return 404, {"error": str(exc)}
        return 404, {"error": "no such endpoint: %s" % path}


class Handler(BaseHTTPRequestHandler):
    server_version = "readproof"
    api = None  # set by serve()

    def log_message(self, fmt, *args):  # quieter than the default
        pass

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802 - required name
        parsed = urllib.parse.urlsplit(self.path)
        path = posixpath.normpath(urllib.parse.unquote(parsed.path))

        result = self.api.resolve("GET", path)
        if result is not None:
            status, payload = result
            self._send_json(status, payload)
            return

        if path == "/api" or path == "/api/":
            self._send_json(200, {"endpoints": [r[1] for r in self.api.routes()]})
            return

        self._serve_static(path)

    def _serve_static(self, path):
        web_dir = self.api.web_dir
        if not web_dir or not os.path.isdir(web_dir):
            self._send_json(
                503,
                {
                    "error": "no built frontend found",
                    "hint": "run `npm install && npm run build` in web/, or start with --web-dir",
                },
            )
            return
        relative = path.lstrip("/") or "index.html"
        candidate = os.path.abspath(os.path.join(web_dir, relative))
        root = os.path.abspath(web_dir)
        if not candidate.startswith(root):  # no path traversal
            self._send_json(403, {"error": "forbidden"})
            return
        if not os.path.isfile(candidate):
            candidate = os.path.join(root, "index.html")  # SPA fallback
            if not os.path.isfile(candidate):
                self._send_json(404, {"error": "not found: %s" % path})
                return
        content_type = mimetypes.guess_type(candidate)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        with open(candidate, "rb") as handle:
            body = handle.read()
        self._send(200, body, content_type)


def serve(ledger_path, vocab_path=None, web_dir=None, host="127.0.0.1", port=DEFAULT_PORT):
    """Start the server. Returns the ``ThreadingHTTPServer`` so tests can shut it down."""
    if web_dir and not os.path.isdir(web_dir):
        raise ServeError(
            "web directory not found: %s\nrun `npm install && npm run build` in web/"
            % web_dir
        )
    handler = type("BoundHandler", (Handler,), {"api": Api(ledger_path, vocab_path, web_dir)})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd
