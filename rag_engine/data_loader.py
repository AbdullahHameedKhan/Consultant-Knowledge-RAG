"""Scan ./internal_reports/, parse PDFs and DOCX, split into chunks.
Lazy loading: skip files whose content hash hasn't changed.
"""
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import docx
import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_engine.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


@dataclass
class DocumentChunk:
    chunk_id: str
    doc_id: str
    source_file: str
    page_label: str
    text: str
    metadata: dict = field(default_factory=dict)


def _hash_file(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _extract_pdf(path: Path) -> list[tuple[str, str]]:
    """Returns list of (text, page_label) tuples."""
    pages: list[tuple[str, str]] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((text, f"p.{i + 1}"))
    return pages


def _extract_docx(path: Path) -> list[tuple[str, str]]:
    doc = docx.Document(str(path))
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [(full_text, "doc")] if full_text else []


def _extract_txt(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    return [(text, "txt")] if text else []


def _extract_text(path: Path) -> list[tuple[str, str]]:
    ext = path.suffix.lower()
    match ext:
        case ".pdf":
            return _extract_pdf(path)
        case ".docx":
            return _extract_docx(path)
        case ".txt":
            return _extract_txt(path)
        case _:
            return []


def load_documents(
    processed_hashes: dict[str, str] | None = None,
) -> tuple[list[DocumentChunk], dict[str, str]]:
    """
    Scan DOCUMENT_DIR and return chunks for new/changed files.

    Args:
        processed_hashes: mapping of file_path → md5 from previous run.

    Returns:
        (new_chunks, updated_hashes)
    """
    if processed_hashes is None:
        processed_hashes = {}

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    new_chunks: list[DocumentChunk] = []
    updated_hashes: dict[str, str] = dict(processed_hashes)
    doc_dir = Path(settings.document_dir)

    if not doc_dir.exists():
        logger.warning("Document directory %s does not exist.", doc_dir)
        return [], updated_hashes

    for path in sorted(doc_dir.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS or not path.is_file():
            continue

        file_key = str(path)
        current_hash = _hash_file(path)

        if processed_hashes.get(file_key) == current_hash:
            logger.debug("Skipping unchanged file: %s", path.name)
            continue

        logger.info("Processing: %s", path.name)
        pages = _extract_text(path)

        for raw_text, page_label in pages:
            splits = splitter.split_text(raw_text)
            for idx, chunk_text in enumerate(splits):
                chunk_id = hashlib.md5(
                    f"{file_key}:{page_label}:{idx}".encode()
                ).hexdigest()
                new_chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        doc_id=hashlib.md5(file_key.encode()).hexdigest(),
                        source_file=path.name,
                        page_label=page_label,
                        text=chunk_text,
                        metadata={"file_path": file_key, "page": page_label},
                    )
                )

        updated_hashes[file_key] = current_hash

    logger.info("Loaded %d new chunks.", len(new_chunks))
    return new_chunks, updated_hashes
