"""Compatibility shim for pre-packaging Claude Desktop configs.

Old configs pointed at `C:\\ZachAI\\companies\\wpflow\\server.py`.
The real entry point is now `wpflow.server:main` (installed as `wpflow` CLI).
This shim keeps old configs working.
"""
from __future__ import annotations
import sys
from wpflow.server import main

if __name__ == "__main__":
    sys.exit(main())
