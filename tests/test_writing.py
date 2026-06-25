"""Writing advice (V1): filler + AI tells. Advisory only — no spelling/grammar."""

from ats_score.extract import Document
from ats_score.writing import check_writing


def doc(text):
    return Document(text=text, fmt="pdf", source=None)  # type: ignore[arg-type]


def test_clean_text_has_no_advice():
    r = check_writing(doc("Developed scalable Python pipelines processing 50000 records."))
    assert r.fillers == 0 and r.ai_tells == 0


def test_fillers_and_ai_tells_detected():
    r = check_writing(doc(
        "In order to delve into the work — using vibrant skills 🚀 with the goal "
        "of growth. As an AI, I hope this helps."))
    assert r.fillers >= 2          # in order to, with the goal of
    assert r.ai_tells >= 4         # em dash, delve, vibrant, emoji, as an ai


def test_date_ranges_not_flagged():
    assert check_writing(doc("Engineer 2023 – 2024.")).ai_tells == 0
    assert check_writing(doc("Worked Jan '21 — Sep '25 on data.")).ai_tells == 0
    assert check_writing(doc("Project Aug — Sep shipped.")).ai_tells == 0


def test_copula_and_negative_parallelism():
    assert check_writing(doc("The role serves as a foundation.")).ai_tells >= 1
    assert check_writing(doc("Not just a coder but a leader.")).ai_tells >= 1


def test_spelling_and_grammar_removed_in_v1():
    # A typo and a repeated word are NOT flagged anymore.
    r = check_writing(doc("Managed teh the project budget."))
    assert r.fillers == 0 and r.ai_tells == 0
