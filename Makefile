.PHONY: build test lint clean

build:
	uv sync --reinstall-package pogo-lab

test:
	uv run pytest

lint:
	uv run ruff check .

clean:
	rm -rf build dist src/pogo_lab/battle/*.so src/pogo_lab/battle/*.pyi
