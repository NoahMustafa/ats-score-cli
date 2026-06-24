"""End-to-end: JD gating, weighting, report shapes. Builds a DOCX in a tmpdir
so it runs in CI with no resume corpus."""

import json
from pathlib import Path

import docx
import pytest

from ats_score.core import score
from ats_score.report import to_dict, render_json, render, _render_plain


@pytest.fixture
def resume(tmp_path) -> Path:
    p = tmp_path / "r.docx"
    d = docx.Document()
    d.add_paragraph("Jane Doe — jane@example.com — +1 555 123 4567")
    d.add_paragraph("SUMMARY")
    d.add_paragraph("Data engineer skilled in Python and SQL.")
    d.add_paragraph("WORK EXPERIENCE")
    for n in (15, 20, 25, 30):
        d.add_paragraph(f"Increased revenue by {n}% across 3 regions.")
    d.add_paragraph("EDUCATION")
    d.add_paragraph("BSc Computer Science")
    d.add_paragraph("TECHNICAL SKILLS")
    d.add_paragraph("Python, SQL, AWS, Airflow, ETL")
    d.save(str(p))
    return p


def test_no_jd_skips_match_and_lists_skills(resume):
    r = score(resume)
    assert r.similarity is None
    assert r.detected_skills
    assert 0 <= r.overall <= 100


def test_jd_runs_match_and_finds_gap(resume):
    r = score(resume, "Data engineer with python, sql, aws, kubernetes and spark.")
    assert r.similarity is not None
    assert not r.detected_skills
    assert "kubernetes" in r.similarity.missing
    assert 0 <= r.overall <= 100


def test_json_shape_switches_on_jd(resume):
    no_jd = to_dict(score(resume))
    assert "detected_skills" in no_jd and "jd_match" not in no_jd
    with_jd = to_dict(score(resume, "python kubernetes"))
    assert "jd_match" in with_jd and "detected_skills" not in with_jd
    # render_json must be valid JSON.
    assert json.loads(render_json(score(resume)))["overall"] == no_jd["overall"]


def test_render_is_plain_when_not_a_tty(resume):
    # Captured (non-tty) output must be the plain renderer, no ANSI escapes.
    out = render(score(resume))
    assert "\x1b[" not in out
    assert "Resume score:" in out


def test_unsupported_file_type_rejected(tmp_path):
    p = tmp_path / "resume.txt"
    p.write_text("hi", encoding="utf-8")
    with pytest.raises(ValueError):
        score(p)
