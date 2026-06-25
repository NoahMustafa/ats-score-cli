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


# "Met" threshold for a prose requirement's best semantic match against the
# resume. Static embeddings (potion-8M) compress cosine into a ~0.3–0.6 band, so
# this is calibrated, not absolute: on real JDs a matching role's requirements
# cluster ≥0.50 while a mismatched role's sit ≤0.40. Tune here if the model
# changes.
_TAU = 0.50


@dataclass
class SimilarityResult:
    score: int
    skill_coverage: float           # Tier 1: named JD skills found in resume
    prose_coverage: float           # Tier 2: JD prose requirements covered
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)   # hard skill gap (Tier 1)
    weak: list[str] = field(default_factory=list)       # prose reqs not covered (Tier 2)

    @property
    def summary(self) -> str:
        miss = ", ".join(self.missing[:6]) if self.missing else "none"
        return (f"skill coverage {self.skill_coverage:.0%} · requirement "
                f"coverage {self.prose_coverage:.0%} · missing: {miss}")


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
    # single English words ESCO lists as "skills" but that are noise on a resume
    # ("re", "scale", "source" from prose; "design"/"engineering" matter only as
    # multi-word phrases like "responsive design"/"data engineering").
    "re", "scale", "source", "design", "engineering", "reporting", "sales",
    "research", "planning", "testing", "writing", "teaching", "training",
    "data", "management", "development", "systems", "solutions", "operations",
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


def _max_sims(queries: list[str], corpus: list[str]):
    """For each query, the best cosine against any corpus sentence (Tier 2)."""
    import numpy as np
    m = _model()
    Q = np.asarray(m.encode(queries), dtype="float32")
    C = np.asarray(m.encode(corpus), dtype="float32")
    Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-9
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
    return (Q @ C.T).max(axis=1)


# Split text into clause-sized segments (sentences and bullet lines) for the
# semantic layer. Headers and one-word lines fall out via the min-word filter.
def _segments(text: str, min_words: int) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        for seg in re.split(r"(?<=[.;:])\s+|\s[•·–—|]\s", line):
            seg = seg.strip(" \t•·-–—|")
            if len(seg.split()) >= min_words:
                out.append(seg)
    return out


def _requirements(jd_text: str) -> list[str]:
    """JD prose requirements (responsibility / requirement sentences)."""
    return _segments(jd_text, min_words=5)


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


def detect_skills(text: str, limit: int = 20) -> list[str]:
    """Skills the parser can read in a resume (no JD). A readback, not a score:
    if a headline skill is missing here, the resume's formatting hid it.
    Ranked specific-first (multi-word before single)."""
    found = _skills(text)
    return sorted(found, key=lambda s: (-len(s.split()), s))[:limit]


def check_similarity(resume_text: str, jd_text: str,
                     tau: float = _TAU) -> SimilarityResult:
    """Two-tier JD match.

    Tier 1 (deterministic): how many of the JD's *named skills* the resume has,
    and which are missing — the hard, actionable gap.
    Tier 2 (semantic): how many of the JD's *prose requirements* are covered by
    some resume sentence, via static-embedding max-similarity — catches phrased
    requirements that have no single skill token.
    """
    jd_skills = _skills(jd_text)
    resume_skills = _skills(resume_text)
    matched = jd_skills & resume_skills
    missing = jd_skills - resume_skills
    missing_ranked = sorted(missing, key=lambda s: (-len(s.split()), -len(s)))
    skill_cov = len(matched) / len(jd_skills) if jd_skills else 1.0

    reqs = _requirements(jd_text)
    rsents = _segments(resume_text, min_words=4)
    weak: list[str] = []
    if reqs and rsents:
        sims = _max_sims(reqs, rsents)
        covered = int((sims >= tau).sum())
        prose_cov = covered / len(reqs)
        weak = [r for r, s in sorted(zip(reqs, sims), key=lambda x: x[1])
                if s < tau]
    else:
        prose_cov = 1.0

    # Blend, weighting the hard skill gap higher. Degrade gracefully when the JD
    # has only skills or only prose.
    if jd_skills and reqs:
        score = round(100 * (0.6 * skill_cov + 0.4 * prose_cov))
    elif jd_skills:
        score = round(100 * skill_cov)
    else:
        score = round(100 * prose_cov)

    return SimilarityResult(
        score=max(0, min(100, score)),
        skill_coverage=round(skill_cov, 3), prose_coverage=round(prose_cov, 3),
        matched=sorted(matched, key=lambda s: (-len(s.split()), s))[:15],
        missing=missing_ranked[:15], weak=weak[:8],
    )


def _selfcheck() -> None:
    resume = ("Data engineer skilled in python, sql, airflow and aws. Built etl "
              "pipelines and dashboards with postgresql and power bi.")
    r1 = check_similarity(resume, resume)
    assert r1.skill_coverage > 0.95, r1.skill_coverage
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
    assert r3.score < r2.score, (r3.score, r2.score)
    assert r3.prose_coverage <= r1.prose_coverage

    # British spelling normalized against the taxonomy.
    r4 = check_similarity("skilled in data modeling", "need data modelling")
    assert "modelling" not in r4.missing, r4.missing

    print("similarity selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
