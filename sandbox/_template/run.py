"""Sandbox experiment template.

Copy this whole folder to start a new experiment:
    cp -r sandbox/_template sandbox/my-idea

Edit this file with your code. Keep PAPER_MODE=True. Don't import from
trading/, kalshi/, or companies/ — copy what you need.
"""
from __future__ import annotations

PAPER_MODE = True
EXPERIMENT_NAME = "template"


def main() -> None:
    assert PAPER_MODE is True, "sandbox experiments must run in paper mode"
    print(f"sandbox template ready — experiment: {EXPERIMENT_NAME}")


if __name__ == "__main__":
    main()
