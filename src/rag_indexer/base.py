"""Общие типы индексатора."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(slots=True)
class RagDocument:
    """Документ из источника (Notes/WebDAV) до чанкинга."""

    namespace: str
    doc_id: str  # стабильный id: 'note:123' / 'webdav:/Knowledge/x.md'
    source: str  # 'notes' | 'webdav'
    path: str  # человекочитаемое расположение
    text: str
    modified: str  # iso/epoch как строка

    def content_hash(self) -> str:
        """Хэш содержимого — чтобы пропускать неизменённые документы."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()
