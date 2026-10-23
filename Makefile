PYTHON ?= python3

.PHONY: help test demo serve-demo web check-bundle clean

help:
	@echo "make test        run the python test suite"
	@echo "make web         rebuild the bundled frontend (needs npm once)"
	@echo "make check-bundle  fail if the committed build is stale"
	@echo "make demo        regenerate demo/ledger.json, demo/gap-table.md, demo/graph.json"
	@echo "make serve-demo  serve the demo at http://127.0.0.1:8010 (no Node needed)"
	@echo "make clean       remove caches and build output"

test:
	$(PYTHON) -m unittest discover -s tests -v

web:
	cd web && npm install && $(PYTHON) -m readproof bundle

check-bundle:
	$(PYTHON) -m readproof bundle check

demo:
	$(PYTHON) demo/build_demo.py

# No Node needed: the committed build in readproof/static is served as-is.
serve-demo: demo
	$(PYTHON) demo/build_demo.py --serve

clean:
	rm -rf readproof/__pycache__ tests/__pycache__ web/node_modules demo/graph.json
