# pogo-lab

A Python project for Pokémon GO rankings and simulations. The initial focus is a
PvP IV rank checker and battle simulation, with longer-term goals of exploring
reinforcement learning and large-scale raid simulations.

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer. uv can
install Python if a compatible interpreter is not already available.

```sh
uv sync --locked
source .venv/bin/activate  # macOS/Linux
pre-commit install

# Or, without activating the virtual environment:
uv run pre-commit install
```

Run the checks locally:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run pre-commit run --all-files
```

Use `uv add <package>` to add a runtime dependency or `uv add --dev <package>`
for a development dependency. Commit changes to both `pyproject.toml` and
`uv.lock`. The virtual environment in `.venv/` is local and is not committed.

## Roadmap

- Shared Pokémon GO data and stat mechanics
- PvP IV rankings and battle simulation
- Reinforcement learning experiments and raid simulation
