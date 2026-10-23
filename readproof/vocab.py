"""The controlled vocabulary that keeps the problem graph connected.

Free-text problem names are what break a knowledge graph: one concept becomes four
nodes ("bandwidth bottleneck" / "uplink saturation" / "通信开销大"), the graph turns
into a cloud of disconnected points, and every gap query returns nothing.

So nodes are only ever created here, from a file a human edits, and the build step
never invents a canonical id. An unmatched reference goes to the triage pool instead —
better a missing edge than a duplicate node.

Id format: ``<KIND>-<CATEGORY>-<NN>``

    KIND      P problem  ·  L limitation  ·  A assumption  ·  M method
    CATEGORY  SCALE  ROBUST  ASSUME  THEORY  EVAL  ENGINEER

The six categories are the skeleton of "what is still unsolved": every category with
nothing in it is a visible blank rather than a silent gap.
"""

from __future__ import annotations

import difflib
import re

EXIT_GRAPH_UNHEALTHY = 4

KINDS = {"P": "Problem", "L": "Limitation", "A": "Assumption", "M": "Method"}
CATEGORIES = ("SCALE", "ROBUST", "ASSUME", "THEORY", "EVAL", "ENGINEER")

ID_PATTERN = re.compile(r"^(?P<kind>[PLAM])-(?P<category>[A-Z]+)-(?P<number>\d{2})$")

COLUMNS = ("id", "name", "kind", "aliases", "parent", "excludes")


class VocabError(Exception):
    """The vocabulary file is malformed or internally inconsistent."""

    exit_code = EXIT_GRAPH_UNHEALTHY


def normalize(text):
    """Fold a phrase for alias comparison: case, punctuation and spacing ignored."""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


class Term(object):
    """One canonical node."""

    __slots__ = ("id", "name", "kind", "aliases", "parent", "excludes", "line")

    def __init__(self, id, name, kind, aliases, parent, excludes, line=0):
        self.id = id
        self.name = name
        self.kind = kind
        self.aliases = aliases
        self.parent = parent
        self.excludes = excludes
        self.line = line

    @property
    def category(self):
        return self.parent.split("-")[1] if "-" in self.parent else self.parent

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "aliases": list(self.aliases),
            "parent": self.parent,
            "excludes": list(self.excludes),
        }

    def __repr__(self):
        return "<Term %s %s>" % (self.id, self.name)


class Vocabulary(object):
    """Parsed, validated vocabulary with alias resolution."""

    def __init__(self, terms, source=""):
        self.terms = terms
        self.source = source
        self._by_id = {term.id: term for term in terms}
        # Longest alias first: "uplink saturation ratio" must beat "uplink".
        pairs = []
        for term in terms:
            pairs.append((normalize(term.name), term))
            for alias in term.aliases:
                pairs.append((normalize(alias), term))
        self._by_phrase = {}
        for phrase, term in sorted(pairs, key=lambda item: len(item[0]), reverse=True):
            if phrase and phrase not in self._by_phrase:
                self._by_phrase[phrase] = term

    # ---------------------------------------------------------------- loading

    @classmethod
    def from_text(cls, text, source=""):
        terms = []
        errors = []
        for number, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = [field.strip() for field in line.split("\t")]
            if fields and fields[0].lower() == "id":
                continue  # header row
            if len(fields) < 5:
                errors.append("line %d: expected 5+ tab-separated columns, got %d" % (number, len(fields)))
                continue
            while len(fields) < len(COLUMNS):
                fields.append("")
            identifier, name, kind, aliases, parent, excludes = fields[:6]
            aliases = [a.strip() for a in aliases.split("|") if a.strip()]
            excludes = [e.strip() for e in excludes.replace(";", "|").split("|") if e.strip()]
            terms.append(Term(identifier, name, kind, aliases, parent, excludes, number))
        if errors:
            raise VocabError("; ".join(errors))
        vocabulary = cls(terms, source=source)
        vocabulary.validate()
        return vocabulary

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as handle:
            return cls.from_text(handle.read(), source=path)

    # ------------------------------------------------------------- validation

    def validate(self):
        """Fail on anything that would silently fork one concept into two nodes."""
        problems = []
        seen_ids = {}
        seen_names = {}
        seen_aliases = {}

        for term in self.terms:
            match = ID_PATTERN.match(term.id)
            if not match:
                problems.append(
                    "line %d: id %r must look like P-SCALE-01" % (term.line, term.id)
                )
                continue
            category = match.group("category")
            if category not in CATEGORIES:
                problems.append(
                    "line %d: unknown category %r (allowed: %s)"
                    % (term.line, category, ", ".join(CATEGORIES))
                )
            expected_kind = KINDS[match.group("kind")]
            if term.kind != expected_kind:
                problems.append(
                    "line %d: id prefix says %s but kind says %r"
                    % (term.line, expected_kind, term.kind)
                )
            expected_parent = "%s-%s" % (match.group("kind"), category)
            if term.parent != expected_parent:
                problems.append(
                    "line %d: parent %r should be %r to match the id"
                    % (term.line, term.parent, expected_parent)
                )
            if not term.name.strip():
                problems.append("line %d: empty name" % term.line)

            if term.id in seen_ids:
                problems.append(
                    "line %d: duplicate id %r (first at line %d)"
                    % (term.line, term.id, seen_ids[term.id])
                )
            seen_ids[term.id] = term.line

            folded = normalize(term.name)
            if folded in seen_names and seen_names[folded] != term.id:
                problems.append(
                    "line %d: name %r duplicates %s — one concept, two ids"
                    % (term.line, term.name, seen_names[folded])
                )
            seen_names[folded] = term.id

            for phrase in [term.name] + term.aliases:
                key = normalize(phrase)
                if not key:
                    problems.append("line %d: blank alias" % term.line)
                    continue
                owner = seen_aliases.get(key)
                if owner is not None and owner != term.id:
                    problems.append(
                        "line %d: phrase %r already belongs to %s" % (term.line, phrase, owner)
                    )
                seen_aliases[key] = term.id

        for term in self.terms:
            for other in term.excludes:
                if other not in seen_ids:
                    problems.append(
                        "line %d: %s excludes unknown id %r" % (term.line, term.id, other)
                    )
                elif other == term.id:
                    problems.append("line %d: %s excludes itself" % (term.line, term.id))

        if problems:
            raise VocabError("\n".join(problems))
        return True

    # --------------------------------------------------------------- resolving

    def get(self, identifier):
        return self._by_id.get(identifier)

    def __len__(self):
        return len(self.terms)

    def __iter__(self):
        return iter(self.terms)

    def resolve(self, text):
        """Map an arbitrary phrase to a canonical term, or ``None``.

        Never invents a term: an unresolved phrase belongs in the triage pool, where a
        human decides whether it is a new concept or a worse name for an existing one.
        """
        if not text:
            return None
        if text in self._by_id:
            return self._by_id[text]
        key = normalize(text)
        if key in self._by_phrase:
            return self._by_phrase[key]
        return None

    def suggestions(self, text, limit=3, cutoff=0.5):
        """Candidates for the triage pool.

        Character similarity, not substring: triage entries are usually a slightly
        different wording of an existing concept ("uplink bandwith"), and substring
        matching finds none of those.
        """
        key = normalize(text)
        if not key:
            return []
        scored = []
        for phrase, term in self._by_phrase.items():
            ratio = difflib.SequenceMatcher(None, key, phrase).ratio()
            if ratio >= cutoff or key in phrase or phrase in key:
                scored.append((ratio, term))
        scored.sort(key=lambda item: item[0], reverse=True)
        out = []
        for _, term in scored:
            if term.id not in [t.id for t in out]:
                out.append(term)
            if len(out) >= limit:
                break
        return out

    def by_kind(self, kind):
        return [term for term in self.terms if term.kind == kind]

    def category_blank(self):
        """Categories with no canonical term yet — the visible blanks."""
        filled = set()
        for term in self.terms:
            if term.kind == "Problem":
                filled.add(term.category)
        return [category for category in CATEGORIES if category not in filled]
