# open-ATS

A terminal **ATS-readiness linter** for resumes (PDF or DOCX). It answers one
question well: *can an applicant tracking system parse this resume, and what is
it missing?* Fully offline, no account, no upload. Ships as a single
self-contained binary per OS (`tool.exe` on Windows, `tool` on Linux/macOS).

```
tool resume.pdf                  # ATS-readiness score + what's missing + writing advice
tool resume.pdf --jd job.txt     # + two-tier JD match (skill gap + requirement coverage)
tool resume.pdf --json           # machine-readable output (for other tools)
tool resume.pdf --md             # export to clean structured Markdown (no scoring)
```

The **overall score is the ATS-readiness score** (0–100). The findings — what's
broken or missing for parsing — are the point, not the number.

> **V1 scope.** This release focuses on the deterministic, reusable core:
> parsing and ATS-readiness. Content-quality grading (bullet strength,
> quantification) and spelling/grammar were dropped — they were low-signal and
> noisy. JD-to-resume matching is included as an optional two-tier check (see
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

### JD match (`--jd`) — two tiers

Pass a job description (file or raw text) to match the resume against it. The
match has two complementary layers and the report shows both:

- **Tier 1 — skill gap (deterministic):** the JD's *named skills* (gazetteer
  match) intersected with the resume's. Output: matched skills + a ranked
  **missing-skills** list. Grounded, explainable, no hallucination.
- **Tier 2 — requirement coverage (semantic):** each JD *prose requirement*
  ("build reliable data pipelines", "work independently under pressure") is
  embedded (`model2vec`/potion-8M, offline) and matched by max-similarity to the
  resume's sentences. Output: a **"requirements your resume doesn't clearly
  cover"** list — the phrased requirements with no clear evidence.

The JD-match score blends the two (skill gap weighted higher). The embedding
model is bundled, so this works fully offline. It still does not *reason* (it's
vector similarity, not an LLM): it captures relatedness, not logical entailment
or evidence quotes — that's a future `--deep` upgrade.

**Job description format — just plain text.** Pass a `.txt` file or a quoted
string; no special formatting required.

```
tool resume.pdf --jd job.txt
tool resume.pdf --jd "Senior Data Engineer. Python, SQL, Airflow, AWS. Build and maintain data pipelines."
```

For the best match, paste the **whole posting** (responsibilities + requirements
+ a skills list). How the two tiers read it:

- **Tier 1** scans the entire text for *named skills*, so list concrete tools and
  technologies (`Python`, `Airflow`, `Kubernetes`, `Snowflake`).
- **Tier 2** splits the text into *requirement sentences* — segments of **5+
  words**, broken on newlines, sentence punctuation, and bullets. Keep
  requirement statements as real sentences; short headers ("Requirements:") are
  ignored. Bullets and line breaks are fine.

### Markdown export (`--md`) — for feeding a resume to an LLM

Dump the resume to clean, **structured Markdown** instead of scoring it — useful
when another model needs to read the resume without fighting PDF layout. It runs
the same extraction as scoring, so the column de-scramble, drawn-bullet
reconstruction, glyph cleanup, and link recovery all carry over.

```
tool resume.pdf --md                 # writes resume.md beside the resume
tool resume.pdf --md out.md          # explicit output file
tool resume.pdf --md docs/           # a directory → docs/resume.md
tool resume.pdf --md --force         # overwrite instead of auto-renaming
```

- The output path is **optional** — it defaults to the resume's name with a
  `.md` suffix, in the resume's folder. A directory target writes `<stem>.md`
  inside it; a path with no suffix gets `.md`.
- **No silent overwrite.** If the target exists, it's auto-renamed `name-1.md`,
  `name-2.md`, … Pass `--force` to overwrite in place instead.
- Mapping: first line → `# title`, section headers → `## heading`, bullets →
  `- item`. Hyperlinks the parser recovered (including ones hidden behind contact
  icons) are appended as a `## Links` section so the model sees them too.

---

## What it does **not** do (V1)

Being honest so the score isn't misleading:

- **No content-quality scoring** (bullet strength, quantified achievements,
  action verbs). The grader exists in the code but is unwired — it was
  unreliable (e.g. it scored *higher* when it failed to find bullets).
- **No spelling or grammar checking.** Removed in V1 as low-signal/noisy.
- **JD match doesn't reason.** Tier 2 is vector similarity, so it captures
  relatedness, not entailment ("Docker" scores close to "Kubernetes"). No
  evidence quotes or gap explanations — that's a future `--deep` (local LLM)
  upgrade.
- **The "bullets are graphics" flag can over-trigger.** Detection keys on small
  left-margin vector marks; a resume with decorative marks but no text bullets
  can read as having graphic bullets. Treat that one warning (−4) as soft.
- **Not a recruiter / batch tool** — it scores one resume at a time. Batch
  ranking is deferred (it also carries an EU AI Act / NYC LL144 legal surface).
