"""Orchestration: run every check, weight the sub-scores, return one Report.

All scoring logic lives here so the CLI stays a thin wrapper. JD-match is
optional — it only runs when a job description is supplied. Without one, the
report instead lists the skills the parser could read (a readback, not a score).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .extract import extract, Document
from .checks_ats import check_ats, AtsResult
from .checks_content import check_content, ContentResult
from .writing import check_writing, WritingResult
from .similarity import check_similarity, detect_skills, SimilarityResult

# ATS-readiness weighted highest: a resume the machine can't parse fails before
# content or wording matter. Weights per branch sum to 1.0.
WEIGHTS = {"ats": 0.40, "content": 0.35, "writing": 0.25}
WEIGHTS_JD = {"ats": 0.30, "content": 0.25, "writing": 0.20, "jd": 0.25}


@dataclass
class Report:
    overall: int
    ats: AtsResult
    content: ContentResult
    writing: WritingResult
    similarity: SimilarityResult | None = None   # only when a JD is given
    detected_skills: list[str] = field(default_factory=list)  # only when no JD
    warnings: list[str] = field(default_factory=list)
    source: str = ""


def _read_jd(jd: str | Path) -> str:
    p = Path(jd)
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    return str(jd)  # allow passing the JD text directly


def score(resume_path: str | Path, jd_path: str | Path | None = None) -> Report:
    doc: Document = extract(resume_path)

    ats = check_ats(doc)
    content = check_content(doc)
    writing = check_writing(doc)

    sim: SimilarityResult | None = None
    detected: list[str] = []
    if jd_path is not None:
        sim = check_similarity(doc.text, _read_jd(jd_path))
        parts = {"ats": ats.score, "content": content.score,
                 "writing": writing.score, "jd": sim.score}
        overall = round(sum(parts[k] * w for k, w in WEIGHTS_JD.items()))
    else:
        detected = detect_skills(doc.text)
        parts = {"ats": ats.score, "content": content.score,
                 "writing": writing.score}
        overall = round(sum(parts[k] * w for k, w in WEIGHTS.items()))

    return Report(
        overall=overall, ats=ats, content=content, writing=writing,
        similarity=sim, detected_skills=detected, warnings=doc.warnings,
        source=str(resume_path),
    )


def _selfcheck() -> None:
    import tempfile
    import docx

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.docx"
        doc = docx.Document()
        doc.add_paragraph("Jane Doe — jane@example.com — +1 555 123 4567")
        doc.add_paragraph("SUMMARY")
        doc.add_paragraph("Data engineer skilled in Python and SQL.")
        doc.add_paragraph("WORK EXPERIENCE")
        for n in (15, 20, 25, 30):
            doc.add_paragraph(f"• Increased revenue by {n}% across 3 regions.")
        doc.add_paragraph("EDUCATION")
        doc.add_paragraph("BSc Computer Science")
        doc.add_paragraph("TECHNICAL SKILLS")
        doc.add_paragraph("Python, SQL, AWS, Airflow, ETL")
        doc.save(str(p))

        # No JD: 3-way weighting, skills readback present, no similarity.
        r = score(p)
        assert r.similarity is None, "no JD must skip similarity"
        assert r.detected_skills, "no JD should list detected skills"
        assert 0 <= r.overall <= 100, r.overall

        # With JD: similarity present, no readback, 4-way weighting.
        rj = score(p, "Data engineer with python, sql, aws, kubernetes and spark.")
        assert rj.similarity is not None, "JD must produce a similarity result"
        assert not rj.detected_skills, "JD path should not list detected skills"
        assert "kubernetes" in rj.similarity.missing, rj.similarity.missing
        assert 0 <= rj.overall <= 100, rj.overall

    print("core selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
