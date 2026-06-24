"""PyInstaller entry point for the frozen `tool` binary. See tool.spec."""

import sys

from ats_score.cli import main

if __name__ == "__main__":
    sys.exit(main())
