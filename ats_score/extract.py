"""Resume text + layout extraction for PDF and DOCX.

Returns plain text plus the layout flags the ATS-readiness check needs
(tables, columns, images, scanned). Dispatch is by file suffix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Unmappable glyphs pdfplumber emits for icon/symbol fonts.
_CID = re.compile(r"\(cid:\d+\)")
# Zero-width / BOM chars (templates like Enhancv inject these; they silently
# break keyword and spell matching, e.g. a zero-width space inside "JavaScript").
_ZEROWIDTH = re.compile("[​‌‍⁠﻿]")


@dataclass
class Document:
    text: str
    fmt: str                       # "pdf" or "docx"
    source: Path
    has_tables: bool = False
    has_columns: bool = False
    has_images: bool = False
    is_scanned: bool = False       # PDF with images but ~no extractable text
    links: list[str] = field(default_factory=list)   # hyperlink URIs (mailto/tel/http)
    warnings: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    # Unify line endings so every downstream check sees \n only, and drop
    # unmappable icon-font glyphs that would otherwise read as spell errors.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CID.sub("", text)
    text = _ZEROWIDTH.sub("", text)
    return text.strip()


def _extract_pdf(path: Path) -> Document:
    import pdfplumber

    parts: list[str] = []
    links: list[str] = []
    has_tables = has_images = has_columns = False
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            # ponytail: x_tolerance=2 (default 3) recovers lost word spacing in
            # tightly-kerned resume PDFs without over-splitting normal words.
            parts.append(page.extract_text(x_tolerance=2) or "")
            if page.extract_tables():
                has_tables = True
            if page.images:
                has_images = True
            if not has_columns and _looks_multicolumn(page):
                has_columns = True
            links.extend(_pdf_links(page))

    text = _normalize("\n".join(parts))
    # ponytail: scanned heuristic = images present but almost no text. Naive but
    # catches the common "exported scan" case; OCR is out of scope.
    is_scanned = has_images and len(text) < 100
    return Document(
        text=text, fmt="pdf", source=path,
        has_tables=has_tables, has_columns=has_columns,
        has_images=has_images, is_scanned=is_scanned,
        links=_dedup(links),
    )


def _dedup(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for i in items:
        if i:
            seen.setdefault(i, None)
    return list(seen)


def _pdf_links(page) -> list[str]:
    out: list[str] = []
    for h in (page.hyperlinks or []):
        if h.get("uri"):
            out.append(h["uri"])
    for a in (page.annots or []):
        data = a.get("data")
        action = data.get("A") if isinstance(data, dict) else None
        uri = action.get("URI") if isinstance(action, dict) else None
        if uri:
            out.append(uri.decode() if isinstance(uri, bytes) else uri)
    return out


def _looks_multicolumn(page) -> bool:
    # ponytail: heuristic. Split words into left/right halves of the page; if
    # both halves are well populated and there's a clear vertical gutter, call
    # it multi-column. Upgrade to a clustering pass if false positives bite.
    words = page.extract_words() or []
    if len(words) < 30:
        return False
    mid = page.width / 2
    left = sum(1 for w in words if w["x1"] < mid)
    right = sum(1 for w in words if w["x0"] > mid)
    total = len(words)
    # both sides carry real content, and few words straddle the centre gutter
    straddle = sum(1 for w in words if w["x0"] < mid < w["x1"])
    return left > total * 0.3 and right > total * 0.3 and straddle < total * 0.05


def _extract_docx(path: Path) -> Document:
    import docx

    document = docx.Document(str(path))
    paras = [p.text for p in document.paragraphs if p.text.strip()]

    has_tables = len(document.tables) > 0
    # pull table cell text too so keyword/JD checks still see it
    for tbl in document.tables:
        for row in tbl.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paras.append(cell.text)

    has_images = bool(document.inline_shapes)
    has_columns = _docx_has_columns(document)

    links = [
        rel.target_ref for rel in document.part.rels.values()
        if "hyperlink" in rel.reltype
    ]

    return Document(
        text=_normalize("\n".join(paras)), fmt="docx", source=path,
        has_tables=has_tables, has_columns=has_columns,
        has_images=has_images, is_scanned=False, links=_dedup(links),
    )


def _docx_has_columns(document) -> bool:
    # ponytail: read the section column count from sectPr; >1 means multi-column.
    try:
        for section in document.sections:
            cols = section._sectPr.find(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cols"
            )
            if cols is not None:
                num = cols.get(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num"
                )
                if num and int(num) > 1:
                    return True
    except Exception:
        pass
    return False


def extract(path: str | Path) -> Document:
    """Extract text + layout flags from a PDF or DOCX resume."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    raise ValueError(f"Unsupported file type '{suffix}'. Use .pdf or .docx.")


def _selfcheck() -> None:
    # Round-trip a generated DOCX (no fixtures needed). PDF path is covered by
    # fixtures in the test suite (phase 8).
    import tempfile
    import docx

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.docx"
        doc = docx.Document()
        doc.add_paragraph("Jane Doe")
        doc.add_paragraph("Experience: built things")
        doc.save(str(p))

        out = extract(p)
        assert out.fmt == "docx", out.fmt
        assert "Jane Doe" in out.text, out.text
        assert "built things" in out.text, out.text
        assert "\r" not in out.text
        assert out.is_scanned is False

    try:
        extract(Path(d) / "missing.docx")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")

    try:
        extract("resume.txt")
    except (ValueError, FileNotFoundError):
        pass
    else:
        raise AssertionError("expected rejection of .txt")

    assert _normalize("Java​Script﻿") == "JavaScript", "zero-width strip"
    assert _normalize("a\x0d\x0ab") == "a\nb"

    print("extract selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
