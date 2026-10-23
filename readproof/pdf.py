"""PDF byte-level inspection: integrity and identity, never parsing.

`readproof` does not extract text from PDFs — see `receipt.py` for why. But it does
have to answer two questions before a PDF may enter the ledger:

1. **Is this file intact?** A truncated download looks like a successful fetch and
   then produces a receipt from half a paper. The `%%EOF` trailer is the only reliable
   signal; file size is not (a valid PDF can be 635 bytes).
2. **Is this the paper the ledger thinks it is?** Manual uploads arrive with whatever
   filename the user had, sometimes as a different version, sometimes as the wrong
   paper entirely.

Both answers are cheap and do not require a parser.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.error
import urllib.request

#: Smallest plausible PDF. Anything under this is a redirect body or an error page.
MIN_BYTES = 64

#: HTTP bodies larger than this are refused rather than buffered into memory.
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024

MAGIC = b"%PDF-"

EXIT_BAD_PDF = 8
EXIT_IDENTITY_MISMATCH = 9

#: `/Type /Page` marks a page object; `/Type /Pages` is the tree node and must not count.
_PAGE_OBJECT = re.compile(rb"/Type\s*/Page[^s]")


class PdfError(Exception):
    """A PDF was refused before it could influence anything."""

    exit_code = EXIT_BAD_PDF


class IdentityMismatch(PdfError):
    exit_code = EXIT_IDENTITY_MISMATCH


def sha256_of_bytes(data):
    return hashlib.sha256(data).hexdigest()


def inspect_bytes(data):
    """Return everything we can determine about a PDF without parsing it."""
    tail = data[-2048:]
    page_objects = len(_PAGE_OBJECT.findall(data))
    problems = []
    if len(data) < MIN_BYTES:
        problems.append("only %d bytes (minimum %d)" % (len(data), MIN_BYTES))
    if not data.startswith(MAGIC):
        problems.append("missing %%PDF- header (not a PDF)")
    if b"%%EOF" not in tail:
        problems.append("missing %%EOF trailer (truncated download)")
    if page_objects < 1:
        problems.append("no page objects found")
    return {
        "bytes": len(data),
        "sha256": sha256_of_bytes(data),
        "has_magic": data.startswith(MAGIC),
        "has_eof": b"%%EOF" in tail,
        "page_objects": page_objects,
        "problems": problems,
        "ok": not problems,
    }


def inspect_file(path):
    with open(path, "rb") as handle:
        return inspect_bytes(handle.read())


def require_valid(path, allow_empty_pages=False):
    """Raise :class:`PdfError` unless the file passes every integrity check."""
    report = inspect_file(path)
    problems = list(report["problems"])
    if allow_empty_pages:
        problems = [p for p in problems if "page objects" not in p]
    if problems:
        raise PdfError("%s: %s" % (os.path.basename(path), "; ".join(problems)))
    return report


def download(url, dest, max_bytes=MAX_DOWNLOAD_BYTES, timeout=60):
    """Fetch a URL to ``dest`` with a size cap. Refuses non-http(s) schemes."""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise PdfError("only http(s) URLs are supported: %s" % url)
    request = urllib.request.Request(
        url, headers={"User-Agent": "readproof/0.4 (+https://github.com/rrdongdong/readproof)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            chunks = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise PdfError("download exceeds %d bytes: %s" % (max_bytes, url))
                chunks.append(chunk)
    except urllib.error.HTTPError as exc:
        raise PdfError("HTTP %s for %s" % (exc.code, url))
    except urllib.error.URLError as exc:
        raise PdfError("could not download %s: %s" % (url, exc.reason))

    data = b"".join(chunks)
    with open(dest, "wb") as handle:
        handle.write(data)
    return dest


def identity_matches(title, text, threshold=0.6):
    """Does ``text`` plausibly belong to the paper ``title``?

    Only the first pages are searched: titles live on page 1, and a later mention of
    the same words in the bibliography would produce false confidence.
    """
    if not title or not text:
        return False, "no title or no text to compare"
    head = text[:6000]
    from_title = [w for w in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", title.lower()) if len(w) > 2]
    if not from_title:
        return False, "title has no comparable words"
    lowered = head.lower()
    hits = [word for word in from_title if word in lowered]
    ratio = len(hits) / float(len(from_title))
    if ratio >= threshold:
        return True, "%d/%d title words found in the first pages" % (len(hits), len(from_title))
    return False, "only %d/%d title words found (%s)" % (
        len(hits),
        len(from_title),
        ", ".join(from_title[:6]),
    )
