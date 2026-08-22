from __future__ import annotations

import math

import pytest
from knowledge_ops.documents import (
    DocumentError,
    chunk_text,
    deterministic_embedding,
    extract_text,
)
from knowledge_ops.models import EMBEDDING_DIMENSIONS


def test_embedding_is_deterministic_and_normalized() -> None:
    first = deterministic_embedding("文件權限需要主管核准")
    second = deterministic_embedding("文件權限需要主管核准")
    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-6)


def test_chunk_text_preserves_content() -> None:
    source = "第一段。" * 200 + "\n\n" + "第二段。" * 200
    chunks = chunk_text(source, chunk_size=200, overlap=20)
    assert len(chunks) > 2
    assert all(len(chunk) <= 220 for chunk in chunks)


def test_extract_text_rejects_unsupported_and_invalid_encoding() -> None:
    with pytest.raises(DocumentError, match="Unsupported"):
        extract_text("sample.exe", b"content")
    with pytest.raises(DocumentError, match="UTF-8"):
        extract_text("sample.txt", b"\xff\xfe\xff")


def test_extract_json_is_searchable_text() -> None:
    text = extract_text("sample.json", b'{"policy": "least privilege"}')
    assert "least privilege" in text
