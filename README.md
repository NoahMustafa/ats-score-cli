# ATS Score CLI

A terminal **ATS-readiness linter** for resumes (PDF or DOCX). It answers one
question well: *can an applicant tracking system parse this resume, and what is
it missing?* Fully offline, no account, no upload. Ships as a single
self-contained binary per OS (`tool.exe` on Windows, `tool` on Linux/macOS).

```
tool resume.pdf            # ATS-readiness score + what's missing + writing advice
tool resume.pdf --json     # machine-readable output (for other tools)
```

The **overall score is the ATS-readiness score** (0–100). The findings — what's
broken or missing for parsing — are the point, not the number.

> **V1 scope.** This release focuses on the deterministic, reusable core:
> parsing and ATS-readiness. Content-quality grading (bullet strength,
> quantification) and spelling/grammar were dropped — they were low-signal and
> noisy. JD-to-resume matching exists in the code but needs an embedding model
> that is **not bundled** in V1, so it is disabled in the shipped binary (see
> "JD match" below).

---

## What it checks

### 1. Extraction (what we read out of the file)

- **PDF** via `pdfplumber`, **DOCX** via `python-docx`. Dispatch is by extension.
- **Two-column layouts** detected and de-scrambled (left column then right), so
  the text isn't the jumble an ATS would produce.
- **Vector ("drawn") bullets** — bullets that are graphics, not characters
  (common in Word/Canva exports) — are detected and flagged, because a real ATS
  won't see them as a list.
- **Tables, images, scanned pages** (images with almost no text) detected.
- **Hyperlinks** (`mailto:`, `tel:`, `http`) pulled from PDF annotations and
  DOCX relationships, so an email/phone behind a contact icon still counts.
- Cleanup: line-ending normalization, removal of icon glyphs and zero-width
  characters, de-hyphenation of words split across a line break.

### 2. ATS readiness — the score

Start at 100, subtract per issue:

| Check | Severity | Penalty |
|---|---|---|
| Not machine-readable (scanned / almost no text) | fail | −40 |
| Tables present (ATS may garble columns) | fail | −12 |
| Multi-column layout | fail | −12 |
| Images present | warn | −5 |
| Bullets are graphics, not text | warn | −4 |
| Missing a standard section — each of Summary, Experience, Education, Skills | warn | −8 each |
| No email found (text or `mailto:` link) | fail | −10 |
| No phone found (text or `tel:` link) | warn | −5 |
| No location found (city/region, or "Remote") | warn | −3 |
| No LinkedIn / portfolio link | warn | −3 |
| Inconsistent date formats (mix of word / numeric / `'21` styles) | warn | −5 |

- A **Projects** section is not required (no penalty if absent).
- **Location** is searched only in the header zone, so a `Languages, Python`
  skills line can't pass as a location.

### 3. Writing advice — shown, **not scored**

Reported as suggestions that do **not** change the overall score:

- **Filler / hedging / ceremony**: *in order to → to*, *a wide range of → many*,
  *when it comes to*, *could potentially*, *at its core*, etc.
- **AI-generated tells** (from Wikipedia's "Signs of AI writing"): em dash / `--`
  as punctuation (**date ranges like `Jan '21 — Sep '25` are exempt**), emojis,
  curly quotes, AI vocabulary (*delve, tapestry, testament, vibrant, pivotal,
  garner, boasts…*), copula avoidance (*serves as, stands as*), negative
  parallelism (*not just X but Y*), and chatbot-paste artifacts (*as an AI,
  I hope this helps*). En dashes are never flagged.

### Skills the parser read

With no JD, the report lists the skills it could extract from the resume against
a bundled cross-domain taxonomy (ESCO + tech, ~66k phrases) — a readback, not a
score. If a key skill is missing from that list, your formatting hid it.

### JD match (disabled in the V1 binary)

Matching a resume against a job description needs static embeddings
(`model2vec`/potion-8M). That model is **not bundled** in V1 (it would add ~34MB
and the feature was the fuzziest part), so `--jd` reports that the match is
unavailable and falls back to the skills readback. The code path is intact: drop
the model into `ats_score/data/potion-8M` (and rebuild without the model
excludes) to re-enable cosine + skill-gap matching.

---

## What it does **not** do (V1)

Being honest so the score isn't misleading:

- **No content-quality scoring** (bullet strength, quantified achievements,
  action verbs). The grader exists in the code but is unwired — it was
  unreliable (e.g. it scored *higher* when it failed to find bullets).
- **No spelling or grammar checking.** Removed in V1 as low-signal/noisy.
- **No JD match in the shipped binary** (model not bundled — see above).
- **The "bullets are graphics" flag can over-trigger.** Detection keys on small
  left-margin vector marks; a resume with decorative marks but no text bullets
  can read as having graphic bullets. Treat that one warning (−4) as soft.
- **Not a recruiter / batch tool** — it scores one resume at a time. Batch
  ranking is deferred (it also carries an EU AI Act / NYC LL144 legal surface).

---

See [specs.md](specs.md) for design rationale and [tasks.md](tasks.md) for build
status.
