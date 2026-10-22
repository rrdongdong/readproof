"""The paper reading state machine.

Six states. Each state *grants capabilities* — it is not a label. A paper may only
produce the artefacts its state allows, and a state may only advance along the
edges declared here. Jumping is a hard error (exit code 5), never a warning.

Why a state machine at all: the most common failure of an automated reader is
"fake reading" — the full text could not be obtained, so the answer was written
from the abstract and nothing in the system made that visible. Giving "not read
yet" a first-class state removes the incentive to silently upgrade it to "read".
"""

from __future__ import annotations

UNREAD = "UNREAD"
FETCH_FAILED = "FETCH_FAILED"
FETCHED = "FETCHED"
READ_PARTIAL = "READ_PARTIAL"
READ_FULL = "READ_FULL"
VERIFIED = "VERIFIED"

STATES = (UNREAD, FETCH_FAILED, FETCHED, READ_PARTIAL, READ_FULL, VERIFIED)

#: How a file was obtained. Manual upload is a legitimate path — it relaxes *how
#: you obtain the file*, never *what counts as evidence*.
PIPELINE = "pipeline"
MANUAL_UPLOAD = "manual_upload"
SOURCES = (PIPELINE, MANUAL_UPLOAD)

EXIT_ILLEGAL_TRANSITION = 5

_TRANSITIONS = {
    UNREAD: frozenset({FETCHED, FETCH_FAILED}),
    FETCH_FAILED: frozenset({FETCHED}),
    FETCHED: frozenset({READ_PARTIAL, READ_FULL}),
    READ_PARTIAL: frozenset({READ_FULL}),
    READ_FULL: frozenset({VERIFIED}),
    VERIFIED: frozenset(),
}

#: Artefacts a paper may contribute, and the weakest state that permits them.
_ARTEFACT_MIN_STATE = {
    "metadata": FETCHED,
    "abstract_note": READ_PARTIAL,
    "eight_questions": READ_FULL,
    "gap_entry": VERIFIED,
}
ARTEFACTS = tuple(_ARTEFACT_MIN_STATE)

#: Rank along the main chain, used only for capability checks.
_RANK = {
    UNREAD: -1,
    FETCH_FAILED: -1,
    FETCHED: 0,
    READ_PARTIAL: 1,
    READ_FULL: 2,
    VERIFIED: 3,
}

#: The four fingerprints a reading receipt must carry. An abstract cannot supply
#: any of them, which is exactly why requiring them blocks fake reading.
RECEIPT_FIELDS = (
    "number_with_locator",   # concrete number + table/number + page
    "hyperparameters",       # a set of hyperparameters + section
    "negative_quote",        # one negative statement, verbatim
    "body_detail",           # one non-conclusory body detail
)


class IllegalTransition(ValueError):
    """Raised when a state change would let a paper claim more than it earned."""

    exit_code = EXIT_ILLEGAL_TRANSITION

    def __init__(self, current, target, via=PIPELINE, reason=""):
        self.current = current
        self.target = target
        self.via = via
        self.reason = reason
        detail = reason or (
            "allowed from %s: %s"
            % (current, sorted(_TRANSITIONS.get(current, ())) or "nothing (terminal)")
        )
        super().__init__(
            "illegal transition %s -> %s (via %s): %s" % (current, target, via, detail)
        )


def check_transition(current, target, via=PIPELINE):
    """Validate one state change, or raise :class:`IllegalTransition`."""
    if current not in _TRANSITIONS:
        raise IllegalTransition(current, target, via, "unknown current state")
    if target not in STATES:
        raise IllegalTransition(current, target, via, "unknown target state")
    if via not in SOURCES:
        raise IllegalTransition(current, target, via, "unknown source")

    # Manual upload may only ever produce a fetched file. It must not be usable as
    # a shortcut around the reading receipt.
    if via == MANUAL_UPLOAD and target != FETCHED:
        raise IllegalTransition(
            current, target, via, "manual upload may only reach FETCHED"
        )
    if target not in _TRANSITIONS[current]:
        raise IllegalTransition(current, target, via)
    return target


def next_states(current):
    """States reachable from ``current`` via the pipeline."""
    return tuple(sorted(_TRANSITIONS.get(current, ())))


def can_write(state, artefact):
    """Whether a paper in ``state`` may emit ``artefact``."""
    if artefact not in _ARTEFACT_MIN_STATE:
        raise ValueError(
            "unknown artefact %r; known: %s" % (artefact, ", ".join(ARTEFACTS))
        )
    return _RANK.get(state, -1) >= _RANK[_ARTEFACT_MIN_STATE[artefact]]


def missing_receipt_fields(receipt):
    """Return the receipt fingerprints that are absent or blank, in canonical order."""
    if not isinstance(receipt, dict):
        return list(RECEIPT_FIELDS)
    missing = []
    for field in RECEIPT_FIELDS:
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing


def receipt_is_complete(receipt):
    """A receipt is complete only when all four fingerprints are non-blank strings."""
    return not missing_receipt_fields(receipt)


def may_promote_to_read_full(current, receipt):
    """Gate ② + state machine combined: can this paper advance to READ_FULL?

    Coverage is checked by the caller (it comes from the extractor); this function
    covers the state edge and the receipt. Returns ``(allowed, reasons)``.
    """
    reasons = []
    if current not in (FETCHED, READ_PARTIAL):
        reasons.append("state %s cannot advance to %s" % (current, READ_FULL))
    missing = missing_receipt_fields(receipt)
    if missing:
        reasons.append("missing receipt fingerprints: %s" % ", ".join(missing))
    return (not reasons, reasons)
