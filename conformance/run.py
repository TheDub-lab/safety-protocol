#!/usr/bin/env python
"""Entry point: `python conformance/run.py` -> runs the Safety Protocol
conformance suite (SPEC.md C1..C10) and exits non-zero on any failure."""
import os
import sys

# Allow running from repo root: ensure repo root (parent of this dir) is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conformance import _main

if __name__ == "__main__":
    sys.exit(_main())
