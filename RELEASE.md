# Releasing

Two artefacts matter: the Python package (which now carries the built frontend) and the
DSH skill in [`paper-trawl`](https://github.com/rrdongdong/paper-trawl).

## Before any release

```console
$ make test                     # 186 tests
$ python -m readproof bundle check   # the committed frontend matches web/src
$ python demo/build_demo.py     # and produces no diff in demo/
```

All three are also enforced by CI.

## The frontend inside the package

`web/src` is built into `readproof/static/` and **committed on purpose**, so that
`pip install readproof` gives a working UI with no Node on the user's machine.

```console
$ cd web && npm install && cd .. && python -m readproof bundle
$ git add readproof/static && git commit -m "chore: rebuild frontend"
```

`BUILD.json` inside that directory records a hash of `web/src`. If you change a component
and forget to rebuild, `readproof bundle check` fails and CI blocks the merge — the failure
says which command to run.

## PyPI

Not published yet. When you want it:

```console
$ python -m pip install --upgrade build twine
$ python -m build                 # sdist + wheel; the wheel includes readproof/static
$ python -m twine check dist/*
$ python -m twine upload dist/*   # needs a PyPI API token
```

Then the whole installation story is:

```console
$ pip install readproof
$ readproof demo                 # shows the state machine
$ readproof --ledger my.json serve --port 8000 --vocab vocab.tsv
```

Check that the wheel really contains the frontend before uploading:

```console
$ python -m zipfile -l dist/readproof-*.whl | grep static
```

If that list is empty, the `[tool.setuptools.package-data]` entry lost its `static/*`
pattern and the published package would serve a 503.

## Versioning

Semantic-ish, but the honest driver is the CHANGELOG: each section names what broke and
what was found by whom. A patch release that fixes a Windows-only crash still gets its own
section, because that is the part a reader wants.

## What a "PyPI token" is, and why this file does not contain one

PyPI is the package index `pip` talks to. Uploading needs a credential tied to your PyPI
account: an API token (username `__token__`, password `pypi-...`). It is not a shared
secret — it authorises publishing **under your name**, so it belongs to you and only you.
Two consequences:

- never paste it into a chat, an issue, or a commit; if it leaks, publish is compromised
  until you revoke it;
- nobody else can publish for you. That is why the release steps below are documented
  rather than executed.

Practical safety rules:

- scope the token to this project only when PyPI offers it, and revoke it after the first
  successful upload if you do not plan to publish often;
- prefer `twine upload` with the token typed at the prompt, or `TWINE_API_KEY` in the
  environment of a single command — not in `~/.pypirc` on a shared machine;
- CI does **not** hold a token. The `package` job builds and attaches the wheel as a run
  artifact instead, which covers everyone who is not published yet.

## If you would rather not publish at all

That is a legitimate choice and nothing breaks:

```console
$ pip install "readproof @ git+https://github.com/rrdongdong/readproof.git"
```

or download the wheel from the `package` job's artifacts. The only thing a package index
buys is a shorter command.
