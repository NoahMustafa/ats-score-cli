# ATS Score CLI — Build Tasks

Build order for the whole project. See [specs.md](specs.md) for the why. Check off as you go.

Cross-OS rule running through everything: **never hardcode paths or separators, never assume an encoding, never assume a shell.** Use `pathlib`, `encoding="utf-8"`, and resolve bundled data via `sys._MEIPASS`.

---

## Phase 0 — Project skeleton ✅

- [x] `pyproject.toml` — package `ats_score`, entry point `ats-score = ats_score.cli:main`, deps from requirements.
- [x] Package dirs + empty `__init__.py`: `ats_score/`.
- [x] `.gitignore` — `build/`, `dist/`, `*.spec`, `__pycache__/`, `.venv/`.
- [x] Delete `ats_score/data/potion-8M/.gitattributes` so the vendored model commits as a plain file, not LFS.
- [x] `bundled_path()` helper (`paths.py`): returns `sys._MEIPASS` when frozen, package dir otherwise. **Every data-file read goes through this.**

## Phase 1 — Extraction (`extract.py`) ✅

- [x] `extract(path) -> Document` returning text + layout flags (has_tables, has_columns, has_images, is_scanned).
- [x] PDF via `pdfplumber`: pull text; detect tables (`.extract_tables`), multi-column, embedded images, empty-text (scanned).
- [x] DOCX via `python-docx`: paragraphs + tables; flag tables + columns.
- [x] Dispatch on suffix (`.pdf`/`.docx`), case-insensitive. Reject others with a clear message.
- [x] Normalize line endings (`\r\n` → `\n`).
- [x] Self-check: DOCX round-trip in `__main__`. PDF deferred to fixtures (phase 8).

## Phase 2 — Checks: ATS readiness (`checks_ats.py`) ✅

- [x] Text-extractable / not-scanned.
- [x] No tables / columns / images.
- [x] Standard sections present (Summary, Experience, Education, Skills) — heading heuristic, case-insensitive. Contact handled via email/phone.
- [x] Contact parseable: email + phone regex.
- [x] Date consistency (word vs numeric style mismatch).
- [x] Returns sub-score + findings.
- [x] Self-check + verified on 4 real resumes.
- Note: icon-hyperlinked contact (email only in PDF link annotation, not text) reads as "no email". Defensible (icon-only contact is an ATS risk). Future: parse PDF URI annotations if false-positives bite.

## Phase 3 — Checks: content (`checks_content.py`) ✅

- [x] Action-verb detection (strong/weak verb sets + -ed/-ing heuristic); weak-verb flags.
- [x] Quantified-bullet check — ignores years/versions so "in 2024" / "Python 3.11" don't fake a metric.
- [x] Length heuristic, scales with seniority (year-token / title proxy).
- [x] Section-aware: verb/quantification rules apply only to bullets under Experience/Project headings; skills "Category: items" lines exempt. Killed false positives.
- [x] Glyph + numbered bullet detection.
- [x] Returns sub-score + per-line findings.
- [x] Self-check (covers each fix) + verified on 6 real resumes.

## Phase 4 — Writing (`writing.py`) ✅

- [x] **Spell:** `pyspellchecker` (distance=2) + vendored 370k-word English list (`data/words_alpha.txt`) → high precision. Report `line N: "wrong" → suggestion`.
- [x] Noise control: skip capitalized words (names/companies/tech), URLs, emails, hyphenated tokens; tolerate plural/verb/British morphology; tech-compound allowlist. Result: 0 false-positive typos across 9 sample resumes.
- [x] De-hyphenate line-break wraps in extraction ("third-\nparty" → "third-party"), keeping the hyphen so real compounds survive.
- [x] **AI-tells** (regex + conservative wordlists): em dash / ` -- `, emojis, curly quotes, AI vocab (excludes common resume words), copula avoidance. En dash NOT flagged (date ranges).
- [x] **Filler + hedging** phrases with suggested fixes.
- [x] Self-check (clean=100, bad flagged, date en-dash safe, capitalized not typo) + verified recall on injected typos.
- Note: dwyl wordlist contains a few noise entries (e.g. "enviroment"), so rare real typos in the list slip through. Acceptable for the precision gain.

## Phase 5 — Similarity (`similarity.py`) ✅

- [x] Load `model2vec` static model from `bundled_path("data/potion-8M")` — **offline** (HF_HUB_OFFLINE).
- [x] `cosine(resume, jd)` via model2vec (256-dim static embeddings).
- [x] **Keyword gap:** clean content keywords (punct-stripped, stopworded); report missing JD terms ranked by JD frequency — the actionable output.
- [x] Hybrid score = 0.55·cosine + 0.45·coverage.
- [x] Self-check (identical≈1, missing terms detected, unrelated low) + verified discrimination on real resumes (data-eng 74 > sysadmin 46 > frontend 21 vs a data JD).

## Phase 6 — Core + report (`core.py`, `report.py`) ✅

- [x] `score(resume_path, jd_path=None) -> Report` — orchestrates phases 1–5, applies weights. **All logic lives here; CLI stays thin.**
- [x] Weights as constants in one place; ATS-readiness weighted highest. No-JD branch (3 weights) vs JD branch (4 weights).
- [x] JD-match gated on a JD; no JD → `detect_skills()` readback (parser-readable skills, no penalty).
- [x] `report.py`: `rich` formatted output + `--json` machine output (`to_dict`/`render_json`).
- [x] Plain-text fallback when not a TTY / `NO_COLOR` set (and if `rich` import fails).
- [x] Self-checks (core: JD vs no-JD branches; report: plain + JSON). Verified on real resumes via CLI.

## Phase 7 — CLI (`cli.py`) ✅

- [x] `argparse`: positional `resume`, `--jd`, `--json`. Thin wrapper over `score()`.
- [x] Non-zero exit (2) on file-not-found / unsupported type.
- [x] `main()` entry point (wired in pyproject: `ats-score = ats_score.cli:main`).

## Phase 8 — Tests ✅

- [x] `tests/test_checks.py` (ATS + content), `tests/test_writing.py`, `tests/test_core.py` (JD gating, weighting, report shapes).
- [x] All fixtures synthetic (in-code Documents + a tmp DOCX) — runs in CI with **no resume corpus** (PII stays git-ignored). No network. 19 tests pass.

## Phase 9 — Packaging (per-OS binary)

Cross-OS is the whole point of this phase. **PyInstaller cannot cross-compile** — each OS builds its own binary.

- [ ] PyInstaller spec (or CLI flags): `--onefile`, `--name tool`.
- [ ] `--add-data` the model + wordlists. **Separator differs per OS:** `src:dest` on Linux/macOS, `src;dest` on Windows. Use a spec file with `datas=[...]` to avoid the separator footgun.
- [ ] `--exclude-module tkinter` and other unused stdlib to trim size.
- [ ] UPX compression (install UPX on each runner).
- [ ] Verify the frozen binary loads the model from `sys._MEIPASS` (run it on a machine with **no** HuggingFace cache to prove offline).
- [ ] Windows: confirm output is `tool.exe`, no console-encoding crash on unicode (set UTF-8 / `rich` handles it).
- [ ] macOS: unsigned binary triggers Gatekeeper — note `xattr -d com.apple.quarantine` for users, or sign/notarize later.
- [ ] Linux: build on the **oldest** glibc target you support (build on old Ubuntu so binary runs on newer). musl/Alpine = separate build if needed.

## Phase 10 — CI release (`.github/workflows/build.yml`)

- [ ] Matrix: `windows-latest`, `ubuntu-latest` (or older for glibc), `macos-latest`.
- [ ] Steps: checkout → setup-python → `pip install -r requirements.txt pyinstaller` → build → upload artifact.
- [ ] Trigger on tag push (`v*`) → attach the 3 binaries (`tool.exe`, `tool`-linux, `tool`-macos) to a GitHub Release.
- [ ] Smoke-test each artifact (`tool --help`, score a fixture) before publishing.

---

## Deferred (not now — see spec *Future*)

- Batch / recruiter mode (folder → ranked CSV). **Legal surface: EU AI Act / NYC LL144 — compliance decision, not just code.**
- LLM-backed deep AI-tell detection (breaks offline-binary constraint).
- macOS code-signing / notarization.
