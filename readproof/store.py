"""JSON-backed paper ledger.

The ledger is the single source of truth for what has been read and how far each
paper got. Reports and the problem graph are derived from it; nothing else holds
reading state.

Duplicates are rejected rather than merged: reading the same paper twice is the
cheapest way to make a literature review look thorough while adding nothing.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone

from . import states

LEDGER_VERSION = 1
DEFAULT_FILENAME = "readproof-ledger.json"

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_DUPLICATE = 2
EXIT_ILLEGAL_TRANSITION = states.EXIT_ILLEGAL_TRANSITION  # 5
EXIT_INCOMPLETE_RECEIPT = 6


class LedgerError(Exception):
    """Base class; every ledger failure carries the process exit code it maps to."""

    exit_code = EXIT_GENERIC


class DuplicatePaper(LedgerError):
    exit_code = EXIT_DUPLICATE


class UnknownPaper(LedgerError):
    exit_code = EXIT_GENERIC


class IncompleteReceipt(LedgerError):
    exit_code = EXIT_INCOMPLETE_RECEIPT


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_title(title):
    """Fold a title to a comparison key; keeps CJK, drops punctuation and case."""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (title or "").lower())


def normalize_identifier(value):
    """Fold an arXiv id or DOI so ``arXiv:2099.00001v2`` and ``2099.00001`` collide."""
    text = (value or "").strip().lower()
    text = re.sub(r"^(arxiv|doi)\s*:\s*", "", text)
    text = re.sub(r"v\d+$", "", text)
    return re.sub(r"[^0-9a-z]+", "", text)


class Ledger:
    """A ledger file plus the operations that keep its invariants."""

    def __init__(self, path, data=None):
        self.path = os.path.abspath(path)
        self.data = data if data is not None else {
            "version": LEDGER_VERSION,
            "papers": [],
            "cards": [],
        }

    # ---------------------------------------------------------------- loading

    @classmethod
    def open(cls, path, create=False):
        path = os.path.abspath(path)
        if not os.path.exists(path):
            if not create:
                raise LedgerError(
                    "ledger not found: %s\nrun `readproof init` first, or pass --ledger"
                    % path
                )
            return cls(path)
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except ValueError as exc:
            raise LedgerError("ledger is not valid JSON: %s (%s)" % (path, exc))
        if not isinstance(data, dict) or not isinstance(data.get("papers"), list):
            raise LedgerError("not a readproof ledger: %s" % path)
        return cls(path, data)

    def save(self):
        """Write atomically: a half-written ledger is worse than a stale one."""
        self.data["version"] = LEDGER_VERSION
        directory = os.path.dirname(self.path) or "."
        if not os.path.isdir(directory):
            raise LedgerError("directory does not exist: %s" % directory)
        fd, tmp = tempfile.mkstemp(prefix=".readproof-ledger-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return self.path

    # ----------------------------------------------------------------- access

    @property
    def papers(self):
        return self.data["papers"]

    @property
    def cards(self):
        return self.data.setdefault("cards", [])

    def find(self, paper_id):
        for paper in self.papers:
            if paper.get("id") == paper_id:
                return paper
        return None

    def require(self, paper_id):
        paper = self.find(paper_id)
        if paper is None:
            known = ", ".join(sorted(p.get("id", "?") for p in self.papers)) or "none"
            raise UnknownPaper("unknown paper id: %s (known: %s)" % (paper_id, known))
        return paper

    # ------------------------------------------------------------------ write

    def add(self, paper_id, title, venue="", arxiv="", doi="", source=states.PIPELINE):
        """Register a paper at UNREAD. Raises DuplicatePaper on any identifying overlap."""
        paper_id = (paper_id or "").strip()
        title = (title or "").strip()
        if not paper_id:
            raise LedgerError("paper id must not be empty")
        if not title:
            raise LedgerError("title must not be empty (it is the dedup key)")

        existing = self.find(paper_id)
        if existing is not None:
            raise DuplicatePaper(
                "paper %s already in the ledger (%s, %s)"
                % (paper_id, existing.get("state"), existing.get("title"))
            )

        folded_title = normalize_title(title)
        for paper in self.papers:
            if normalize_title(paper.get("title")) == folded_title:
                raise DuplicatePaper(
                    "same title already registered as %s: %s"
                    % (paper.get("id"), paper.get("title"))
                )
            for field, value in (("arxiv", arxiv), ("doi", doi)):
                if not value:
                    continue
                mine = normalize_identifier(value)
                theirs = normalize_identifier(paper.get(field))
                if mine and mine == theirs:
                    raise DuplicatePaper(
                        "same %s already registered as %s (%s)"
                        % (field, paper.get("id"), paper.get(field))
                    )

        record = {
            "id": paper_id,
            "title": title,
            "venue": venue,
            "arxiv": arxiv,
            "doi": doi,
            "state": states.UNREAD,
            "source": source,
            "receipt": None,
            "history": [
                {"at": _now(), "from": None, "to": states.UNREAD, "via": source}
            ],
        }
        self.papers.append(record)
        return record

    def advance(self, paper_id, target, via=states.PIPELINE):
        """Move a paper one legal step. Illegal moves raise; READ_FULL needs a receipt."""
        paper = self.require(paper_id)
        current = paper.get("state", states.UNREAD)

        # State edge first: a paper that cannot legally be READ_FULL should hear
        # that, not a complaint about its receipt.
        states.check_transition(current, target, via=via)

        if target == states.READ_FULL:
            missing = states.missing_receipt_fields(paper.get("receipt"))
            if missing:
                raise IncompleteReceipt(
                    "refusing %s -> %s: missing reading-receipt fingerprints: %s"
                    % (current, target, ", ".join(missing))
                )

        paper["state"] = target
        if via != states.PIPELINE:
            paper["source"] = via
        paper.setdefault("history", []).append(
            {"at": _now(), "from": current, "to": target, "via": via}
        )
        return paper

    def set_receipt(self, paper_id, receipt):
        """Store a reading receipt. Incomplete receipts are rejected, not stored."""
        paper = self.require(paper_id)
        if not isinstance(receipt, dict):
            raise LedgerError("receipt must be a JSON object")
        missing = states.missing_receipt_fields(receipt)
        if missing:
            raise IncompleteReceipt(
                "receipt rejected: missing fingerprints: %s" % ", ".join(missing)
            )
        stored = {field: receipt[field].strip() for field in states.RECEIPT_FIELDS}
        extras = {
            key: value
            for key, value in receipt.items()
            if key not in stored and key != "extra"
        }
        if isinstance(receipt.get("extra"), dict):
            extras.update(receipt["extra"])
        if extras:
            stored["extra"] = extras
        paper["receipt"] = stored
        return stored

    # ------------------------------------------------------------------ reads

    def set_card(self, paper_id, card):
        """Attach a problem card to a paper.

        A card is where the graph comes from, so it is validated here: the paper must
        exist, and only known relations are accepted. Whether each entry resolves to a
        vocabulary term is the graph builder's decision, not the store's — an unresolved
        phrase belongs in the triage pool, not in an error.
        """
        from . import graph as graph_mod

        paper = self.require(paper_id)
        # A card is a reading artefact: every entry carries a page and an evidence grade,
        # and neither can exist before some of the text has been read. Recording cards for
        # unread papers is how a graph fills with confident statements about papers nobody
        # opened — so this is a gate, not a warning.
        state = paper.get("state", states.UNREAD)
        if not states.can_write(state, "abstract_note"):
            raise LedgerError(
                "cannot record a problem card for %s in state %s: a card needs at least "
                "%s (advance the paper once you have its text)"
                % (paper_id, state, states.READ_PARTIAL)
            )
        if not isinstance(card, dict):
            raise LedgerError("card must be a JSON object")
        cleaned = {"paper": paper_id}
        for relation, entries in card.items():
            if relation == "paper":
                continue
            if relation not in graph_mod.RELATIONS:
                raise LedgerError(
                    "unknown relation %r; known: %s"
                    % (relation, ", ".join(sorted(graph_mod.RELATIONS)))
                )
            if isinstance(entries, str):
                entries = [entries]
            if not isinstance(entries, list):
                raise LedgerError("relation %r must be a list" % relation)
            normalised = []
            for entry in entries:
                if isinstance(entry, str):
                    normalised.append({"node": entry, "loc": ""})
                elif isinstance(entry, dict):
                    if relation != "anomaly" and not entry.get("node"):
                        raise LedgerError(
                            "relation %r: entry without a node" % relation
                        )
                    normalised.append(dict(entry))
                else:
                    raise LedgerError("relation %r: entries must be strings or objects" % relation)
            if normalised:
                cleaned[relation] = normalised

        self.cards[:] = [c for c in self.cards if c.get("paper") != paper_id]
        self.cards.append(cleaned)
        paper["has_card"] = True
        return cleaned

    def card_for(self, paper_id):
        for card in self.cards:
            if card.get("paper") == paper_id:
                return card
        return None

    def counts(self):
        tally = {state: 0 for state in states.STATES}
        for paper in self.papers:
            state = paper.get("state", states.UNREAD)
            tally[state] = tally.get(state, 0) + 1
        return tally
