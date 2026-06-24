"""Writing checks: spelling precision, fillers, AI tells."""

from ats_score.extract import Document
from ats_score.writing import check_writing


def doc(text):
    return Document(text=text, fmt="pdf", source=None)  # type: ignore[arg-type]


def test_clean_text_is_perfect():
    r = check_writing(doc("Developed scalable Python pipelines processing 50000 records."))
    assert r.typos == 0 and r.fillers == 0 and r.ai_tells == 0 and r.score == 100


def test_typos_fillers_and_ai_tells_detected():
    r = check_writing(doc(
        "In order to delve into the experiance, I worked — using vibrant skills "
        "🚀 with the goal of growth.\nthe award i recieved in 2024."))
    assert r.typos >= 2          # experiance, recieved
    assert r.fillers >= 2        # in order to, with the goal of
    assert r.ai_tells >= 3       # em dash, vibrant, emoji
    assert r.score < 100


def test_date_en_dash_not_flagged():
    assert check_writing(doc("Engineer 2023 – 2024 built systems.")).ai_tells == 0


def test_capitalized_tech_not_a_typo():
    assert check_writing(doc("Built APIs with Python and AWS Lambda.")).typos == 0


def test_british_spelling_tolerated():
    # "optimise"/"colour" are valid, must not be flagged as typos.
    assert check_writing(doc("Optimised colour rendering and behaviour.")).typos == 0
