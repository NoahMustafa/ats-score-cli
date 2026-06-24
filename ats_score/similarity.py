"""JD-match: semantic similarity (model2vec) + actionable keyword gap.

The cosine is a fuzzy overall signal; the missing-keywords list is what a user
actually acts on. Both run fully offline from the vendored static model.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .paths import bundled_path

# Common words that aren't skills/keywords — kept out of the gap analysis.
STOP = {
    "the", "and", "for", "with", "you", "our", "are", "will", "have", "has",
    "this", "that", "from", "your", "all", "can", "who", "but", "not", "their",
    "they", "them", "its", "was", "were", "would", "should", "must", "may",
    "ability", "work", "working", "team", "teams", "role", "job", "company",
    "experience", "experienced", "years", "year", "skills", "skill", "strong",
    "knowledge", "including", "etc", "able", "well", "new", "use", "using",
    "across", "within", "into", "per", "via", "such", "also", "more", "most",
    "other", "any", "each", "based", "help", "ensure", "support", "related",
    "required", "preferred", "plus", "responsibilities", "requirements",
    "candidate", "candidates", "looking", "join", "position", "opportunity",
    "environment", "excellent", "good", "great", "high", "highly", "ideal",
    "hiring", "seeking", "apply", "applicant", "applicants", "wanted", "needed",
}

_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,}")


@dataclass
class SimilarityResult:
    score: int
    cosine: float
    coverage: float
    missing: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        miss = ", ".join(self.missing[:8]) if self.missing else "none"
        return f"cosine {self.cosine:.2f} · keyword coverage {self.coverage:.0%} · missing: {miss}"


@lru_cache(maxsize=1)
def _model():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # never hit the network
    from model2vec import StaticModel
    return StaticModel.from_pretrained(str(bundled_path("data/potion-8M")))


def _cosine(a, b) -> float:
    import numpy as np
    emb = _model().encode([a, b])
    na, nb = np.linalg.norm(emb[0]), np.linalg.norm(emb[1])
    if na == 0 or nb == 0:
        return 0.0
    return float(emb[0] @ emb[1] / (na * nb))


def _keywords(text: str) -> tuple[set[str], dict[str, int]]:
    """Clean content keywords with JD frequency (punctuation stripped)."""
    grams: dict[str, int] = {}
    for raw in _TOKEN.findall(text.lower()):
        t = raw.strip(".-")  # "python." -> "python", keep node.js / c++ intact
        if len(t) >= 3 and t not in STOP:
            grams[t] = grams.get(t, 0) + 1
    return set(grams), grams


def check_similarity(resume_text: str, jd_text: str) -> SimilarityResult:
    jd_set, jd_freq = _keywords(jd_text)
    resume_set, _ = _keywords(resume_text)

    matched = jd_set & resume_set
    missing = jd_set - resume_set
    # Rank missing by JD frequency, then by length (specific terms first).
    missing_clean = sorted(missing, key=lambda k: (-jd_freq[k], -len(k)))

    coverage = len(matched) / len(jd_set) if jd_set else 0.0
    cosine = _cosine(resume_text, jd_text)
    # Hybrid: semantic + keyword coverage. Cosine dominates overall fit;
    # coverage grounds it in concrete term overlap.
    score = max(0, min(100, round(100 * (0.55 * cosine + 0.45 * coverage))))

    return SimilarityResult(
        score=score, cosine=round(cosine, 3), coverage=round(coverage, 3),
        missing=missing_clean[:15], matched=sorted(matched)[:15],
    )


def _selfcheck() -> None:
    resume = ("Data engineer skilled in Python, SQL, Airflow and AWS. Built ETL "
              "pipelines and dashboards with PostgreSQL and Power BI.")
    jd_same = resume
    r1 = check_similarity(resume, jd_same)
    assert r1.cosine > 0.95, r1.cosine
    assert r1.coverage > 0.95, r1.coverage
    assert r1.score >= 95, r1.score

    jd = ("Looking for a data engineer with Python, Kubernetes, GraphQL and "
          "Spark experience to build streaming pipelines.")
    r2 = check_similarity(resume, jd)
    assert "kubernetes" in r2.missing, r2.missing
    assert "graphql" in r2.missing, r2.missing
    assert "python" not in r2.missing, r2.missing  # present in resume

    unrelated = "Pastry chef creating desserts, cakes and breads in a busy kitchen."
    r3 = check_similarity(resume, unrelated)
    assert r3.cosine < r1.cosine
    assert r3.score < r2.score

    print("similarity selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
