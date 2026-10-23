# readproof web

A read-only interface over a readproof ledger: what has been read, what the receipts
actually say, and where the gaps are.

## Build

```console
cd web
npm install
npm run build          # → web/dist/
```

Then serve it together with the API:

```console
cd ..
readproof --ledger ledger.json serve --port 8000 --vocab vocab.tsv --web-dir web/dist
# open http://127.0.0.1:8000
```

## Develop

```console
readproof --ledger ledger.json serve --port 8000 --vocab vocab.tsv --web-dir "" &
cd web && npm run dev     # http://localhost:5173, /api proxied to :8000
```

## Why no framework on the server

The API is `http.server` from the standard library. That is deliberate:

- the machine this runs on has no `pip`, so a framework cannot be installed;
- the engine's selling point is that it has **no third-party dependencies** and can be
  tested on every commit;
- the routing is a dozen lines — a framework would not earn its keep.

The frontend is a real build chain (Vite + React) because that is where the build
actually helps.

## What it will not do

Write. Every state change goes through the CLI, where each gate has an exit code and
can be tested without a socket. The UI reads; the CLI decides.
