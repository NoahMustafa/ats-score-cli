"""Content-quality checks: action verbs, quantified bullets, length.

Operates on a Document. Returns a 0-100 sub-score plus per-line findings.
The actionable signal is "which bullets are weak / unquantified", not the score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import Document
from .checks_ats import Finding, _is_heading

# Headings whose bullets are achievements (verb/quantification rules apply).
# Bullets under Skills/Summary/Strengths/etc. are exempt.
_ACHIEVEMENT_HEADINGS = ("experience", "employment", "work", "project")
# Other top-level section headings. We only flip the achievement-section flag on
# a *known* section heading — a job title / company line ("Paragone One
# Internship") also looks like a heading but must NOT end the experience section,
# or its bullets go ungraded.
_OTHER_SECTIONS = (
    "education", "skills", "summary", "profile", "objective", "about",
    "certification", "certificate", "award", "honor", "language", "interest",
    "hobbies", "reference", "contact", "competenc", "technolog", "publication",
    "volunteer", "course", "training", "achievement",
)

# Bullet glyphs + numbered list markers, stripped from the line start.
_BULLET = re.compile(r"^\s*(?:[•▪‣⁃◦\-\*·–]|\d+[.)])\s+")
# "Category: items" lines (e.g. skills sections) are not achievement bullets,
# so verb/quantification rules don't apply to them.
_CATEGORY = re.compile(r"^[A-Za-z][\w &/+\-]{0,30}:\s")

# Quantification: a real metric, not a year or version number. Strip those
# first ("Built pipeline in 2024" / "Python 3.11" are NOT achievements), then
# any remaining digit counts (50%, 3 regions, 3,500+ records, 99% uptime).
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_VERSION = re.compile(r"\b\d+(?:\.\d+)+\b")
_DIGIT = re.compile(r"\d")
# Unambiguous magnitude words that count as quantification ("zero critical
# vulnerabilities", "hundreds of records"). Deliberately excludes one-ten,
# which are too noisy ("one of the team").
_WORDNUM = re.compile(
    r"\b(?:zero|dozens?|hundreds?|thousands?|millions?|billions?|"
    r"doubled|tripled|halved)\b", re.I)

# First-word weak verbs (duty-listing, not achievement).
WEAK_VERBS = {
    "responsible", "worked", "helped", "assisted", "participated", "involved",
    "tasked", "handled", "made", "did", "used", "contributed",
}
# Multi-word weak openers checked against the whole bullet start.
WEAK_OPENERS = (
    "responsible for", "duties included", "in charge of", "tasked with",
)
# Strong resume action verbs whose first word should not end in -ed/-ing
# (the heuristic below handles regular verbs; this list covers irregulars +
# common bases so we do not false-flag a real action verb).
STRONG_VERBS = {
    "led", "built", "drove", "ran", "wrote", "grew", "set", "won", "sold",
    "spearheaded", "create", "design", "develop", "build", "lead", "manage",
    "deliver", "launch", "ship", "drive", "own", "boost", "cut", "scale",
    "architect", "automate", "optimize", "reduce", "increase", "improve",
    "deploy", "secure", "harden", "integrate", "analyze", "produce", "achieve",
    "orchestrate", "engineer", "mentor", "found", "establish", "streamline",
}
# Words that clearly aren't a verb start.
_NON_VERB = {
    "the", "a", "an", "this", "that", "these", "those", "our", "my", "their",
    "his", "her", "its", "i", "we", "they", "various", "responsible",
}

_SENIOR = re.compile(r"\b(senior|lead|principal|staff|manager|director|head)\b", re.I)


@dataclass
class ContentResult:
    score: int
    findings: list[Finding]
    bullets: int = 0       # total bullets found
    graded: int = 0        # bullets under Experience/Projects (verb/number rules apply)
    unquantified: int = 0
    weak: int = 0
    no_verb: int = 0

    @property
    def summary(self) -> str:
        return (f"{self.bullets} bullets ({self.graded} graded) · "
                f"{self.unquantified} missing numbers · {self.weak} weak verbs "
                f"· {self.no_verb} no action verb")


def _bullets(text: str) -> list[tuple[int, str, bool]]:
    """Return (line_no, bullet_text, under_experience_section).

    A bullet that wraps across lines is merged into one logical bullet: the
    first word still drives the action-verb check, and the full text drives the
    quantification check (a number in the wrapped part must still count).
    """
    out: list[list] = []
    in_experience = False
    cur: int | None = None   # index of the bullet currently open for wrapping
    for i, line in enumerate(text.splitlines(), start=1):
        # Bullet check first: a short bullet ("• Hi") can otherwise look like a
        # heading and get swallowed.
        if _BULLET.match(line):
            out.append([i, _BULLET.sub("", line).strip(), in_experience])
            cur = len(out) - 1
        elif _is_heading(line):
            cur = None   # a section/title heading closes the open bullet
            low = line.lower()
            if any(k in low for k in _ACHIEVEMENT_HEADINGS):
                in_experience = True
            elif any(k in low for k in _OTHER_SECTIONS):
                in_experience = False
            # else: a job-title / company line — keep the current section state
            # so its bullets stay graded.
        elif cur is not None and line.strip():
            # A plain line right after a bullet is its wrapped continuation.
            out[cur][1] += " " + line.strip()
    return [(ln, txt, exp) for ln, txt, exp in out]


def _is_quantified(bullet: str) -> bool:
    if _WORDNUM.search(bullet):
        return True
    s = _VERSION.sub(" ", bullet)
    s = _YEAR.sub(" ", s)
    return bool(_DIGIT.search(s))


def _first_word(bullet: str) -> str:
    m = re.match(r"[^\w]*([A-Za-z']+)", bullet)
    return m.group(1).lower() if m else ""


def _verb_like(word: str) -> bool:
    return word in STRONG_VERBS or (len(word) > 3 and word.endswith(("ed", "ing")))


def _is_senior(text: str) -> bool:
    # Proxy for experience level: many year tokens (≈ several dated entries) or
    # an explicit senior/lead title. Senior resumes are allowed to run longer.
    years = len(_YEAR.findall(text))
    return years >= 4 or bool(_SENIOR.search(text))


def check_content(doc: Document) -> ContentResult:
    findings: list[Finding] = []
    bullets = _bullets(doc.text)
    words = len(doc.text.split())

    # Only bullets under an experience/project heading get verb/quantification
    # rules, and never "Category: items" lines (skills lists etc.).
    achievements = [
        (ln, b) for ln, b, in_exp in bullets
        if in_exp and not _CATEGORY.match(b)
    ]

    unquantified = weak = no_verb = 0
    for ln, b in achievements:
        low = b.lower()
        if not _is_quantified(b):
            unquantified += 1

        first = _first_word(b)
        opener = next((w for w in WEAK_OPENERS if low.startswith(w)), None)
        if opener or first in WEAK_VERBS:
            weak += 1
            findings.append(Finding(
                "warn", f'line {ln}: weak verb "{opener or first}"', 3))
        elif first in _NON_VERB or not _verb_like(first):
            no_verb += 1
            findings.append(Finding(
                "warn", f'line {ln}: may not start with an action verb ("{first}")', 2))

        if len(b.split()) > 45:
            findings.append(Finding("warn", f"line {ln}: bullet too long", 2))

    if achievements and unquantified:
        # Not every bullet can carry a metric ("Built ETL pipeline in Airflow"
        # is fine). Tolerate ~30% unquantified; penalize only the excess, scaled
        # by ratio — a few bare bullets barely dent the score, a resume with
        # almost no numbers still takes a real hit (cap 15).
        ratio = unquantified / len(achievements)
        penalty = min(15, round(max(0.0, ratio - 0.3) * 25))
        if penalty:
            findings.append(Finding(
                "warn", f"{unquantified}/{len(achievements)} bullets lack numbers",
                penalty))

    long_limit = 1300 if _is_senior(doc.text) else 900
    if words < 200:
        findings.append(Finding("fail", f"too short ({words} words)", 15))
    elif words > long_limit:
        findings.append(Finding("warn", f"too long ({words} words)", 8))

    if not bullets:
        findings.append(Finding("warn", "no bullet points found", 10))

    score = max(0, 100 - sum(f.penalty for f in findings))
    return ContentResult(
        score=score, findings=findings, bullets=len(bullets),
        graded=len(achievements), unquantified=unquantified, weak=weak,
        no_verb=no_verb,
    )


def _selfcheck() -> None:
    # Base text + an experience heading so bullets count as achievements.
    base = "SUMMARY long enough resume text to clear the floor. " * 30
    base += "\nWORK EXPERIENCE\n"

    good = Document(
        text=base + "\n".join(
            f"• Increased revenue by {n}% across 3 regions." for n in (15, 20, 25)
        ),
        fmt="pdf", source=None,  # type: ignore[arg-type]
    )
    g = check_content(good)
    assert g.bullets == 3 and g.unquantified == 0 and g.weak == 0, vars(g)
    assert g.no_verb == 0, vars(g)
    assert g.score >= 90, (g.score, g.summary)

    # Year/version must NOT count as quantified.
    yr = check_content(Document(
        text=base + "• Built a data pipeline in 2024 using Python 3.11.",
        fmt="pdf", source=None))  # type: ignore[arg-type]
    assert yr.unquantified == 1, yr.unquantified

    # Magnitude words count as quantified; "one of the" does not.
    wn = check_content(Document(
        text=base + "• Achieved zero critical vulnerabilities across the farm.",
        fmt="pdf", source=None))  # type: ignore[arg-type]
    assert wn.unquantified == 0, wn.unquantified
    one = check_content(Document(
        text=base + "• Was one of the engineers on the team.",
        fmt="pdf", source=None))  # type: ignore[arg-type]
    assert one.unquantified == 1, one.unquantified

    # Single weak verb anywhere at the start.
    wv = check_content(Document(
        text=base + "• Handled support tickets daily.",
        fmt="pdf", source=None))  # type: ignore[arg-type]
    assert wv.weak == 1, wv.weak

    # Non-verb start flagged (inside experience).
    nv = check_content(Document(
        text=base + "• The project team shipped features.",
        fmt="pdf", source=None))  # type: ignore[arg-type]
    assert nv.no_verb == 1, vars(nv)

    # Skills-section bullets are exempt from verb rules.
    skills = check_content(Document(
        text=base + "• Reduced cost by 10%.\nTECHNICAL SKILLS\n• Languages: Python, SQL",
        fmt="pdf", source=None))  # type: ignore[arg-type]
    assert skills.no_verb == 0, vars(skills)

    # Numbered bullets detected.
    nb = check_content(Document(
        text=base + "1. Designed 4 services.\n2. Reduced latency by 30%.",
        fmt="pdf", source=None))  # type: ignore[arg-type]
    assert nb.bullets == 2, nb.bullets

    # Senior resume allowed to run longer.
    long_txt = "Senior Engineer. " + ("word " * 1100)
    sr = check_content(Document(text=long_txt, fmt="pdf", source=None))  # type: ignore[arg-type]
    assert not any("too long" in f.message for f in sr.findings), sr.summary

    print("checks_content selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
