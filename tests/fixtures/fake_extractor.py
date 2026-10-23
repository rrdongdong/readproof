"""Stand-in extractor for tests: takes a PDF path, prints the full-paper fixture.

It exists so the adapter can be tested without poppler-utils installed, and so the
extractor contract (last argument is the PDF, text on stdout) is executable
documentation.
"""

import pathlib
import sys

FIXTURE = pathlib.Path(__file__).parent / "full_paper.txt"


def main():
    if len(sys.argv) < 2:
        print("usage: fake_extractor.py <pdf>", file=sys.stderr)
        return 64
    sys.stdout.write(FIXTURE.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
