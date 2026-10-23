PYTHON ?= python3

.PHONY: help test demo serve-demo web clean

help:
	@echo "make test        run the python test suite"
	@echo "make web         install and build the frontend (web/dist)"
	@echo "make demo        regenerate demo/ledger.json, demo/gap-table.md, demo/graph.json"
	@echo "make serve-demo  serve the demo at http://127.0.0.1:8010 (needs: make web)"
	@echo "make clean       remove caches and build output"

test:
	$(PYTHON) -m unittest discover -s tests -v

web:
	cd web && npm install && npm run build

demo:
	$(PYTHON) demo/build_demo.py

serve-demo: web demo
	$(PYTHON) demo/build_demo.py --serve

clean:
	rm -rf readproof/__pycache__ tests/__pycache__ web/dist web/node_modules demo/graph.json
