# Contributing

## Setup

```
pip install -r requirements.txt
pip install pytest
python -m pytest -q
```

## Making a change

1. Fork, branch off `master`.
2. Keep changes scoped — one fix/feature per PR.
3. `python -m pytest -q` must pass.
4. If you touch a check or the score formula, update `README.md`'s
   scoring table to match.
5. Open a PR describing what changed and why.

## Reporting a bug

Open an issue with: the command you ran, what you expected, what happened.
A minimal resume (PDF/DOCX) that reproduces it helps a lot — strip any real
personal info first.
