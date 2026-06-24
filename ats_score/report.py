"""Render a Report: rich terminal output, plain-text fallback, or JSON.

The CLI picks the mode; this module owns the formatting. Findings are the point
of the tool, so each section prints its actionable findings, not just a number.
"""

from __future__ import annotations

import json
import os
import sys

from .core import Report
from .checks_ats import Finding


def _grade(s: int) -> str:
    if s >= 90:
        return "excellent"
    if s >= 75:
        return "good"
    if s >= 60:
        return "fair"
    return "needs work"


def _color(s: int) -> str:
    return "green" if s >= 75 else "yellow" if s >= 60 else "red"


def to_dict(r: Report) -> dict:
    def findings(fs: list[Finding]) -> list[dict]:
        return [{"severity": f.severity, "message": f.message, "penalty": f.penalty}
                for f in fs]

    out: dict = {
        "source": r.source,
        "overall": r.overall,
        "ats": {"score": r.ats.score, "findings": findings(r.ats.findings)},
        "content": {"score": r.content.score, "findings": findings(r.content.findings),
                    "bullets": r.content.bullets, "graded": r.content.graded,
                    "unquantified": r.content.unquantified, "weak": r.content.weak,
                    "no_verb": r.content.no_verb},
        "writing": {"score": r.writing.score, "findings": findings(r.writing.findings),
                    "typos": r.writing.typos, "fillers": r.writing.fillers,
                    "ai_tells": r.writing.ai_tells},
    }
    if r.similarity is not None:
        s = r.similarity
        out["jd_match"] = {"score": s.score, "cosine": s.cosine,
                           "coverage": s.coverage, "matched": s.matched,
                           "missing": s.missing}
    else:
        out["detected_skills"] = r.detected_skills
    if r.warnings:
        out["warnings"] = r.warnings
    return out


def render_json(r: Report) -> str:
    return json.dumps(to_dict(r), indent=2, ensure_ascii=False)


def _use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def render(r: Report) -> str:
    """Rich output if attached to a color TTY, otherwise plain text."""
    if _use_color():
        try:
            return _render_rich(r)
        except Exception:
            pass  # ponytail: rich missing/broken -> plain text, never crash
    return _render_plain(r)


def _sections(r: Report):
    """(label, score, summary) for the four sub-scores, JD only if present."""
    yield "ATS readiness", r.ats.score, r.ats.summary
    yield "Content", r.content.score, r.content.summary
    yield "Writing", r.writing.score, r.writing.summary
    if r.similarity is not None:
        yield "JD match", r.similarity.score, r.similarity.summary


def _render_plain(r: Report) -> str:
    L: list[str] = []
    name = os.path.basename(r.source) or r.source
    L.append(f"Resume score: {r.overall}/100 ({_grade(r.overall)})  —  {name}")
    L.append("=" * 60)
    for label, sc, summ in _sections(r):
        L.append(f"\n{label}: {sc}/100 ({_grade(sc)})")
        L.append(f"  {summ}")

    all_findings = (r.ats.findings + r.content.findings + r.writing.findings)
    fails = [f for f in all_findings if f.severity == "fail"]
    warns = [f for f in all_findings if f.severity == "warn"]
    if fails:
        L.append("\nFix first:")
        L.extend(f"  ✗ {f.message}" for f in fails)
    if warns:
        L.append("\nImprove:")
        L.extend(f"  • {f.message}" for f in warns[:20])
        if len(warns) > 20:
            L.append(f"  … and {len(warns) - 20} more")

    if r.similarity is not None:
        s = r.similarity
        if s.missing:
            L.append("\nMissing skills the JD asks for:")
            L.append("  " + ", ".join(s.missing))
    elif r.detected_skills:
        L.append("\nSkills the parser read (add a JD with --jd to match):")
        L.append("  " + ", ".join(r.detected_skills))

    return "\n".join(L)


def _render_rich(r: Report) -> str:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console(record=True, force_terminal=True)
    name = os.path.basename(r.source) or r.source
    console.print(Panel(
        f"[bold {_color(r.overall)}]{r.overall}/100[/]  ({_grade(r.overall)})",
        title=f"Resume score — {name}", expand=False))

    table = Table(show_header=True, header_style="bold")
    table.add_column("Section")
    table.add_column("Score", justify="right")
    table.add_column("Detail")
    for label, sc, summ in _sections(r):
        table.add_row(label, f"[{_color(sc)}]{sc}[/]", summ)
    console.print(table)

    all_findings = (r.ats.findings + r.content.findings + r.writing.findings)
    fails = [f for f in all_findings if f.severity == "fail"]
    warns = [f for f in all_findings if f.severity == "warn"]
    if fails:
        console.print("\n[bold red]Fix first[/]")
        for f in fails:
            console.print(f"  [red]✗[/] {f.message}")
    if warns:
        console.print("\n[bold yellow]Improve[/]")
        for f in warns[:20]:
            console.print(f"  [yellow]•[/] {f.message}")
        if len(warns) > 20:
            console.print(f"  [dim]… and {len(warns) - 20} more[/]")

    if r.similarity is not None:
        s = r.similarity
        if s.matched:
            console.print("\n[bold green]Matched skills[/]  " + ", ".join(s.matched))
        if s.missing:
            console.print("[bold red]Missing skills[/]  " + ", ".join(s.missing))
    elif r.detected_skills:
        console.print("\n[bold]Skills the parser read[/] [dim](add --jd to match)[/]")
        console.print("  " + ", ".join(r.detected_skills))

    return console.export_text(styles=True).rstrip("\n")


def _selfcheck() -> None:
    from .core import Report
    from .checks_ats import AtsResult, Finding
    from .checks_content import ContentResult
    from .writing import WritingResult

    r = Report(
        overall=82,
        ats=AtsResult(90, [Finding("warn", "missing section: Summary", 8)]),
        content=ContentResult(80, [Finding("warn", "2/5 bullets lack numbers", 4)],
                              bullets=5, graded=5, unquantified=2),
        writing=WritingResult(95, [], typos=0, fillers=0, ai_tells=0),
        detected_skills=["machine learning", "python", "sql"],
        source="resume.pdf",
    )
    plain = _render_plain(r)
    assert "82/100" in plain, plain
    assert "machine learning" in plain
    assert "missing section: Summary" in plain
    d = to_dict(r)
    assert d["overall"] == 82 and "detected_skills" in d and "jd_match" not in d
    assert json.loads(render_json(r))["ats"]["score"] == 90

    print("report selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
