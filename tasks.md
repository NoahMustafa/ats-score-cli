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

## Phase 2 — Checks: ATS readiness (`checks_ats.py`)

- [ ] Text-extractable / not-scanned.
- [ ] No tables / columns / text-boxes / header-footer content.
- [ ] Standard sections present (Contact, Summary, Experience, Education, Skills) — heading regex, case-insensitive.
- [ ] Contact parseable: email + phone regex.
- [ ] Date consistency.
- [ ] Returns sub-scores + reasons.

## Phase 3 — Checks: content (`checks_content.py`)

- [ ] Action-verb detection; weak-verb flags (bundled wordlist).
- [ ] Quantified-bullet check (numbers / %).
- [ ] Length vs bullet-count heuristics.
- [ ] Returns sub-scores + per-line findings.

## Phase 4 — Writing (`writing.py`)

- [ ] **Spell:** `pyspellchecker` → `unknown()` + `correction()`. Report `line N: wrong → suggestion`.
- [ ] Build bundled **tech/skill allowlist** + proper-name skip so jargon isn't flagged. (Without this the check is noise.)
- [ ] **AI-tells** (bundled wordlists, regex): em/en dash, ` -- `, emojis (unicode ranges), curly quotes, AI vocab, copula avoidance, filler, hedging. Each → line + text + fix.
- [ ] Wordlist data files under `ats_score/data/`, loaded via `bundled_path()`.
- [ ] Self-check: known-bad string flags expected typos/tells; clean string flags nothing.

## Phase 5 — Similarity (`similarity.py`)

- [ ] Load `model2vec` static model from `bundled_path("data/potion-8M")` — **no network**.
- [ ] `cosine(resume_text, jd_text)` for the fuzzy secondary signal.
- [ ] **Skill extraction:** skills in JD missing from resume (the actionable output) — match against bundled skill list + JD tokens.
- [ ] Hybrid JD-match score (overlap + cosine).
- [ ] Self-check: identical text ≈ 1.0; unrelated text low.

## Phase 6 — Core + report (`core.py`, `report.py`)

- [ ] `score(resume_path, jd_path=None) -> Report` — orchestrates phases 1–5, applies weights. **All logic lives here; CLI stays thin.**
- [ ] Weights as constants in one place; ATS-readiness weighted slightly higher.
- [ ] `report.py`: `rich` formatted output (the report shape in spec) + `--json` machine output.
- [ ] Plain-text fallback when not a TTY / `NO_COLOR` set.

## Phase 7 — CLI (`cli.py`)

- [ ] `argparse`: positional `resume`, `--jd`, `--json`. Thin wrapper over `score()`.
- [ ] Non-zero exit on file-not-found / unsupported type.
- [ ] `main()` entry point.

## Phase 8 — Tests

- [ ] `tests/test_writing.py`, `tests/test_checks.py` — asserts on fixture resumes (good + bad).
- [ ] No frameworks beyond `pytest`; small fixtures, no network.

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
