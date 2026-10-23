"""readproof — a research assistant that refuses to pretend it read something."""

__version__ = "0.4.0"

from .states import (  # noqa: F401
    ARTEFACTS,
    EXIT_ILLEGAL_TRANSITION,
    FETCH_FAILED,
    FETCHED,
    IllegalTransition,
    MANUAL_UPLOAD,
    PIPELINE,
    READ_FULL,
    READ_PARTIAL,
    RECEIPT_FIELDS,
    STATES,
    UNREAD,
    VERIFIED,
    can_write,
    check_transition,
    may_promote_to_read_full,
    missing_receipt_fields,
    next_states,
    receipt_is_complete,
)

__all__ = [
    "__version__",
    "ARTEFACTS",
    "EXIT_ILLEGAL_TRANSITION",
    "FETCH_FAILED",
    "FETCHED",
    "IllegalTransition",
    "MANUAL_UPLOAD",
    "PIPELINE",
    "READ_FULL",
    "READ_PARTIAL",
    "RECEIPT_FIELDS",
    "STATES",
    "UNREAD",
    "VERIFIED",
    "can_write",
    "check_transition",
    "may_promote_to_read_full",
    "missing_receipt_fields",
    "next_states",
    "receipt_is_complete",
]
