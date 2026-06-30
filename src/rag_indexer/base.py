"""Shared indexer types."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(slots=True)
class RagDocument:
    """A document from a source (Notes/WebDAV) before chunking."""

    namespace: str
    doc_id: str  # stable id: 'note:123' / 'webdav:/Knowledge/x.md'
    source: str  # 'notes' | 'webdav'
    path: str  # human-readable location
    text: str
    modified: str  # iso/epoch as a string

    def content_hash(self) -> str:
        """Content hash — to skip unchanged documents."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()
