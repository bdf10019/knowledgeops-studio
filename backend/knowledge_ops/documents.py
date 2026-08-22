from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge_ops.models import EMBEDDING_DIMENSIONS, Chunk, Document

TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
STRUCTURED_SUFFIXES = {".csv", ".json"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | STRUCTURED_SUFFIXES | {".pdf"}


class DocumentError(ValueError):
    pass


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentError(f"Unsupported document type: {suffix or 'unknown'}")

    if suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # pypdf exposes several parser-specific exceptions
            raise DocumentError("The PDF could not be parsed") from exc
    else:
        try:
            decoded = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Text documents must use UTF-8 encoding") from exc

        if suffix == ".csv":
            rows = list(csv.DictReader(io.StringIO(decoded)))
            text = "\n\n".join(
                "; ".join(f"{key}: {value}" for key, value in row.items()) for row in rows
            )
        elif suffix == ".json":
            try:
                payload = json.loads(decoded)
            except json.JSONDecodeError as exc:
                raise DocumentError("The JSON document is invalid") from exc
            text = json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            text = decoded

    normalized = unicodedata.normalize("NFKC", text).replace("\x00", "").strip()
    if len(normalized) < 20:
        raise DocumentError("The document has too little extractable text")
    return normalized


def chunk_text(text: str, *, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", ". ", " ", ""],
        length_function=len,
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def _features(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    latin = re.findall(r"[a-z0-9][a-z0-9_-]+", normalized)
    han = re.findall(r"[\u3400-\u9fff]", normalized)
    han_bigrams = ["".join(han[index : index + 2]) for index in range(max(0, len(han) - 1))]
    return latin + han + han_bigrams


def deterministic_embedding(text: str) -> list[float]:
    """Create a dependency-free, deterministic demo embedding.

    It proves the vector storage and retrieval path without downloading model weights. It is
    intentionally documented as a local fallback, not a semantic embedding benchmark.
    """

    vector = [0.0] * EMBEDDING_DIMENSIONS
    for feature in _features(text):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        sign = -1.0 if digest[4] & 1 else 1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def ingest_document(
    db: Session,
    *,
    collection_id: str,
    filename: str,
    content_type: str,
    data: bytes,
    source_label: str,
    actor_id: str,
) -> tuple[Document, bool]:
    digest = content_sha256(data)
    existing = db.scalar(
        select(Document).where(
            Document.collection_id == collection_id,
            Document.sha256 == digest,
            Document.status != "deleted",
        )
    )
    if existing is not None:
        return existing, False

    text = extract_text(filename, data)
    last_version = db.scalar(
        select(func.max(Document.version)).where(
            Document.collection_id == collection_id,
            Document.filename == filename,
        )
    )
    document = Document(
        collection_id=collection_id,
        filename=Path(filename).name,
        content_type=content_type or "application/octet-stream",
        sha256=digest,
        version=(last_version or 0) + 1,
        status="indexed",
        source_label=source_label.strip(),
        created_by=actor_id,
    )
    db.add(document)
    db.flush()

    for index, content in enumerate(chunk_text(text)):
        db.add(
            Chunk(
                document_id=document.id,
                chunk_index=index,
                content=content,
                sha256=text_sha256(content),
                embedding=deterministic_embedding(content),
                metadata_json={"filename": document.filename, "source": document.source_label},
            )
        )
    db.flush()
    return document, True
