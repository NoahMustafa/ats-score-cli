"""ATS-readiness checks: can an applicant tracking system parse this resume.

Operates on a Document from extract.py. Returns a 0-100 sub-score plus a list
of findings (severity + message), where the deterministic, actionable signal
lives. Scoring = start at 100, subtract a penalty per failed check, clamp to 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import Document

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

# Section -> heading keywords. Contact is handled separately via email/phone,
# since resumes rarely print a literal "Contact" heading.
SECTION_KEYWORDS = {
    "Summary": ("summary", "profile", "objective", "about"),
    "Experience": ("experience", "employment", "work history"),
    "Education": ("education", "academic"),
    "Skills": ("skills", "competencies", "technologies"),
}

# Month-Year vs numeric date styles, to spot mixed formatting.
_DATE_WORD = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}\b",
    re.I,
)
_DATE_NUM = re.compile(r"\b\d{1,2}[/-]\d{4}\b")


@dataclass
class Finding:
    severity: str   # "fail" | "warn"
    message: str
    penalty: int


@dataclass
class AtsResult:
    score: int
    findings: list[Finding]

    @property
    def summary(self) -> str:
        return " · ".join(f.message for f in self.findings) or "no issues"


def _is_heading(line: str) -> bool:
    # A heading is a short line, no sentence punctuation, mostly letters. Keeps
    # body text like "hands-on experience" from counting as an Experience header.
    line = line.strip()
    return 0 < len(line) <= 40 and not line.endswith((".", ",", ";")) and \
        sum(c.isalpha() or c.isspace() or c in "&/-" for c in line) >= len(line) - 1


def _sections_present(text: str) -> set[str]:
    headings = [ln for ln in text.splitlines() if _is_heading(ln)]
    found: set[str] = set()
    for section, keywords in SECTION_KEYWORDS.items():
        for h in headings:
            low = h.lower()
            if any(k in low for k in keywords):
                found.add(section)
                break
    return found


def _date_consistent(text: str) -> bool:
    has_word = bool(_DATE_WORD.search(text))
    has_num = bool(_DATE_NUM.search(text))
    # Mixed "Jan 2024" and "01/2024" styles read as inconsistent.
    return not (has_word and has_num)


def check_ats(doc: Document) -> AtsResult:
    findings: list[Finding] = []

    if doc.is_scanned or len(doc.text) < 100:
        findings.append(Finding("fail", "not machine-readable (scanned/empty)", 40))

    if doc.has_tables:
        findings.append(Finding("fail", "tables present (ATS may garble)", 12))
    if doc.has_columns:
        findings.append(Finding("fail", "multi-column layout", 12))
    if doc.has_images:
        findings.append(Finding("warn", "images present", 5))

    present = _sections_present(doc.text)
    missing = [s for s in SECTION_KEYWORDS if s not in present]
    for s in missing:
        findings.append(Finding("warn", f"missing section: {s}", 8))

    if not EMAIL.search(doc.text):
        findings.append(Finding("fail", "no email found", 10))
    if not PHONE.search(doc.text):
        findings.append(Finding("warn", "no phone found", 5))

    if not _date_consistent(doc.text):
        findings.append(Finding("warn", "inconsistent date formats", 5))

    score = max(0, 100 - sum(f.penalty for f in findings))
    return AtsResult(score=score, findings=findings)


def _selfcheck() -> None:
    good = Document(
        text=(
            "Jane Doe\njane@example.com  +1 555 123 4567\n"
            "SUMMARY\nData engineer.\n"
            "WORK EXPERIENCE\nBuilt pipelines Jan 2024 - Mar 2024.\n"
            "EDUCATION\nBSc CS\n"
            "TECHNICAL SKILLS\nPython, SQL\n"
        ),
        fmt="pdf", source=None,  # type: ignore[arg-type]
    )
    r = check_ats(good)
    assert r.score >= 90, (r.score, r.summary)

    scanned = Document(text="", fmt="pdf", source=None, is_scanned=True)  # type: ignore[arg-type]
    assert check_ats(scanned).score <= 60, check_ats(scanned).score

    bad = Document(
        text="Some resume text with enough length " * 5 + " no contact here",
        fmt="pdf", source=None, has_tables=True, has_columns=True,  # type: ignore[arg-type]
    )
    rb = check_ats(bad)
    assert rb.score < r.score
    assert any("email" in f.message for f in rb.findings)

    print("checks_ats selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
