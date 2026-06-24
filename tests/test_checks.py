"""ATS-readiness + content checks on synthetic Documents (no corpus needed)."""

from ats_score.extract import Document
from ats_score.checks_ats import check_ats
from ats_score.checks_content import check_content


def doc(text, **kw):
    return Document(text=text, fmt="pdf", source=None, **kw)  # type: ignore[arg-type]


GOOD = (
    "Jane Doe\njane@example.com  +1 555 123 4567\n"
    "SUMMARY\nData engineer.\n"
    "WORK EXPERIENCE\nBuilt pipelines Jan 2024 to Mar 2024.\n"
    "EDUCATION\nBSc CS\n"
    "TECHNICAL SKILLS\nPython, SQL\n"
)


def test_ats_clean_resume_scores_high():
    assert check_ats(doc(GOOD)).score >= 90


def test_ats_flags_tables_columns_and_missing_contact():
    r = check_ats(doc("Resume text " * 30, has_tables=True, has_columns=True))
    assert r.score < 90
    msgs = " ".join(f.message for f in r.findings)
    assert "email" in msgs and "table" in msgs and "column" in msgs


def test_ats_scanned_is_not_machine_readable():
    assert check_ats(doc("", is_scanned=True)).score <= 60


def test_ats_email_via_mailto_link_counts():
    d = doc("No address in body. " * 10, links=["mailto:jane@example.com"])
    assert not any("no email" in f.message for f in check_ats(d).findings)


# --- content ---------------------------------------------------------------
EXP = "SUMMARY enough words to clear the length floor. " * 30 + "\nWORK EXPERIENCE\n"


def test_content_quantified_strong_bullets_clean():
    r = check_content(doc(EXP + "\n".join(
        f"• Increased revenue by {n}% across 3 regions." for n in (15, 20, 25))))
    assert r.bullets == 3 and r.unquantified == 0 and r.weak == 0


def test_content_year_is_not_a_metric():
    r = check_content(doc(EXP + "• Built a pipeline in 2024 using Python 3.11."))
    assert r.unquantified == 1


def test_content_weak_verb_flagged():
    assert check_content(doc(EXP + "• Handled support tickets daily.")).weak == 1


def test_content_skills_line_exempt_from_verb_rule():
    r = check_content(doc(
        EXP + "• Cut cost 10%.\nTECHNICAL SKILLS\n• Languages: Python, SQL"))
    assert r.no_verb == 0


def test_content_too_short_fails():
    assert any("too short" in f.message
               for f in check_content(doc("Tiny resume.")).findings)
