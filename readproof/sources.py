"""Finding a text extractor without bundling one.

`readproof` needs extracted text to build a reading receipt, but it must not ship a
PDF parser (see `receipt.py`) and must not pretend it has one when it does not. So this
module looks for an extractor the machine already has, runs it with a fixed contract,
and fails with a specific exit code when nothing suitable is installed.

Contract for any extractor: it receives a PDF path as its last argument and writes
page-separated text to stdout. The two defaults both satisfy this.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess

EXIT_NO_EXTRACTOR = 7

#: Commands tried in order when nothing is configured. Both emit form-feed page breaks.
DEFAULT_EXTRACTORS = (
    ("pdftotext", ["pdftotext", "-layout", "-enc", "UTF-8", "{pdf}", "-"]),
    ("mutool", ["mutool", "draw", "-F", "txt", "-o", "-", "{pdf}"]),
)

ENV_OVERRIDE = "READPROOF_PDF_COMMAND"

#: A paper that takes longer than this to extract is not a paper we are willing to wait
#: for; the timeout also protects against an extractor that pages a human.
DEFAULT_TIMEOUT = 180


class ExtractorUnavailable(Exception):
    """No extractor is installed, and guessing would silently produce nothing."""

    exit_code = EXIT_NO_EXTRACTOR


class ExtractionFailed(Exception):
    """An extractor ran and failed, or produced nothing usable."""

    exit_code = 1


def split_command(raw, windows=None):
    """Split a command template without destroying Windows paths.

    ``shlex.split`` applies POSIX rules, where a backslash is an escape character, so
    ``C:\\tools\\python.exe script.py`` came back as ``C:toolspython.exe script.py``
    and ``shutil.which`` then failed on a path that exists. On Windows we split without
    POSIX escaping and strip the surrounding quotes ourselves.
    """
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return shlex.split(raw)
    tokens = []
    for token in shlex.split(raw, posix=False):
        if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
            token = token[1:-1]
        tokens.append(token)
    return tokens


def _template_from_env():
    raw = os.environ.get(ENV_OVERRIDE, "").strip()
    if not raw:
        return None
    argv = split_command(raw)
    if not any("{pdf}" in token for token in argv):
        argv = argv + ["{pdf}"]
    name = os.path.basename(argv[0]) or "custom"
    return (name, argv)


def available(command=None):
    """Return the extractor that would be used, or ``None``.

    ``command`` may be an explicit template string (as in ``$READPROOF_PDF_COMMAND``).
    """
    if command:
        argv = split_command(command)
        if not any("{pdf}" in token for token in argv):
            argv = argv + ["{pdf}"]
        if shutil.which(argv[0]):
            return (os.path.basename(argv[0]), argv)
        raise ExtractorUnavailable(
            "configured extractor not found: %s (from %s)" % (argv[0], ENV_OVERRIDE)
        )

    env = _template_from_env()
    if env is not None:
        if shutil.which(env[1][0]):
            return env
        raise ExtractorUnavailable(
            "extractor from %s not found: %s" % (ENV_OVERRIDE, env[1][0])
        )

    for name, argv in DEFAULT_EXTRACTORS:
        if shutil.which(argv[0]):
            return (name, argv)
    return None


def describe_unavailable():
    tried = ", ".join(name for name, _ in DEFAULT_EXTRACTORS)
    return (
        "no PDF text extractor available (tried: %s).\n"
        "options:\n"
        "  1. install poppler-utils (provides pdftotext)\n"
        "  2. set %s to a command that writes extracted text to stdout, e.g.\n"
        "       export %s='dsh-pdf-extract {}'\n"
        "  3. extract the text yourself and pass it with --from-text\n"
        "  4. upload the PDF and let the agent read it, then pass the text"
        % (tried, ENV_OVERRIDE, ENV_OVERRIDE)
    )


def extract_text(pdf_path, command=None, timeout=DEFAULT_TIMEOUT):
    """Run the chosen extractor. Returns ``(text, meta)``.

    Raises :class:`ExtractorUnavailable` when nothing is installed and
    :class:`ExtractionFailed` when the extractor runs but yields nothing.
    """
    found = available(command)
    if found is None:
        raise ExtractorUnavailable(describe_unavailable())
    name, template = found
    argv = [token.replace("{pdf}", pdf_path) for token in template]
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ExtractionFailed("%s timed out after %ds" % (name, timeout))
    except OSError as exc:
        raise ExtractionFailed("could not run %s: %s" % (name, exc))

    text = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = stderr[-1] if stderr else "no stderr"
        raise ExtractionFailed("%s exited %d: %s" % (name, completed.returncode, detail))
    if len(text.strip()) < 200:
        raise ExtractionFailed(
            "%s produced %d characters — the PDF has no text layer (scanned image?)"
            % (name, len(text.strip()))
        )
    return text, {"extractor": name, "chars": len(text), "pages": text.count("\f") + 1}
