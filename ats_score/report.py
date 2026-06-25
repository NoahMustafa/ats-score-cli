"""Render a Report: rich terminal output, plain-text fallback, or JSON.

V1 is an ATS-readiness linter: the overall score is the ATS score, the body is
"what's wrong / what's missing for ATS", and writing advice (filler + AI tells)
is shown separately as suggestions that do not affect the score.
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
        "overall": r.overall,                 # == ats score
        "ats": {"score": r.ats.score, "findings": findings(r.ats.findings)},
        "writing_advice": {                    # not scored
            "fillers": r.writing.fillers,
            "ai_tells": r.writing.ai_tells,
            "findings": findings(r.writing.findings),
        },
    }
    if r.similarity is not None:
        s = r.similarity
        out["jd_match"] = {"score": s.score,
                           "skill_coverage": s.skill_coverage,
                           "prose_coverage": s.prose_coverage,
                           "matched": s.matched, "missing": s.missing,
                           "weak_requirements": s.weak}
    else:
        out["detected_skills"] = r.detected_skills
        if r.jd_unavailable:
            out["jd_match_unavailable"] = "embedding model not bundled in this build"
    if r.warnings:
        out["warnings"] = r.warnings
    return out


def render_json(r: Report) -> str:
    return json.dumps(to_dict(r), indent=2, ensure_ascii=False)


def _use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def render(r: Report) -> str:
    if _use_color():
        try:
            return _render_rich(r)
        except Exception:
            pass  # ponytail: rich missing/broken -> plain text, never crash
    return _render_plain(r)


def _render_plain(r: Report) -> str:
    L: list[str] = []
    name = os.path.basename(r.source) or r.source
    L.append(f"ATS readiness: {r.overall}/100 ({_grade(r.overall)})  —  {name}")
    L.append("=" * 60)

    fails = [f for f in r.ats.findings if f.severity == "fail"]
    warns = [f for f in r.ats.findings if f.severity == "warn"]
    if fails:
        L.append("\nFix these (blocks ATS parsing):")
        L.extend(f"  ✗ {f.message}" for f in fails)
    if warns:
        L.append("\nMissing / improve:")
        L.extend(f"  • {f.message}" for f in warns)
    if not fails and not warns:
        L.append("\nNo ATS issues found.")

    if r.writing.findings:
        L.append("\nWriting advice (not scored — clean up for a human reader):")
        L.extend(f"  ~ {f.message}" for f in r.writing.findings[:20])
        if len(r.writing.findings) > 20:
            L.append(f"  … and {len(r.writing.findings) - 20} more")

    if r.similarity is not None:
        s = r.similarity
        L.append(f"\nJD match: {s.score}/100  "
                 f"(skills {s.skill_coverage:.0%} · requirements {s.prose_coverage:.0%})")
        if s.missing:
            L.append("Missing skills the JD names:")
            L.append("  " + ", ".join(s.missing))
        if s.weak:
            L.append("Requirements your resume doesn't clearly cover:")
            L.extend(f"  - {w}" for w in s.weak)
    else:
        if r.jd_unavailable:
            L.append("\n(JD match unavailable: embedding model not bundled in this build.)")
        if r.detected_skills:
            L.append("\nSkills the parser read:")
            L.append("  " + ", ".join(r.detected_skills))

    return "\n".join(L)


def _render_rich(r: Report) -> str:
    import io
    from rich.console import Console
    from rich.panel import Panel

    console = Console(record=True, force_terminal=True, file=io.StringIO())
    name = os.path.basename(r.source) or r.source
    console.print(Panel(
        f"[bold {_color(r.overall)}]{r.overall}/100[/]  ({_grade(r.overall)})",
        title=f"ATS readiness — {name}", expand=False))

    fails = [f for f in r.ats.findings if f.severity == "fail"]
    warns = [f for f in r.ats.findings if f.severity == "warn"]
    if fails:
        console.print("[bold red]Fix these[/] [dim](blocks ATS parsing)[/]")
        for f in fails:
            console.print(f"  [red]✗[/] {f.message}")
    if warns:
        console.print("\n[bold yellow]Missing / improve[/]")
        for f in warns:
            console.print(f"  [yellow]•[/] {f.message}")
    if not fails and not warns:
        console.print("[green]No ATS issues found.[/]")

    if r.writing.findings:
        console.print("\n[bold]Writing advice[/] [dim](not scored)[/]")
        for f in r.writing.findings[:20]:
            console.print(f"  [dim]~[/] {f.message}")
        if len(r.writing.findings) > 20:
            console.print(f"  [dim]… and {len(r.writing.findings) - 20} more[/]")

    if r.similarity is not None:
        s = r.similarity
        console.print(f"\n[bold]JD match[/] [{_color(s.score)}]{s.score}/100[/] "
                      f"[dim](skills {s.skill_coverage:.0%} · "
                      f"requirements {s.prose_coverage:.0%})[/]")
        if s.matched:
            console.print("[green]Matched skills[/]  " + ", ".join(s.matched))
        if s.missing:
            console.print("[bold red]Missing skills the JD names[/]  " + ", ".join(s.missing))
        if s.weak:
            console.print("[bold yellow]Requirements not clearly covered[/]")
            for w in s.weak:
                console.print(f"  [yellow]-[/] {w}")
    else:
        if r.jd_unavailable:
            console.print("\n[dim](JD match unavailable: model not bundled in this build.)[/]")
        if r.detected_skills:
            console.print("\n[bold]Skills the parser read[/]")
            console.print("  " + ", ".join(r.detected_skills))

    return console.export_text(styles=True).rstrip("\n")


def _selfcheck() -> None:
    from .core import Report
    from .checks_ats import AtsResult, Finding
    from .writing import WritingResult

    r = Report(
        overall=84,
        ats=AtsResult(84, [Finding("fail", "no email found", 10),
                           Finding("warn", "missing section: Skills", 8)]),
        writing=WritingResult([Finding("warn", 'line 3: AI vocab "delve"', 0)],
                              fillers=0, ai_tells=1),
        detected_skills=["python", "sql"],
        source="resume.pdf",
    )
    plain = _render_plain(r)
    assert "84/100" in plain and "no email found" in plain, plain
    assert "delve" in plain and "not scored" in plain
    assert "python" in plain
    d = to_dict(r)
    assert d["overall"] == 84 and "writing_advice" in d and "jd_match" not in d
    assert json.loads(render_json(r))["ats"]["score"] == 84

    print("report selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
