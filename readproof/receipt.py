"""Find the four reading-receipt fingerprints in extracted paper text.

This module deliberately does **not** parse PDFs. Text extraction belongs to a real
PDF engine (`dsh-pdf`, which uses pdfjs-dist), because a stdlib parser fails exactly
where it matters: subsetted CID fonts with no ``/ToUnicode`` and pages buried in
``/ObjStm``. Reimplementing that here would produce garbage that looks like text,
which is worse than failing.

So the input is plain text with form-feed (``\\f``) page breaks — what
``pdftotext``, ``dsh-pdf`` and most extractors emit — and the job here is to answer
one question honestly:

    is this a full paper, or is it an abstract someone dressed up as one?

The four fingerprints are chosen because an abstract cannot supply them. If they
cannot be found, the text is not a full paper, and the caller must not be allowed
to claim it read one.
"""

from __future__ import annotations

import re

#: Below this many characters the text cannot be a full paper, whatever it claims.
ABSTRACT_ONLY_MAX_CHARS = 3000

#: A full paper is at least this long and this many pages, with an experiment
#: section and a reference list. Below that we call it partial and say so.
MIN_FULL_CHARS = 12000
MIN_FULL_PAGES = 4

VERDICT_FULL = "full"
VERDICT_PARTIAL = "partial"
VERDICT_ABSTRACT_ONLY = "abstract_only"

PAGE_BREAK = "\f"

#: Words that mark a real hyperparameter statement, mapped to canonical names.
HYPERPARAM_KEYS = {
    "learning rate": "lr",
    "lr": "lr",
    "batch size": "batch",
    "batch": "batch",
    "epochs": "epochs",
    "epoch": "epochs",
    "iterations": "iters",
    "iteration": "iters",
    "iters": "iters",
    "steps": "steps",
    "weight decay": "wd",
    "momentum": "momentum",
    "dropout": "dropout",
    "warmup": "warmup",
    "resolution": "resolution",
    "threshold": "threshold",
    "lambda": "lambda",
    "β": "beta",
    "beta": "beta",
    "λ": "lambda",
    "alpha": "alpha",
    "α": "alpha",
}

#: Phrases that signal a limitation. Only a full text contains these in the
#: authors' own voice; abstracts are written to avoid them.
NEGATIVE_CUES = (
    "we do not",
    "we cannot",
    "we did not",
    "does not handle",
    "do not handle",
    "fails to",
    "fails when",
    "is not evaluated",
    "are not evaluated",
    "remains open",
    "left for future",
    "we leave",
    "limitation",
    "limited to",
    "only a single",
    "cannot handle",
    "future work",
)

#: Phrases that signal an implementation or setup detail, i.e. body material.
BODY_CUES = (
    "we use",
    "we set",
    "we train",
    "we implement",
    "implemented in",
    "we follow",
    "our implementation",
    "all experiments",
    "in our setup",
    "hardware",
    "trained on",
    "we adopt",
    "we initialize",
    "footnote",
)

SECTION_WORDS = (
    "abstract",
    "introduction",
    "related work",
    "background",
    "method",
    "methods",
    "approach",
    "implementation",
    "experiment",
    "experiments",
    "results",
    "evaluation",
    "ablation",
    "discussion",
    "limitation",
    "limitations",
    "future work",
    "conclusion",
    "conclusions",
    "references",
    "appendix",
)

_NUMBERED_HEADING = re.compile(
    r"^\s*(?:(?:[IVXLC]{1,5})|(?:\d{1,2}(?:\.\d{1,2}){0,2}))\.?\s+"
    r"([A-Z][A-Za-z][A-Za-z \-]{2,60})\s*$"
)
_PLAIN_HEADING = re.compile(
    r"^\s*(%s)[A-Za-z ]{0,30}\s*$" % "|".join(SECTION_WORDS), re.IGNORECASE
)
_CAPTION = re.compile(
    r"\b(?:Table|Tab\.|Figure|Fig\.)\s*([IVXLC]+|\d{1,2}[a-z]?)\b",
    re.IGNORECASE,
)
_NUMERIC_WITH_UNIT = re.compile(
    r"-?\d+(?:\.\d+)?\s*(?:dB|%|MB|KB|GB|ms|fps|cm|mm|km|px|s\b|m\b|°|deg)",
    re.IGNORECASE,
)
_PLAIN_NUMBER = re.compile(r"\b\d+\.\d{2,}\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


class ReceiptExtractionError(Exception):
    """Raised when the text cannot supply all four fingerprints."""

    exit_code = 6

    def __init__(self, message, missing=None, assessment=None):
        self.missing = list(missing or [])
        self.assessment = assessment or {}
        super().__init__(message)


def split_pages(text):
    """Split on form feed. A single-page document yields one entry."""
    pages = [page for page in text.split(PAGE_BREAK)]
    if not pages:
        return [""]
    return pages


def _looks_like_heading(line):
    stripped = line.strip()
    if not stripped or len(stripped) > 70:
        return None
    match = _NUMBERED_HEADING.match(stripped)
    if match:
        return match.group(1).strip()
    match = _PLAIN_HEADING.match(stripped)
    if match:
        return match.group(1).strip()
    return None


def scan(text):
    """Annotate every line with its page and the section it belongs to.

    Returns ``(lines, headings)`` where each line is
    ``{"page", "section", "text"}`` and headings are ``(page, title)`` pairs.
    """
    pages = split_pages(text)
    lines = []
    headings = []
    section = ""
    for index, page in enumerate(pages, start=1):
        for raw in page.splitlines():
            title = _looks_like_heading(raw)
            if title:
                section = title
                headings.append((index, title))
            if raw.strip():
                lines.append({"page": index, "section": section, "text": raw.strip()})
    return lines, headings


def _sentences(lines):
    """Flatten lines into sentences, keeping page and section provenance."""
    for line in lines:
        for sentence in _SENTENCE_SPLIT.split(line["text"]):
            sentence = sentence.strip()
            if 20 <= len(sentence) <= 400:
                yield {
                    "page": line["page"],
                    "section": line["section"],
                    "text": sentence,
                }


def assess(text, min_full_chars=MIN_FULL_CHARS, min_full_pages=MIN_FULL_PAGES):
    """Decide whether this text is a full paper, a partial read, or just an abstract."""
    pages = split_pages(text)
    chars = len(text)
    _, headings = scan(text)
    titles = [title.lower() for _, title in headings]

    has_abstract = any("abstract" in title for title in titles)
    has_experiment = any(
        any(word in title for word in ("experiment", "result", "implementation", "evaluation", "ablation"))
        for title in titles
    )
    has_references = any("reference" in title for title in titles)

    reasons = []
    if chars < min_full_chars:
        reasons.append("only %d characters" % chars)
    if len(pages) < min_full_pages:
        reasons.append("only %d page(s)" % len(pages))
    if not has_experiment:
        reasons.append("no experiment/results section")
    if not has_references:
        reasons.append("no reference list")

    # An abstract has no experiment section and no references. Shortness alone is not
    # enough to call it an abstract: a three-page excerpt of a real paper is a partial
    # read, and the message should say so rather than mislabel it.
    if not has_experiment and (chars < ABSTRACT_ONLY_MAX_CHARS or len(pages) == 1):
        verdict = VERDICT_ABSTRACT_ONLY
    elif reasons:
        verdict = VERDICT_PARTIAL
    else:
        verdict = VERDICT_FULL

    return {
        "verdict": verdict,
        "pages": len(pages),
        "chars": chars,
        "chars_per_page": round(chars / max(1, len(pages)), 1),
        "has_abstract": has_abstract,
        "has_experiment_section": has_experiment,
        "has_references": has_references,
        "sections": [title for _, title in headings],
        "reasons": reasons,
    }


def _section_label(section):
    return "sec %s" % section if section else "unsectioned"


def find_number_with_locator(lines):
    """A concrete number that sits next to a table/figure caption, with page."""
    best = None
    for index, line in enumerate(lines):
        caption = _CAPTION.search(line["text"])
        if not caption:
            continue
        window = [line["text"]]
        for offset in range(1, 4):
            if index + offset < len(lines) and lines[index + offset]["page"] == line["page"]:
                window.append(lines[index + offset]["text"])
        blob = " ".join(window)
        numbers = _NUMERIC_WITH_UNIT.findall(blob) or _PLAIN_NUMBER.findall(blob)
        if not numbers:
            continue
        label = caption.group(0).strip()
        candidate = "%s: %s (p.%d)" % (label, " / ".join(numbers[:3]), line["page"])
        # Prefer a caption that actually carries units.
        if _NUMERIC_WITH_UNIT.findall(blob):
            return candidate
        if best is None:
            best = candidate
    return best


def find_hyperparameters(lines):
    """Hyperparameter statements with their values and section."""
    found = []
    seen = set()
    pattern = re.compile(
        r"(?i)\b(%s)\b\s*(?:=|:|of|is|was|=?)\s*([0-9][0-9a-zA-Z.eE\-+]{0,10})"
        % "|".join(sorted(HYPERPARAM_KEYS, key=len, reverse=True))
    )
    for line in lines:
        for match in pattern.finditer(line["text"]):
            raw_key = match.group(1).lower()
            canonical = HYPERPARAM_KEYS.get(raw_key)
            if canonical is None or canonical in seen:
                continue
            value = match.group(2).rstrip(".,;")
            if not any(ch.isdigit() for ch in value):
                continue
            seen.add(canonical)
            found.append((canonical, value, line["page"], line["section"]))
            if len(found) == 3:
                break
        if len(found) == 3:
            break
    if not found:
        return None
    page = found[0][2]
    section = _section_label(found[0][3])
    body = ", ".join("%s=%s" % (key, value) for key, value, _, _ in found)
    return "%s (%s, p.%d)" % (body, section, page)


def find_negative_quote(lines):
    """A limitation stated in the authors' own words."""
    fallback = None
    for sentence in _sentences(lines):
        lowered = sentence["text"].lower()
        if not any(cue in lowered for cue in NEGATIVE_CUES):
            continue
        quote = sentence["text"]
        if len(quote) > 180:
            quote = quote[:177].rstrip() + "..."
        entry = '%s (%s, p.%d)' % (quote, _section_label(sentence["section"]), sentence["page"])
        section = (sentence["section"] or "").lower()
        if "limitation" in section or "future" in section or "discussion" in section:
            return entry
        if fallback is None:
            fallback = entry
    return fallback


def find_body_detail(lines):
    """A non-conclusory body sentence: setup, implementation, a footnote."""
    for sentence in _sentences(lines):
        section = (sentence["section"] or "").lower()
        if "abstract" in section or "introduction" in section:
            continue
        lowered = sentence["text"].lower()
        if any(cue in lowered for cue in BODY_CUES):
            quote = sentence["text"]
            if len(quote) > 180:
                quote = quote[:177].rstrip() + "..."
            return '%s (%s, p.%d)' % (
                quote,
                _section_label(sentence["section"]),
                sentence["page"],
            )
    return None


FINDERS = {
    "number_with_locator": find_number_with_locator,
    "hyperparameters": find_hyperparameters,
    "negative_quote": find_negative_quote,
    "body_detail": find_body_detail,
}


def extract_receipt(text, require_full=True):
    """Build the four fingerprints from extracted text, or fail loudly.

    ``require_full`` is the gate itself: if the text does not look like a full
    paper, no receipt is produced, so the paper cannot reach ``READ_FULL``.
    """
    assessment = assess(text)
    if require_full and assessment["verdict"] != VERDICT_FULL:
        raise ReceiptExtractionError(
            "text is not a full paper (%s): %s"
            % (assessment["verdict"], "; ".join(assessment["reasons"]) or "insufficient length"),
            missing=list(FINDERS),
            assessment=assessment,
        )

    lines, _ = scan(text)
    receipt = {}
    missing = []
    for field, finder in FINDERS.items():
        value = finder(lines)
        if value:
            receipt[field] = value
        else:
            missing.append(field)

    if missing:
        raise ReceiptExtractionError(
            "could not find %d of 4 fingerprints: %s"
            % (len(missing), ", ".join(missing)),
            missing=missing,
            assessment=assessment,
        )

    receipt["extra"] = {
        "extractor": "readproof-text-v1",
        "verdict": assessment["verdict"],
        "pages": assessment["pages"],
        "chars": assessment["chars"],
    }
    return receipt, assessment
