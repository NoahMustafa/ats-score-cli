"""Command-line entry point. Thin wrapper over core.score / report.render."""

from __future__ import annotations

import argparse
import sys

from .core import score
from .report import render, render_json


def main(argv: list[str] | None = None) -> int:
    # The report uses ✗/•/box-drawing chars; a legacy Windows console (cp1252)
    # crashes on them. Force UTF-8 so the binary works on a stock terminal.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="ats-score",
        description="Score a resume for ATS-readiness, content, and writing. "
                    "Add --jd to also match it against a job description.")
    parser.add_argument("resume", help="resume file (.pdf or .docx)")
    parser.add_argument("--jd", metavar="FILE_OR_TEXT",
                        help="job description file (or text) to match against")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of a report")
    args = parser.parse_args(argv)

    try:
        report = score(args.resume, args.jd)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:  # unsupported file type
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(render_json(report) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
