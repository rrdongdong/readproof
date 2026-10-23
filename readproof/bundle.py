"""Build and stamp the bundled frontend.

The built app lives inside the package (``readproof/static``) so that:

- ``pip install readproof`` brings a working UI with no Node on the user's machine;
- a source checkout works after ``python -m readproof bundle``;
- there is exactly one copy of the built assets, not one in ``web/dist`` and another in
  the package.

Because the output is committed, it can go stale. ``BUILD.json`` records a hash of
``web/src`` plus the entry points, and :func:`staleness` compares that against the tree;
CI fails when they disagree, so "forgot to rebuild" is a build error rather than a
confusing blank page.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PACKAGE_DIR)
WEB_DIR = os.path.join(ROOT, "web")
STATIC_DIR = os.path.join(PACKAGE_DIR, "static")
MANIFEST = os.path.join(STATIC_DIR, "BUILD.json")

EXIT_NPM_MISSING = 11


class BundleError(Exception):
    exit_code = EXIT_NPM_MISSING


def _canonical_bytes(path):
    """Read a source file as text-normalised bytes.

    Line endings are folded to LF before hashing: a Windows checkout with
    ``core.autocrlf`` would otherwise produce a different hash for identical sources and
    report the committed build as stale on every Windows machine.
    """
    with open(path, "rb") as handle:
        return handle.read().replace(b"\r\n", b"\n")


def source_fingerprint(web_dir=WEB_DIR):
    """Hash the frontend sources that determine the build output."""
    entries = []
    roots = [
        os.path.join(web_dir, "src"),
        os.path.join(web_dir, "index.html"),
        os.path.join(web_dir, "package.json"),
        os.path.join(web_dir, "vite.config.js"),
    ]
    files = []
    for root in roots:
        if os.path.isfile(root):
            files.append(root)
        elif os.path.isdir(root):
            for base, _dirs, names in os.walk(root):
                files.extend(os.path.join(base, name) for name in sorted(names))
    for path in sorted(files):
        relative = os.path.relpath(path, web_dir).replace(os.sep, "/")
        digest = hashlib.sha256(_canonical_bytes(path)).hexdigest()
        entries.append("%s %s" % (relative, digest))
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def write_manifest(source_hash, note=""):
    # Relative paths only: an absolute path both changes per machine and publishes
    # somebody's home directory, which is exactly what broke the demo ledger earlier.
    entries = sorted(
        os.path.relpath(os.path.join(base, name), STATIC_DIR).replace(os.sep, "/")
        for base, _dirs, names in os.walk(STATIC_DIR)
        for name in names
        if name != "BUILD.json"
    )
    payload = {
        "source": source_hash,
        "note": note or "built by `python -m readproof bundle`; committed on purpose",
        "files": entries,
    }
    with open(MANIFEST, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return MANIFEST


def staleness(web_dir=WEB_DIR):
    """Return ``(stale, message)`` comparing the committed build to the current sources."""
    if not os.path.isfile(MANIFEST):
        return True, "no BUILD.json: the bundled frontend has never been built"
    try:
        with open(MANIFEST, encoding="utf-8") as handle:
            recorded = json.load(handle).get("source")
    except ValueError:
        return True, "BUILD.json is not valid JSON"
    current = source_fingerprint(web_dir)
    if recorded != current:
        return True, (
            "the bundled frontend is stale: web/src changed since it was built.\n"
            "  rebuild: python -m readproof bundle   (or: cd web && npm run build)"
        )
    return False, "bundled frontend matches web/src"


def build(web_dir=WEB_DIR, static_dir=STATIC_DIR, npm="npm"):
    """Run the frontend build and stamp the manifest. Raises BundleError without npm."""
    if shutil.which(npm) is None:
        raise BundleError(
            "npm not found — the frontend cannot be rebuilt here.\n"
            "the committed build in %s is used as-is; to rebuild install Node, or run the\n"
            "build on a machine that has it and commit the result" % static_dir
        )
    if not os.path.isdir(web_dir):
        raise BundleError("frontend sources not found: %s" % web_dir)
    before = source_fingerprint(web_dir)
    result = subprocess.run(
        [npm, "run", "build"], cwd=web_dir, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise BundleError(
            "npm run build failed (%d):\n%s\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )
    if not os.path.isfile(os.path.join(static_dir, "index.html")):
        raise BundleError("build produced no index.html in %s" % static_dir)
    if source_fingerprint(web_dir) != before:
        raise BundleError("frontend sources changed during the build; rebuild again")
    write_manifest(before)
    return static_dir


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("check", "--check"):
        stale, message = staleness()
        print(message)
        return 1 if stale else 0
    try:
        target = build()
    except BundleError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    print("bundled frontend rebuilt: %s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
