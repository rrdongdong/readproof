"""Command line interface.

Everything the agent does to a paper's state goes through here, so the gates are
enforced in one place whether a human or a skill is driving.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import pdf as pdf_mod
from . import receipt as receipt_mod
from . import sources as sources_mod
from . import states
from .store import (
    DEFAULT_FILENAME,
    Ledger,
    LedgerError,
)

EXIT_USAGE = 64

EPILOG = """\
exit codes
  0   ok
  1   generic error (unknown paper, bad ledger, bad input)
  2   duplicate paper (blocked, not merged)
  5   illegal state transition
  6   incomplete reading receipt
  7   no PDF text extractor available
  8   PDF failed integrity checks (truncated / not a PDF)
  9   manual upload does not match the ledger title

examples
  readproof init
  readproof add 07 --title "A Paper Title" --venue "CVPR 2026" --arxiv 2601.00001
  readproof advance 07 FETCHED
  readproof advance 07 READ_FULL                    # blocked without a receipt
  readproof receipt 07 --file receipt.json
  readproof advance 07 READ_FULL
  readproof receipt 08 --number "Table II: 41.2 dB (p.5)" \\
      --hyper "lr=2e-4 (sec IV-A, p.4)" \\
      --negative "we do not report motion blur (sec V-D, p.7)" \\
      --body "cosine schedule only in a p.3 footnote"
"""


def build_parser():
    parser = argparse.ArgumentParser(
        prog="readproof",
        description="A research assistant that refuses to pretend it read something.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ledger",
        default=os.environ.get("READPROOF_LEDGER", DEFAULT_FILENAME),
        help="ledger file (default: $READPROOF_LEDGER or ./%s)" % DEFAULT_FILENAME,
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", metavar="command")

    sub.add_parser("init", help="create an empty ledger")
    sub.add_parser("demo", help="show the state machine")

    add = sub.add_parser("add", help="register a paper at UNREAD")
    add.add_argument("paper_id")
    add.add_argument("--title", required=True)
    add.add_argument("--venue", default="")
    add.add_argument("--arxiv", default="")
    add.add_argument("--doi", default="")

    adv = sub.add_parser("advance", help="move a paper to another state")
    adv.add_argument("paper_id")
    adv.add_argument("state", choices=list(states.STATES))
    adv.add_argument(
        "--via",
        default=states.PIPELINE,
        choices=list(states.SOURCES),
        help="how the file was obtained",
    )

    rec = sub.add_parser("receipt", help="attach a reading receipt to a paper")
    rec.add_argument("paper_id")
    rec.add_argument("--file", help="JSON file with the four fingerprints")
    rec.add_argument(
        "--from-text",
        metavar="TXT",
        help="extracted paper text (form-feed page breaks); fingerprints are found for you",
    )
    rec.add_argument(
        "--from-pdf",
        metavar="PDF",
        help="a PDF; text is extracted with an installed extractor, then fingerprinted",
    )
    rec.add_argument(
        "--allow-partial",
        action="store_true",
        help="accept text that does not look like a full paper (records the verdict)",
    )
    rec.add_argument("--number", help="number_with_locator: value + table + page")
    rec.add_argument("--hyper", help="hyperparameters: values + section")
    rec.add_argument("--negative", help="negative_quote: a verbatim limitation")
    rec.add_argument("--body", help="body_detail: a non-conclusory body detail")

    chk = sub.add_parser("check", help="validate a receipt JSON without touching the ledger")
    chk.add_argument("--file", required=True)

    ext = sub.add_parser(
        "extract", help="show what a receipt would contain, without storing it"
    )
    ext.add_argument("text_file", help="extracted text, or a PDF to extract from")
    ext.add_argument(
        "--allow-partial",
        action="store_true",
        help="do not refuse text that looks abstract-only or partial",
    )

    intk = sub.add_parser(
        "intake", help="accept a manually supplied PDF or URL and stop at FETCHED"
    )
    intk.add_argument("paper_id")
    intk.add_argument("source", help="local PDF path or http(s) URL")
    intk.add_argument("--title", help="register the paper if the id is unknown")
    intk.add_argument(
        "--accept-mismatch",
        action="store_true",
        help="proceed even if the first pages do not look like the ledger title",
    )

    sta = sub.add_parser("status", help="show one paper")
    sta.add_argument("paper_id")

    lst = sub.add_parser("list", help="list papers")
    lst.add_argument("--state", choices=list(states.STATES))

    return parser


def emit(payload, as_json, text=None):
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text if text is not None else json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_init(args):
    ledger = Ledger.open(args.ledger, create=True)
    if os.path.exists(ledger.path) and ledger.papers:
        raise LedgerError("ledger already exists and is not empty: %s" % ledger.path)
    path = ledger.save()
    emit({"ledger": path, "papers": 0}, args.json, "created %s" % path)
    return 0


def cmd_demo(args):
    rows = []
    for state in states.STATES:
        artefact = [a for a in states.ARTEFACTS if states.can_write(state, a)]
        rows.append(
            {
                "state": state,
                "next": list(states.next_states(state)),
                "may_write": artefact,
            }
        )
    if args.json:
        emit({"states": rows, "receipt_fields": list(states.RECEIPT_FIELDS)}, True)
        return 0
    width = max(len(r["state"]) for r in rows)
    print("%-*s  %-34s  %s" % (width, "state", "next (via pipeline)", "may write"))
    print("%s  %s  %s" % ("-" * width, "-" * 34, "-" * 34))
    for row in rows:
        print(
            "%-*s  %-34s  %s"
            % (
                width,
                row["state"],
                ", ".join(row["next"]) or "(terminal)",
                ", ".join(row["may_write"]) or "-",
            )
        )
    print("\nmanual upload may only reach: %s" % states.FETCHED)
    print("receipt needs: %s" % ", ".join(states.RECEIPT_FIELDS))
    return 0


def cmd_add(args):
    ledger = Ledger.open(args.ledger, create=True)
    paper = ledger.add(
        args.paper_id,
        args.title,
        venue=args.venue,
        arxiv=args.arxiv,
        doi=args.doi,
    )
    ledger.save()
    emit(
        {"id": paper["id"], "state": paper["state"], "ledger": ledger.path},
        args.json,
        "%s added at %s" % (paper["id"], paper["state"]),
    )
    return 0


def cmd_advance(args):
    ledger = Ledger.open(args.ledger)
    paper = ledger.advance(args.paper_id, args.state, via=args.via)
    ledger.save()
    emit(
        {"id": paper["id"], "state": paper["state"], "via": args.via},
        args.json,
        "%s -> %s" % (paper["id"], paper["state"]),
    )
    return 0


def _text_from_pdf(path):
    """Extract text from a PDF, or explain precisely why that is not possible."""
    text, meta = sources_mod.extract_text(path)
    return text, meta


def _maybe_pdf_text(path):
    """Auto-detect: a PDF goes through an extractor, anything else is already text."""
    with open(path, "rb") as handle:
        head = handle.read(5)
    if head.startswith(pdf_mod.MAGIC):
        return _text_from_pdf(path)
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read(), {"extractor": "plain-text", "chars": None, "pages": None}


def _receipt_payload(args):
    if getattr(args, "from_pdf", None):
        text, meta = _text_from_pdf(args.from_pdf)
        payload, _ = receipt_mod.extract_receipt(
            text, require_full=not getattr(args, "allow_partial", False)
        )
        payload.setdefault("extra", {}).update(
            {"extractor": meta["extractor"], "source_pdf_chars": meta["chars"]}
        )
        return payload
    if getattr(args, "from_text", None):
        with open(args.from_text, encoding="utf-8") as handle:
            text = handle.read()
        payload, assessment = receipt_mod.extract_receipt(
            text, require_full=not getattr(args, "allow_partial", False)
        )
        return payload
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            return json.load(handle)
    return {
        "number_with_locator": args.number or "",
        "hyperparameters": args.hyper or "",
        "negative_quote": args.negative or "",
        "body_detail": args.body or "",
    }


def cmd_receipt(args):
    receipt = _receipt_payload(args)
    ledger = Ledger.open(args.ledger)
    stored = ledger.set_receipt(args.paper_id, receipt)
    ledger.save()
    emit(
        {"id": args.paper_id, "receipt": stored},
        args.json,
        "receipt stored for %s (%d fingerprints)"
        % (args.paper_id, len(states.RECEIPT_FIELDS)),
    )
    return 0


def cmd_check(args):
    with open(args.file, encoding="utf-8") as handle:
        receipt = json.load(handle)
    missing = states.missing_receipt_fields(receipt)
    payload = {
        "complete": not missing,
        "missing": missing,
        "present": [f for f in states.RECEIPT_FIELDS if f not in missing],
    }
    if args.json:
        emit(payload, True)
    else:
        print("complete:", "yes" if payload["complete"] else "no")
        for field in states.RECEIPT_FIELDS:
            mark = "x" if field in missing else "v"
            print("  [%s] %s" % (mark, field))
    return 0 if payload["complete"] else 6


def cmd_extract(args):
    text, meta = _maybe_pdf_text(args.text_file)
    assessment = receipt_mod.assess(text)
    assessment["extractor"] = meta.get("extractor")
    payload = {"assessment": assessment, "receipt": None, "missing": []}
    try:
        found, _ = receipt_mod.extract_receipt(
            text, require_full=not args.allow_partial
        )
        payload["receipt"] = found
    except receipt_mod.ReceiptExtractionError as exc:
        payload["missing"] = exc.missing
        if args.json:
            emit(payload, True)
        else:
            print("verdict : %s" % assessment["verdict"])
            print("  pages : %d" % assessment["pages"])
            print("  chars : %d" % assessment["chars"])
            for reason in assessment["reasons"]:
                print("  why   : %s" % reason)
            print("missing : %s" % ", ".join(exc.missing))
            print("\nnot a full paper -> this text cannot produce a receipt")
        return exc.exit_code

    if args.json:
        emit(payload, True)
        return 0
    print("verdict : %s" % assessment["verdict"])
    print("  pages : %d" % assessment["pages"])
    print("  chars : %d" % assessment["chars"])
    for field in states.RECEIPT_FIELDS:
        print("  [v] %-20s %s" % (field, payload["receipt"][field]))
    return 0


def cmd_intake(args):
    ledger = Ledger.open(args.ledger, create=True)
    paper = ledger.find(args.paper_id)
    if paper is None:
        if not args.title:
            raise LedgerError(
                "unknown paper %s: run `add %s --title ...` first, or pass --title"
                % (args.paper_id, args.paper_id)
            )
        paper = ledger.add(args.paper_id, args.title)
        ledger.save()

    source = args.source
    temporary = None
    if source.lower().startswith(("http://", "https://")):
        import tempfile

        handle, temporary = tempfile.mkstemp(prefix="readproof-", suffix=".pdf")
        os.close(handle)
        pdf_mod.download(source, temporary)
        local_path = temporary
    else:
        local_path = source

    try:
        report = pdf_mod.require_valid(local_path)

        identity = {"checked": False, "ok": None, "detail": "no extractor available"}
        if sources_mod.available() is not None:
            try:
                head_text, meta = _text_from_pdf(local_path)
                ok, detail = pdf_mod.identity_matches(paper.get("title", ""), head_text)
                identity = {
                    "checked": True,
                    "ok": ok,
                    "detail": detail,
                    "extractor": meta["extractor"],
                }
            except (sources_mod.ExtractionFailed, sources_mod.ExtractorUnavailable) as exc:
                identity = {"checked": True, "ok": None, "detail": str(exc)}

        if identity.get("ok") is False and not args.accept_mismatch:
            raise pdf_mod.IdentityMismatch(
                "manual upload does not look like %s (%s); re-run with --accept-mismatch "
                "if you are sure" % (paper.get("title"), identity.get("detail"))
            )

        paper["intake"] = {
            "source": source if source.lower().startswith("http") else os.path.abspath(source),
            "bytes": report["bytes"],
            "sha256": report["sha256"],
            "page_objects": report["page_objects"],
            "identity": identity,
            "accepted_mismatch": bool(args.accept_mismatch),
        }

        current = paper.get("state", states.UNREAD)
        if current in (states.UNREAD, states.FETCH_FAILED):
            ledger.advance(args.paper_id, states.FETCHED, via=states.MANUAL_UPLOAD)
        ledger.save()
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)

    payload = {
        "id": args.paper_id,
        "state": ledger.find(args.paper_id)["state"],
        "sha256": report["sha256"],
        "bytes": report["bytes"],
        "page_objects": report["page_objects"],
        "identity": identity,
    }
    emit(
        payload,
        args.json,
        "intake ok: %s -> %s\n  sha256: %s\n  bytes: %d, %d page object(s)\n  identity: %s"
        % (
            args.paper_id,
            payload["state"],
            report["sha256"][:16] + "...",
            report["bytes"],
            report["page_objects"],
            identity.get("detail"),
        ),
    )
    return 0


def cmd_status(args):
    ledger = Ledger.open(args.ledger)
    paper = ledger.require(args.paper_id)
    if args.json:
        emit(paper, True)
        return 0
    print("%s  %s" % (paper["id"], paper["state"]))
    print("  title   : %s" % paper.get("title"))
    for field in ("venue", "arxiv", "doi"):
        if paper.get(field):
            print("  %-8s: %s" % (field, paper[field]))
    print("  source  : %s" % paper.get("source"))
    allowed = [a for a in states.ARTEFACTS if states.can_write(paper["state"], a)]
    print("  may write: %s" % (", ".join(allowed) or "-"))
    receipt = paper.get("receipt")
    if receipt:
        print("  receipt : complete")
    else:
        print("  receipt : none (cannot become %s)" % states.READ_FULL)
    history = paper.get("history") or []
    if history:
        print("  history :")
        for event in history:
            print(
                "    %s  %s -> %s (%s)"
                % (event.get("at"), event.get("from"), event.get("to"), event.get("via"))
            )
    return 0


def cmd_list(args):
    ledger = Ledger.open(args.ledger)
    papers = [
        paper
        for paper in ledger.papers
        if args.state is None or paper.get("state") == args.state
    ]
    if args.json:
        emit({"count": len(papers), "papers": papers}, True)
        return 0
    if not papers:
        print("(no papers)")
        return 0
    width = max(len(p.get("id", "")) for p in papers)
    for paper in papers:
        print(
            "%-*s  %-14s  %s"
            % (width, paper.get("id"), paper.get("state"), paper.get("title"))
        )
    tally = ledger.counts()
    summary = ", ".join("%s=%d" % (k, v) for k, v in tally.items() if v)
    print("\n%d paper(s): %s" % (len(papers), summary or "none"))
    return 0


COMMANDS = {
    "init": cmd_init,
    "demo": cmd_demo,
    "add": cmd_add,
    "advance": cmd_advance,
    "receipt": cmd_receipt,
    "extract": cmd_extract,
    "intake": cmd_intake,
    "check": cmd_check,
    "status": cmd_status,
    "list": cmd_list,
}


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_USAGE
    handler = COMMANDS[args.command]
    try:
        return handler(args)
    except (
        LedgerError,
        states.IllegalTransition,
        receipt_mod.ReceiptExtractionError,
        pdf_mod.PdfError,
        sources_mod.ExtractorUnavailable,
        sources_mod.ExtractionFailed,
    ) as exc:
        code = getattr(exc, "exit_code", 1)
        print("readproof: %s" % exc, file=sys.stderr)
        return code
    except FileNotFoundError as exc:
        print("readproof: file not found: %s" % exc.filename, file=sys.stderr)
        return 1
    except ValueError as exc:  # bad JSON in --file
        print("readproof: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
