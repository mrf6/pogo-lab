.PHONY: build test lint clean

build:
	uv sync --reinstall-package pogolab

test:
	uv run pytest

lint:
	uv run ruff check .

clean:
	rm -rf build dist src/pogolab/battle/*.so src/pogolab/battle/*.pyi
