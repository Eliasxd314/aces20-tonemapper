#!/usr/bin/env python3
"""Entry point kept for backwards compatibility: ``./tonemap-aces.py image.exr``.

The implementation lives in the ``aces20_tonemapper`` package.
"""
import sys

from aces20_tonemapper.cli import main

if __name__ == "__main__":
    sys.exit(main())
