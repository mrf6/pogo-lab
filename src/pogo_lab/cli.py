"""Command-line entry point for pogo-lab."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pogo-lab",
        description="Pokémon GO PvP IV rank checker and simulation lab.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pogo-lab CLI / interactive TUI."""
    parser = build_parser()
    parser.parse_args(argv)

    from pogo_lab.tui import run_tui

    run_tui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
