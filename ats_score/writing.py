"""Writing checks: spelling, filler phrases, and AI-generated tells.

Operates on a Document's text. Returns a 0-100 sub-score plus per-line findings.
Wordlists are kept conservative on purpose: a resume scorer that flags normal
words ("enhance", "leverage", a date en-dash) is noise, not signal.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from functools import lru_cache

from .extract import Document
from .checks_ats import Finding, EMAIL
from .paths import bundled_path

# --- spelling ---------------------------------------------------------------
# Only fully-lowercase word tokens are spell-checked. Capitalized words
# (names, companies, tech like "Python"/"AWS") and anything with digits are
# skipped — that removes the bulk of false positives without a huge dictionary.
_URL = re.compile(r"https?://\S+|www\.\S+|\b[\w./-]+\.(?:com|io|dev|org|net|ai|co)\b", re.I)
_STRIP = string.punctuation + "•·–—‣⁃◦"
# Lowercase tech/resume terms a general dictionary doesn't know but are correct.
SPELL_ALLOW = {
    "devops", "fullstack", "frontend", "backend", "microservices", "kubernetes",
    "dockerfile", "kubectl", "nginx", "postgres", "postgresql", "mysql",
    "mongodb", "redis", "sql", "nosql", "graphql", "restful", "api", "apis",
    "sdk", "json", "yaml", "html", "css", "javascript", "typescript", "nodejs",
    "async", "asyncio", "numpy", "pandas", "matplotlib", "pytorch", "scikit",
    "sklearn", "tensorflow", "etl", "elt", "dbt", "airflow", "kafka", "spark",
    "snowflake", "redshift", "tableau", "powerbi", "kpis", "saas", "ci", "cd",
    "oauth", "jwt", "ssl", "tls", "linux", "ubuntu", "bash", "cron", "ansible",
    "terraform", "github", "gitlab", "bitbucket", "jira", "agile", "scrum",
    "ux", "ui", "frontend", "onboarding", "upselling", "stakeholder",
    "stakeholders", "analytics", "dataset", "datasets", "dashboards",
    "scalable", "performant", "realtime", "url", "urls", "cli", "regex",
    # modern compounds a 370k general list still misses (plurals via morphology)
    "workflow", "walkthrough", "heatmap", "roadmap", "dropdown", "login",
    "signup", "webpage", "website", "codebase", "toolkit", "dashboard",
    "dataframe", "hostname", "runtime", "uptime", "downtime", "namespace",
    "middleware", "changelog", "lifecycle", "chatbot", "plugin", "blockchain",
    "crypto", "fintech", "ecommerce", "webhook", "endpoint", "endpoints",
    "boilerplate", "scraping", "wireframe", "wireframes",
}

# --- filler / hedging -------------------------------------------------------
FILLERS = {
    "in order to": "to",
    "due to the fact that": "because",
    "at this point in time": "now",
    "in the event that": "if",
    "has the ability to": "can",
    "have the ability to": "can",
    "it is important to note": "(drop it)",
    "for the purpose of": "for",
    "with the goal of": "to",
    "a wide range of": "many",
    "in terms of": "(rephrase)",
}
HEDGES = ("could potentially", "might possibly", "may be able to", "sort of",
          "kind of", "more or less")

# --- AI tells ---------------------------------------------------------------
# Conservative AI-vocabulary: words rarely legitimate on a resume. Deliberately
# excludes enhance/leverage/robust/seamless — common, valid resume words.
AI_VOCAB = {
    "delve", "tapestry", "testament", "vibrant", "underscore", "underscores",
    "intricate", "interplay", "realm", "myriad", "plethora", "embark",
    "multifaceted", "nuanced", "showcasing", "pivotal", "burgeoning",
}
COPULA = ("serves as", "stands as", "boasts a", "boasts an", "acts as a")
# Em dash + double/spaced hyphen used as punctuation. En dash (–) is NOT
# flagged: on resumes it almost always means a date range ("2023 – 2024").
_EMDASH = re.compile(r"—|\s--\s|\s—\s")
# A dash between two dates is a range separator, not an AI tell — and people use
# em dashes for it as often as en dashes. A "date side" is a month, a year, a
# month+year, or present/now, so this covers "Jan '21 — Sep '25", "2023 —
# Present", and "Aug — Sep". Both sides must be date-like, so a prose em dash
# ("the team — delivering results") is still flagged.
_MONTH = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?")
_DATE_SIDE = rf"(?:{_MONTH}\s+)?'?\d{{2,4}}|{_MONTH}|present|current|now"
_DATE_RANGE = re.compile(rf"(?:{_DATE_SIDE})\s*[—–-]\s*(?:{_DATE_SIDE})", re.I)
_CURLY = re.compile(r"[‘’“”]")
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F000-\U0001F0FF\U00002600-\U000027BF⬀-⯿]")


@dataclass
class WritingResult:
    score: int
    findings: list[Finding]
    typos: int = 0
    fillers: int = 0
    ai_tells: int = 0

    @property
    def summary(self) -> str:
        return f"{self.typos} typos · {self.fillers} fillers · {self.ai_tells} AI-tells"


@lru_cache(maxsize=1)
def _speller():
    from spellchecker import SpellChecker
    # distance=2 catches transpositions (recieve -> receive). Augment the small
    # default dictionary with a 370k-word English list + tech terms so domain
    # vocabulary isn't flagged as misspelled.
    s = SpellChecker(distance=2)
    wordfile = bundled_path("data/words_alpha.txt")
    if wordfile.exists():
        s.word_frequency.load_text_file(str(wordfile))
    s.word_frequency.load_words(SPELL_ALLOW)
    return s


def _candidates(line: str):
    """Lowercase, hyphen-free, URL-free word tokens worth spell-checking."""
    line = _URL.sub(" ", line)
    for raw in line.split():
        if any(c in raw for c in "-/.@_"):
            continue  # hyphenated compound, URL, path, or handle
        t = raw.strip(_STRIP)
        if len(t) >= 3 and t.isascii() and t.isalpha() and t.islower():
            yield t


def _known(spell, w: str) -> bool:
    return not spell.unknown([w])


def _is_typo(spell, w: str) -> bool:
    if w in SPELL_ALLOW or _known(spell, w):
        return False
    # Tolerate morphological variants of a known word (the dictionary lacks many
    # plurals/verb forms/British spellings, which would otherwise be false hits).
    stems = []
    for suf, cut in (("s", 1), ("es", 2), ("ed", 2), ("ing", 3), ("er", 2), ("ly", 2)):
        if w.endswith(suf) and len(w) - cut >= 3:
            stems.append(w[:-cut])
    if w.endswith("ies") and len(w) > 4:
        stems.append(w[:-3] + "y")  # companies -> company, currencies -> currency
    brit = w.replace("isation", "ization").replace("ise", "ize").replace("our", "or")
    if brit != w:
        stems.append(brit)
    return not any(_known(spell, s) for s in stems)


def _spell_findings(text: str) -> tuple[int, list[Finding]]:
    spell = _speller()
    findings: list[Finding] = []
    seen: set[str] = set()
    count = 0
    for ln, line in enumerate(text.splitlines(), start=1):
        if EMAIL.search(line):
            continue  # don't spell-check emails/handles
        for w in _candidates(line):
            if w in seen or not _is_typo(spell, w):
                continue
            seen.add(w)
            count += 1
            fix = spell.correction(w)
            tip = f" → {fix}" if fix and fix != w else ""
            findings.append(Finding("warn", f'line {ln}: "{w}"{tip}', 2))
    return count, findings


def check_writing(doc: Document) -> WritingResult:
    text = doc.text
    low = text.lower()
    findings: list[Finding] = []

    typos, spell_f = _spell_findings(text)
    findings.extend(spell_f[:15])  # cap spelling noise in the report

    fillers = 0
    for phrase, fix in FILLERS.items():
        for _ in re.finditer(re.escape(phrase), low):
            fillers += 1
            findings.append(Finding("warn", f'filler "{phrase}" → {fix}', 2))
    for h in HEDGES:
        if h in low:
            fillers += 1
            findings.append(Finding("warn", f'hedging "{h}"', 2))

    ai = 0
    for ln, line in enumerate(text.splitlines(), start=1):
        ll = line.lower()
        if _EMDASH.search(line) and not _DATE_RANGE.search(line):
            ai += 1
            findings.append(Finding("warn", f"line {ln}: em dash / double hyphen", 3))
        if _CURLY.search(line):
            ai += 1
            findings.append(Finding("warn", f"line {ln}: curly quotes", 2))
        if _EMOJI.search(line):
            ai += 1
            findings.append(Finding("warn", f"line {ln}: emoji", 3))
        for w in AI_VOCAB:
            if re.search(rf"\b{w}\b", ll):
                ai += 1
                findings.append(Finding("warn", f'line {ln}: AI vocab "{w}"', 3))
        for c in COPULA:
            if c in ll:
                ai += 1
                findings.append(Finding("warn", f'line {ln}: "{c}" (copula avoidance)', 2))

    penalty = (min(20, typos * 2) + min(10, fillers * 2) + min(15, ai * 3))
    score = max(0, 100 - penalty)
    return WritingResult(score=score, findings=findings,
                         typos=typos, fillers=fillers, ai_tells=ai)


def _selfcheck() -> None:
    clean = Document(
        text="Developed scalable Python pipelines processing 50000 records daily.",
        fmt="pdf", source=None)  # type: ignore[arg-type]
    c = check_writing(clean)
    assert c.typos == 0 and c.fillers == 0 and c.ai_tells == 0, vars(c)
    assert c.score == 100, c.score

    bad = Document(
        text=("In order to delve into the experiance, I worked — using vibrant "
              "skills 🚀 with the goal of growth.\n"
              "the award i recieved in 2024."),
        fmt="pdf", source=None)  # type: ignore[arg-type]
    b = check_writing(bad)
    assert b.typos >= 2, b.typos                # experiance, recieved
    assert b.fillers >= 2, b.fillers            # in order to, with the goal of
    assert b.ai_tells >= 3, b.ai_tells          # em dash, vibrant, emoji
    assert b.score < c.score

    # En dash in a date range must NOT be flagged.
    dr = check_writing(Document(text="Engineer 2023 – 2024 built systems.",
                                fmt="pdf", source=None))  # type: ignore[arg-type]
    assert dr.ai_tells == 0, dr.ai_tells

    # Em-dash date ranges (month+year, month-only, to-present) are separators,
    # not AI tells.
    for rng in ("Jan '21 — Sep '25", "Project Aug — Sep", "Engineer 2023 — Present"):
        rr = check_writing(Document(text=rng, fmt="pdf", source=None))  # type: ignore[arg-type]
        assert rr.ai_tells == 0, (rng, rr.ai_tells)
    # But a prose em dash is still an AI tell.
    pe = check_writing(Document(text="The team — delivering great results.",
                                fmt="pdf", source=None))  # type: ignore[arg-type]
    assert pe.ai_tells == 1, pe.ai_tells

    # "Python" capitalized is not a typo.
    cap = check_writing(Document(text="Built APIs with Python and AWS Lambda.",
                                 fmt="pdf", source=None))  # type: ignore[arg-type]
    assert cap.typos == 0, vars(cap)

    print("writing selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
