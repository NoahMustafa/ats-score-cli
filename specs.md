# ATS Score CLI — Spec

A terminal tool that scores a resume for ATS-readiness, writing quality, and (optionally) match against a job description. Enhancv-style checker, but offline and in the terminal. Ships as a single self-contained binary per OS.

## Goal

Given a resume (PDF or DOCX), produce a scored report covering:

1. **ATS-readiness** — can an applicant tracking system parse it.
2. **Content quality** — verbs, quantified bullets, length.
3. **Writing** — typos, filler phrases, AI-generated tells.
4. **JD match** (optional) — semantic + keyword overlap against a job description, with an explicit list of missing skills.

No JD required for checks 1–3. The JD only drives check 4.

## Non-goals (v1)

- No recruiter-side batch ranking of candidates. (See *Future*, and the legal note there — ranking humans for hiring is a regulated surface.)
- No training a custom model. Pretrained, distilled embeddings only.
- No cloud / API calls. Fully offline. Everything bundled in the binary.
- No deep semantic AI-tell detection (significance inflation, rule-of-three). Needs an LLM; out of scope for an offline binary.

## Distribution

- Single self-contained binary per OS: `tool.exe` (Windows), `tool` (Linux/macOS).
- Model weights, dictionaries, and wordlists bundled inside the binary as data files.
- **PyInstaller `--onefile`**. Cannot cross-compile — build each OS on its own runner.
- **GitHub Actions matrix** (windows + ubuntu + macos): push a tag → 3 binaries published.
- UPX compression + `--exclude-module` for unused stdlib (tkinter, tests) to trim size.
- `# ponytail: PyInstaller onefile; switch to Nuitka only if startup speed/size hurts.`

## Stack

| Need | Tool | Notes |
|---|---|---|
| PDF text + layout | `pdfplumber` | also exposes tables/columns for ATS checks |
| DOCX text | `python-docx` | |
| Spell / typos | `pyspellchecker` | pure-python, bundled freq dict |
| Filler + AI-tells | regex + bundled wordlists | 0 deps |
| Semantic similarity | `model2vec` (potion-8M) | static embeddings, numpy-only, no torch/onnx |
| Terminal output | `rich` | optional color; plain fallback |

### Why model2vec / potion-8M

- Static token embeddings distilled from MiniLM. Inference = average token vectors + cosine. **numpy only — no torch, no onnxruntime.**
- Model ≈ 30MB. Final binary ≈ 50–70MB (vs ~250MB for onnx, ~1GB+ for torch).
- Resumes and JDs are keyword-dense, not subtle prose — the quality gap vs full MiniLM on *this* text is a rounding error.
- Fast on CPU, free per-run — also the correct pick if batch mode is ever added.
- `# ponytail: model2vec static embeddings; upgrade to onnx int8 MiniLM (~45MB) only if match quality measurably weak.`

**Brutal-honest note on the match score:** the similarity number is the fuzziest, least verifiable part of the tool (enhancv's is vibes too). The valuable signal is the deterministic stuff — typos, missing sections, unquantified bullets, AI-tells, and the **explicit list of missing skills**. The cosine is a secondary signal; do not over-invest in the model.

## Scoring

### ATS-readiness
- Text is extractable (not a scanned image).
- No tables / multi-column layout / text boxes / header-footer content (ATS chokes on these).
- Standard section headings present: Contact, Summary, Experience, Education, Skills.
- Contact info parseable: email, phone.
- Dates consistent.
- File type sane (.pdf / .docx).

### Content quality
- Action verbs present, weak verbs flagged.
- Bullets quantified (numbers / %).
- Length vs experience; bullet length sane.

### Writing
- **Spell:** `pyspellchecker.unknown()` → misspelled words; `correction()` → suggestion. Report `line N: "experiance" → experience`.
  - **Requires a bundled tech/skill allowlist** (Kubernetes, OAuth, GraphQL, …) + proper-name skip, or it flags jargon as typos and the check is noise.
- **AI-tells** (mechanical subset of the humanizer guide, bundled wordlists):
  - `—` em dash, `–` en dash, ` -- ` double hyphen
  - emojis (unicode ranges)
  - curly quotes `“ ” ‘ ’`
  - AI vocab: delve, tapestry, testament, pivotal, vibrant, showcase, underscore, garner…
  - copula avoidance: "serves as", "boasts a", "stands as"
  - filler: "in order to", "due to the fact that", "at this point in time"
  - hedging: "could potentially possibly"
  - Each → line + offending text + fix suggestion.

### JD match (optional)
- **Skill/keyword extraction** (exact, explainable): list skills in JD missing from resume — the thing users act on.
- **Embedding cosine** (potion-8M): fuzzy secondary similarity signal.
- Hybrid score combining the two.

### Weights
- Overall = weighted sum of the four sections. Default: equal-ish; ATS-readiness weighted slightly higher (it's the pass/fail gate). Tunable in one place.
- `# ponytail: weights as constants in one module; expose as flags only if users ask.`

## CLI

```
ats-score resume.pdf                 # ATS + content + writing
ats-score resume.pdf --jd job.txt    # + JD match
ats-score resume.pdf --json          # machine-readable output
```

- `argparse` (stdlib). No click/typer.
- `cli.py` is a thin wrapper over a single `score(resume_path, jd_path=None) -> Report` function, so batch mode is a cheap `for` loop + CSV writer later.

## Report shape

```
resume.pdf  →  74/100

ATS-readiness  85   parse ok · no tables · 5/5 sections · contact found
Content        70   12 bullets · 4 missing numbers · 2 weak verbs
Writing        68   3 typos · 5 fillers · 2 AI-tells (em dash, "delve")
JD match       72   missing: Kubernetes, GraphQL, CI/CD

Typos:    line14 experiance→experience · line22 recieve→receive
AI-tells: line9 em dash · line9 "delve"→dig into
Fillers:  line5 "in order to"→"to"
```

## Structure

```
ats-score-cli/
  pyproject.toml
  .github/workflows/build.yml   # matrix → 3 binaries on tag
  ats_score/
    cli.py            # argparse, thin wrapper over score()
    core.py           # score() — orchestrates, returns Report
    extract.py        # pdf/docx → text + layout flags
    checks_ats.py     # readiness
    checks_content.py # verbs / numbers / length
    writing.py        # spell + filler + ai-tells
    similarity.py     # model2vec cosine + skill extraction
    report.py         # rich output + json
    data/             # bundled: wordlists, tech-allowlist, model weights
  tests/
    test_writing.py
    test_checks.py
```

## Future (deferred — do not build now)

- **Batch / enterprise mode:** folder of resumes → ranked CSV/JSON. Core stays the same; add a loop + output format. model2vec already suits batch (fast, CPU, free).
  - **Legal landmine:** auto-ranking *humans* for hiring is regulated — EU AI Act ("high-risk"), NYC Local Law 144 (bias-audit requirement), EEOC adverse-impact liability. A parse/format checker has none of this; a candidate ranker has all of it. Treat as a compliance decision, not just a feature.
- LLM-backed deep AI-tell detection and semantic rewrite suggestions (needs API; breaks the offline-binary constraint).
- Self-check multi-seat distribution (same tool, sold to teams) — no architecture change.
