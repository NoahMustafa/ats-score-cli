"""Writing advice: filler phrases and AI-generated tells.

V1 scope: this is *advice only* — it does not affect the overall score (which is
ATS-readiness). It flags wordy filler and tell-tale signs of AI-generated text
(em dashes, emojis, AI vocabulary, copula avoidance, chatbot paste artifacts) so
the applicant can clean them up. Spelling and grammar checking were removed in
V1: they were low-signal and noisy.

Lists are kept conservative on purpose — a resume flagging normal words
("enhance", "leverage", a date en-dash) is noise, not signal. The AI vocabulary
and phrasing patterns are drawn from Wikipedia's "Signs of AI writing".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import Document
from .checks_ats import Finding

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
    "when it comes to": "(rephrase)",
    "the fact of the matter": "(drop it)",
    "needless to say": "(drop it)",
    "it goes without saying": "(drop it)",
}
HEDGES = ("could potentially", "might possibly", "may be able to", "sort of",
          "kind of", "more or less", "it could be argued", "arguably")
# "Persuasive authority" framing — ceremony that adds no information.
AUTHORITY = ("the real question is", "at its core", "what really matters",
             "the heart of the matter", "the deeper issue")

# --- AI tells ---------------------------------------------------------------
# Conservative AI-vocabulary: words rarely legitimate on a resume. Deliberately
# excludes enhance/leverage/robust/seamless/dynamic/innovative — common, valid
# resume words. Source: Wikipedia "Signs of AI writing" (§4, §7).
AI_VOCAB = {
    "delve", "tapestry", "testament", "vibrant", "underscore", "underscores",
    "intricate", "intricacies", "interplay", "realm", "myriad", "plethora",
    "embark", "multifaceted", "nuanced", "showcasing", "showcase", "showcases",
    "pivotal", "burgeoning", "garner", "garnered", "fostering", "exemplifies",
    "groundbreaking", "renowned", "boasts", "nestled", "enduring", "indelible",
    "unparalleled", "unwavering", "transformative", "trailblazing", "bustling",
    "captivating",
}
COPULA = ("serves as", "stands as", "boasts a", "boasts an", "acts as a",
          "represents a")
# Chatbot paste artifacts — if any of these survive into a resume, it was almost
# certainly copied straight out of an AI chat. High-confidence tell.
CHATBOT = ("as an ai", "as a language model", "i hope this helps",
           "let me know if", "feel free to reach", "here is a", "here's a",
           "great question", "as of my last", "i cannot provide")
# Negative parallelism: "not just X but Y", "not only ... but also".
_NEGPAR = re.compile(r"\bnot (?:just|only|merely)\b[^.\n]{0,50}\bbut\b", re.I)

# Em dash + double/spaced hyphen used as punctuation. En dash (–) is NOT
# flagged: on resumes it almost always means a date range.
_EMDASH = re.compile(r"—|\s--\s|\s—\s")
# A dash between two dates is a range separator, not an AI tell. A "date side" is
# a month, a year, a month+year, or present/now ("Jan '21 — Sep '25", "Aug —
# Sep", "2023 — Present"). Both sides date-like, so a prose em dash is still hit.
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_SIDE = rf"(?:{_MONTH}\s+)?'?\d{{2,4}}|{_MONTH}|present|current|now"
_DATE_RANGE = re.compile(rf"(?:{_DATE_SIDE})\s*[—–-]\s*(?:{_DATE_SIDE})", re.I)
_CURLY = re.compile(r"[‘’“”]")
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F000-\U0001F0FF\U00002600-\U000027BF⬀-⯿]")


@dataclass
class WritingResult:
    """Advisory only — these counts do NOT feed the overall score."""
    findings: list[Finding]
    fillers: int = 0
    ai_tells: int = 0

    @property
    def total(self) -> int:
        return self.fillers + self.ai_tells

    @property
    def summary(self) -> str:
        return f"{self.fillers} filler · {self.ai_tells} AI-tells (advice only)"


def check_writing(doc: Document) -> WritingResult:
    text = doc.text
    low = text.lower()
    findings: list[Finding] = []

    fillers = 0
    for phrase, fix in FILLERS.items():
        for _ in re.finditer(re.escape(phrase), low):
            fillers += 1
            findings.append(Finding("warn", f'filler "{phrase}" → {fix}', 0))
    for h in HEDGES + AUTHORITY:
        if h in low:
            fillers += 1
            findings.append(Finding("warn", f'wordy "{h}"', 0))

    ai = 0
    for ln, line in enumerate(text.splitlines(), start=1):
        ll = line.lower()
        if _EMDASH.search(line) and not _DATE_RANGE.search(line):
            ai += 1
            findings.append(Finding("warn", f"line {ln}: em dash / double hyphen (replace with a comma or period)", 0))
        if _CURLY.search(line):
            ai += 1
            findings.append(Finding("warn", f'line {ln}: curly quotes (use straight quotes)', 0))
        if _EMOJI.search(line):
            ai += 1
            findings.append(Finding("warn", f"line {ln}: emoji (remove)", 0))
        if _NEGPAR.search(line):
            ai += 1
            findings.append(Finding("warn", f'line {ln}: "not just … but" phrasing (rewrite plainly)', 0))
        for w in AI_VOCAB:
            if re.search(rf"\b{w}\b", ll):
                ai += 1
                findings.append(Finding("warn", f'line {ln}: AI vocab "{w}"', 0))
        for c in COPULA:
            if c in ll:
                ai += 1
                findings.append(Finding("warn", f'line {ln}: "{c}" (use "is"/"has")', 0))
        for c in CHATBOT:
            if c in ll:
                ai += 1
                findings.append(Finding("warn", f'line {ln}: chatbot artifact "{c}" (delete)', 0))

    return WritingResult(findings=findings, fillers=fillers, ai_tells=ai)


def _selfcheck() -> None:
    clean = Document(
        text="Developed scalable Python pipelines processing 50000 records daily.",
        fmt="pdf", source=None)  # type: ignore[arg-type]
    c = check_writing(clean)
    assert c.fillers == 0 and c.ai_tells == 0, vars(c)

    bad = Document(
        text=("In order to delve into the experience, I worked — using vibrant "
              "skills 🚀 with the goal of growth. As an AI, I hope this helps.\n"
              "The role serves as a testament to my work."),
        fmt="pdf", source=None)  # type: ignore[arg-type]
    b = check_writing(bad)
    assert b.fillers >= 2, b.fillers            # in order to, with the goal of
    assert b.ai_tells >= 5, vars(b)             # em dash, vibrant, emoji, delve, as an ai, serves as, testament

    # En/em dash in a date range must NOT be flagged.
    for rng in ("Engineer 2023 – 2024.", "Jan '21 — Sep '25", "Project Aug — Sep"):
        assert check_writing(Document(text=rng, fmt="pdf", source=None)).ai_tells == 0, rng  # type: ignore[arg-type]

    # Spelling/grammar are gone in V1: a typo is not flagged here.
    typo = check_writing(Document(text="Managed teh project budget.",
                                  fmt="pdf", source=None))  # type: ignore[arg-type]
    assert typo.ai_tells == 0 and typo.fillers == 0, vars(typo)

    print("writing selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
