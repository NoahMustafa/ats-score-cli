"""JD-match: semantic similarity (model2vec) + a real skills gap.

Skills are matched against a vendored cross-domain taxonomy (ESCO + tech
terms), so the gap reports actual missing *skills* (e.g. "azure", "food
safety") rather than JD prose ("ingestion", "collaboration"). The cosine is a
fuzzy overall signal; the missing-skills list is what a user acts on. Fully
offline.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .paths import bundled_path

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]*")

# British -> American so JD "modelling/optimisation" matches the taxonomy.
_BRIT = {
    "modelling": "modeling", "modelled": "modeled", "labelling": "labeling",
    "travelling": "traveling", "cancelled": "canceled", "catalogue": "catalog",
}


def _normalize_word(t: str) -> str:
    t = t.strip(".-")
    if t in _BRIT:
        return _BRIT[t]
    if t.endswith("isation"):
        return t[:-7] + "ization"
    if t.endswith("ised"):
        return t[:-4] + "ized"
    if t.endswith("ising"):
        return t[:-5] + "izing"
    if t.endswith("ise") and len(t) > 5:
        return t[:-3] + "ize"
    return t


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
        return (f"cosine {self.cosine:.2f} · skill coverage {self.coverage:.0%} "
                f"· missing: {miss}")


# Lone ESCO entries that are generic English, not distinguishing skills. They
# only cause noise ("retrieval" from "retrieval layers", "clean" from "clean
# pipelines"). Real single-word skills (python, azure, accounting) are kept.
_GENERIC = {
    "clean", "retrieval", "access", "absorb", "accompany", "basic", "general",
    "various", "additional", "relevant", "related", "current", "daily",
    "overall", "support", "deliver", "provide", "obtain", "perform", "process",
    "handle", "prepare", "maintain", "operate", "assist", "monitor", "review",
    "control", "report", "record", "collect", "follow", "complete", "identify",
    "achieve", "apply", "adopt", "advise", "arrange", "attend", "assess",
    "balance", "build", "carry", "check", "clear", "close", "conduct", "create",
}


@lru_cache(maxsize=1)
def _gazetteer() -> frozenset[str]:
    text = bundled_path("data/skills.txt").read_text(encoding="utf-8")
    return frozenset(
        line for line in text.splitlines()
        if line and not (" " not in line and line in _GENERIC)
    )


@lru_cache(maxsize=1)
def _model():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # never hit the network
    from model2vec import StaticModel
    return StaticModel.from_pretrained(str(bundled_path("data/potion-8M")))


def _cosine(a: str, b: str) -> float:
    import numpy as np
    emb = _model().encode([a, b])
    na, nb = np.linalg.norm(emb[0]), np.linalg.norm(emb[1])
    if na == 0 or nb == 0:
        return 0.0
    return float(emb[0] @ emb[1] / (na * nb))


def _skills(text: str) -> set[str]:
    """Skills present in text = its 1-4 word n-grams that are in the taxonomy."""
    toks = [_normalize_word(w.lower()) for w in _WORD.findall(text)]
    toks = [t for t in toks if t]
    gaz = _gazetteer()
    found: set[str] = set()
    n = len(toks)
    for i in range(n):
        for k in range(1, 5):
            if i + k <= n:
                gram = " ".join(toks[i:i + k])
                if gram in gaz:
                    found.add(gram)
    # Drop a single-word skill already covered by a matched multi-word skill
    # ("learning" when "machine learning" matched).
    multi = [s for s in found if " " in s]
    return {s for s in found
            if " " in s or not any(s in m.split() for m in multi)}


def detect_skills(text: str, limit: int = 12) -> list[str]:
    """Skills the parser can read in a resume (no JD). A readback, not a score:
    if a headline skill is missing here, the resume's formatting hid it.
    Ranked specific-first (multi-word before single)."""
    found = _skills(text)
    return sorted(found, key=lambda s: (-len(s.split()), s))[:limit]


def check_similarity(resume_text: str, jd_text: str) -> SimilarityResult:
    jd_skills = _skills(jd_text)
    resume_skills = _skills(resume_text)

    matched = jd_skills & resume_skills
    missing = jd_skills - resume_skills
    # Specific (multi-word) skills first, then longer.
    missing_ranked = sorted(missing, key=lambda s: (-len(s.split()), -len(s)))

    coverage = len(matched) / len(jd_skills) if jd_skills else 0.0
    cosine = _cosine(resume_text, jd_text)
    score = max(0, min(100, round(100 * (0.5 * cosine + 0.5 * coverage))))

    return SimilarityResult(
        score=score, cosine=round(cosine, 3), coverage=round(coverage, 3),
        missing=missing_ranked[:15],
        matched=sorted(matched, key=lambda s: (-len(s.split()), s))[:15],
    )


def _selfcheck() -> None:
    resume = ("Data engineer skilled in python, sql, airflow and aws. Built etl "
              "pipelines and dashboards with postgresql and power bi.")
    r1 = check_similarity(resume, resume)
    assert r1.coverage > 0.95, r1.coverage
    assert r1.score >= 90, r1.score

    jd = ("Data engineer needed with python, kubernetes, spark and azure. "
          "Build streaming pipelines and data modeling.")
    r2 = check_similarity(resume, jd)
    assert "kubernetes" in r2.missing, r2.missing
    assert "azure" in r2.missing, r2.missing
    assert "python" not in r2.missing, r2.missing  # present in resume
    # JD prose must NOT appear as a skill.
    assert not any(w in r2.missing for w in ("ingestion", "build", "needed")), r2.missing

    unrelated = "Pastry chef creating desserts, cakes and breads in a busy kitchen."
    r3 = check_similarity(resume, unrelated)
    assert r3.cosine < r1.cosine
    assert r3.score < r2.score

    # British spelling normalized against the taxonomy.
    r4 = check_similarity("skilled in data modeling", "need data modelling")
    assert "modelling" not in r4.missing, r4.missing

    print("similarity selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
