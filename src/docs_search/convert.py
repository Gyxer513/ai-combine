"""Convert documents (PDF/DOCX/PPTX/HTML/...) to Markdown for the docs index.

Drop raw documents into DOCS_CONVERT_SRC, run this module, and it writes one `.md` per
file into DOCS_CORPUS_DIR (which DOCS_GLOBS already includes). Then build the index with
`python -m src.docs_search.index`.

    python -m src.docs_search.convert            # convert DOCS_CONVERT_SRC -> DOCS_CORPUS_DIR
    python -m src.docs_search.convert src/ out/  # explicit paths

Uses markitdown (Microsoft) — lazily imported, so the base install can import this module
and report a clean "not installed" error instead of crashing. `.md`/`.txt` are passed
through (copied) without invoking the converter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import structlog

from src.orchestrator.config import settings

log = structlog.get_logger()

# Extensions markitdown converts; .md/.txt are copied as-is.
_CONVERTIBLE = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm",
    ".csv", ".json", ".xml", ".epub", ".rtf", ".odt",
}
_PASSTHROUGH = {".md", ".markdown", ".txt"}


class DocsConverterUnavailable(RuntimeError):
    """Raised when the `convert` extra (markitdown) is not installed."""


def _make_converter():
    """Build a markitdown converter or raise a friendly error."""
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise DocsConverterUnavailable(
            "document conversion needs the 'convert' extra: uv sync --extra convert "
            "(markitdown)"
        ) from exc
    return MarkItDown()


def _out_name(rel: Path) -> str:
    """Flatten a relative path to a single .md filename, keeping the source extension.

    'reports/q3.pdf' -> 'reports__q3.pdf.md' (avoids collisions across formats/folders).
    """
    flat = "__".join(rel.parts)
    return f"{flat}.md"


def convert_tree(src_dir: str, out_dir: str, *, converter=None) -> tuple[int, int]:
    """Convert every supported file under src_dir into out_dir. Returns (written, skipped)."""
    src = Path(src_dir)
    out = Path(out_dir)
    if not src.exists():
        log.warning("convert.src_missing", src=src_dir)
        return (0, 0)
    out.mkdir(parents=True, exist_ok=True)

    written = skipped = 0
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        ext = path.suffix.lower()
        rel = path.relative_to(src)
        target = out / _out_name(rel)
        if ext in _PASSTHROUGH:
            target.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            written += 1
            continue
        if ext not in _CONVERTIBLE:
            skipped += 1
            continue
        if converter is None:
            converter = _make_converter()
        try:
            text = converter.convert(str(path)).text_content
        except Exception as exc:  # noqa: BLE001 — one bad file shouldn't abort the batch
            log.warning("convert.failed", file=str(path), error=str(exc))
            skipped += 1
            continue
        target.write_text(text or "", encoding="utf-8")
        written += 1
        log.info("convert.ok", file=rel.as_posix())

    log.info("convert.done", written=written, skipped=skipped, out=out_dir)
    return (written, skipped)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    src = args[0] if len(args) >= 1 else settings.docs_convert_src
    out = args[1] if len(args) >= 2 else settings.docs_corpus_dir
    convert_tree(src, out)


if __name__ == "__main__":
    main()
