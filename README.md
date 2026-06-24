# ATS Score CLI

Terminal tool that scores a resume (PDF or DOCX) for ATS-readiness, content
quality, and writing quality — and, optionally, match against a job
description. Fully offline, no account, no upload. Ships as a single
self-contained binary per OS (`tool.exe` on Windows, `tool` on Linux/macOS);
the model weights, dictionaries, and skill taxonomy are bundled inside.

```
tool resume.pdf                 # ATS + content + writing  (+ skills the parser read)
tool resume.pdf --jd job.txt    # + JD match (job description from a file)
tool resume.pdf --jd "python, sql, aws, kubernetes"   # JD as raw text
tool resume.pdf --json          # machine-readable output (for scripts)
```

The score is **0–100 overall**, plus four sub-scores. Every sub-score starts at
100 and loses points per issue found, so the findings — not the number — are the
point. A clean resume keeps its points.

---

## What it actually checks

### 1. Extraction (what we read out of the file first)

Before scoring, the resume is parsed into text + layout facts:

- **PDF** via `pdfplumber`, **DOCX** via `python-docx`. Dispatch is by file
  extension; anything else is rejected.
- **Two-column layouts** are detected and de-scrambled (left column read fully,
  then the right) so the text isn't the line-by-line jumble an ATS would produce.
- **Vector ("drawn") bullets** — bullets that are graphics, not text characters
  (common in Word/Canva exports) — are detected and reconstructed so they can be
  graded. They are still flagged, because a real ATS won't see them as a list.
- **Tables, images, and scanned pages** (images with almost no text) are detected.
- **Hyperlinks** (`mailto:`, `tel:`, `http`) are pulled from PDF annotations and
  DOCX relationships, so an email/phone hidden behind a contact icon still counts.
- **Cleanup**: line-ending normalization, removal of unmappable icon glyphs and
  zero-width characters, and de-hyphenation of words split across a line break.

### 2. ATS readiness — can a tracking system parse it (weight: highest)

Start 100, subtract:

| Check | Severity | Penalty |
|---|---|---|
| Not machine-readable (scanned / almost no text) | fail | −40 |
| Tables present (ATS may garble columns) | fail | −12 |
| Multi-column layout | fail | −12 |
| Images present | warn | −5 |
| Bullets are graphics, not text | warn | −4 |
| Missing a standard section — each of Summary, Experience, Education, Skills | warn | −8 each |
| **No email** found (text or `mailto:` link) | fail | −10 |
| No phone found (text or `tel:` link) | warn | −5 |
| **Inconsistent date formats** | warn | −5 |

- **Sections** are matched by heading keywords (e.g. Summary/Profile/Objective,
  Experience/Employment/Work History, Education/Academic,
  Skills/Competencies/Technologies), case-insensitive.
- **Date consistency** is intentionally narrow: it flags only when a resume mixes
  word-style dates (`Jan 2024`) with numeric ones (`01/2024`). It does **not**
  judge `'21` vs `2021`, month-only vs month-year, or separator style.

### 3. Content quality — are the bullets strong

Only bullets **under an Experience/Employment/Work/Project heading** are graded
(those are achievements). Bullets under Skills/Summary and `Category: items`
lines are exempt. Start 100, subtract:

| Check | Penalty |
|---|---|
| Bullets lacking a number — tolerates ~30% bare, penalizes the excess by ratio | up to −15 |
| Weak verb to start a bullet (`responsible for`, `worked`, `helped`, `assisted`…) | −3 each |
| Bullet doesn't start with an action verb | −2 each |
| Bullet too long (> 45 words) | −2 each |
| Resume too short (< 200 words) | −15 |
| Resume too long (> 900 words, or > 1300 for a senior/lead resume) | −8 |
| No bullet points found at all | −10 |

- **"Has a number"** ignores years (`in 2024`) and version numbers (`Python 3.11`)
  so they can't fake a metric; magnitude words (`doubled`, `hundreds`, `zero`)
  do count.
- **Seniority** (many dated entries, or a senior/lead/principal title) raises the
  length ceiling.

### 4. Writing quality — typos, filler, AI tells

Start 100, subtract (each category capped so one type can't tank the score):

- **Spelling** (cap −20): `pyspellchecker` (edit distance 2) against a bundled
  370k-word English list plus a tech allow-list. It **skips** capitalized words
  (names, companies, `Python`, `AWS`), URLs, emails, and hyphenated compounds,
  and tolerates plural/verb/British morphology — so it reports real typos, not
  vocabulary it simply doesn't know. Each flagged word shows a suggested fix.
- **Filler & hedging** (cap −10): phrases like *in order to → to*,
  *due to the fact that → because*, *a wide range of → many*, plus hedges
  (*could potentially*, *sort of*).
- **AI-generated tells** (cap −15): em dash / `--` used as punctuation
  (**date ranges like `Jan '21 — Sep '25` are exempt**), emojis, curly quotes,
  tell-tale vocabulary (*delve, tapestry, testament, myriad, pivotal*…), and
  copula-avoidance patterns (*serves as, stands as*). En dashes are never flagged.

### 5. JD match — only when you pass `--jd`

Optional. Without a JD, this section is skipped entirely (and instead the report
lists the **skills the parser could read** in your resume — a readback, not a
score; if a key skill is missing from that list, your formatting hid it).

With a JD, the match score = **50% semantic similarity + 50% skill coverage**:

- **Semantic similarity**: cosine between resume and JD using static embeddings
  (`model2vec` / potion-8M, 256-dim, offline). A fuzzy overall signal.
- **Skill coverage**: skills are matched against a bundled cross-domain taxonomy
  (ESCO + tech terms, ~66k phrases) using 1–4 word phrase matching, so the
  **missing-skills list is real skills** (e.g. `azure`, `kubernetes`), not JD
  prose. British spellings are normalized. This list is the actionable output.

---

## How the overall score is weighted

| | ATS | Content | Writing | JD match |
|---|---|---|---|---|
| **Without `--jd`** | 40% | 35% | 25% | — |
| **With `--jd`** | 30% | 25% | 20% | 25% |

ATS-readiness is weighted highest: a resume the machine can't parse fails before
content or wording matter.

---

## What it does **not** check (known gaps)

Being honest so the score isn't misleading:

- **No location/address check**, and no requirement for LinkedIn/portfolio links
  (links are read, but only email/phone are required).
- **Date consistency is coarse** (word-vs-numeric only; see above).
- **No grammar checking** beyond spelling — sentence structure and tense aren't
  judged.
- **The skill taxonomy is ESCO-based**, so the JD skill gap is strongest for
  common professional/tech roles and thinner for niche trades. Occasional
  mis-segmentation noise (e.g. a generic phrase slipping into the list) is
  possible.
- **Drawn-bullet reconstruction is generous-for-grading**, not an ATS simulator:
  we recover graphic bullets so content can score them, but still flag them as a
  parsing risk because a real ATS won't.
- **Not a recruiter/batch ranking tool** — it scores one resume at a time.

---

See [specs.md](specs.md) for design rationale and [tasks.md](tasks.md) for build
status.
