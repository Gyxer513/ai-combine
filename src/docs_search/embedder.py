"""Local ONNX embedder for EmbeddingGemma-300m (int8). No torch.

Lazily downloads the quantized ONNX model + tokenizer from Hugging Face (cached to a
volume) and produces L2-normalized sentence embeddings via masked mean pooling.
EmbeddingGemma expects task-specific prompt prefixes for retrieval (query vs document),
so `embed()` takes a `kind` and prepends the configured prefix.

Heavy deps (onnxruntime, tokenizers, huggingface_hub, numpy) are imported lazily so the
base install — without the `docs` extra — can still import this module and report a
clean "not installed" error instead of crashing.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from src.orchestrator.config import settings

if TYPE_CHECKING:  # only for type checkers, never imported at runtime in base install
    import numpy as np


class DocsEmbedderUnavailable(RuntimeError):
    """Raised when the `docs` extra (onnxruntime/tokenizers/...) is not installed."""


def _require_deps():
    """Import the heavy deps or raise a friendly error. Returns the modules."""
    try:
        import numpy as np
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
    except ImportError as exc:  # extra not installed
        raise DocsEmbedderUnavailable(
            "docs search needs the 'docs' extra: uv sync --extra docs "
            "(onnxruntime, faiss-cpu, tokenizers, huggingface-hub, numpy)"
        ) from exc
    return np, ort, hf_hub_download, Tokenizer


class DocsEmbedder:
    """EmbeddingGemma ONNX embedder. Thread-safe lazy load; reused across queries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None
        self._input_names: set[str] = set()
        self._np = None

    # -- loading -------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        with self._lock:
            if self._session is not None:
                return
            np, ort, hf_hub_download, Tokenizer = _require_deps()
            token = settings.hf_token or None
            cache = settings.docs_model_cache
            model_path = hf_hub_download(
                settings.docs_model_repo,
                settings.docs_model_file,
                cache_dir=cache,
                token=token,
            )
            tok_path = hf_hub_download(
                settings.docs_model_repo,
                settings.docs_tokenizer_file,
                cache_dir=cache,
                token=token,
            )
            sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            tokenizer = Tokenizer.from_file(tok_path)
            tokenizer.enable_truncation(max_length=1024)
            tokenizer.enable_padding()
            self._np = np
            self._session = sess
            self._tokenizer = tokenizer
            self._input_names = {i.name for i in sess.get_inputs()}

    # -- embedding -----------------------------------------------------------

    def embed(self, texts: list[str], *, kind: str = "document") -> np.ndarray:
        """Embed texts -> (n, dim) float32, L2-normalized. kind: 'query' | 'document'."""
        self._ensure_loaded()
        np = self._np
        prefix = settings.docs_query_prefix if kind == "query" else settings.docs_doc_prefix
        encs = self._tokenizer.encode_batch([prefix + (t or "") for t in texts])

        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feeds: dict[str, object] = {}
        if "input_ids" in self._input_names:
            feeds["input_ids"] = ids
        if "attention_mask" in self._input_names:
            feeds["attention_mask"] = mask
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        if "position_ids" in self._input_names:
            feeds["position_ids"] = np.broadcast_to(
                np.arange(ids.shape[1], dtype=np.int64), ids.shape
            ).copy()

        outputs = self._session.run(None, feeds)
        out_names = [o.name for o in self._session.get_outputs()]
        vecs = self._pool(outputs, out_names, mask)
        vecs = vecs[:, : settings.docs_model_dim]  # Matryoshka truncation if configured
        return self._normalize(vecs)

    def embed_one(self, text: str, *, kind: str = "query") -> np.ndarray:
        return self.embed([text], kind=kind)[0]

    # -- helpers -------------------------------------------------------------

    def _pool(self, outputs, out_names, mask) -> np.ndarray:
        """Use a ready sentence embedding if the export has one, else masked mean pool."""
        np = self._np
        for name in ("sentence_embedding", "sentence_embeddings", "pooler_output"):
            if name in out_names:
                return outputs[out_names.index(name)].astype(np.float32)
        hidden = outputs[0].astype(np.float32)  # (n, seq, dim) last_hidden_state
        m = mask.astype(np.float32)[:, :, None]
        summed = (hidden * m).sum(axis=1)
        counts = np.clip(m.sum(axis=1), 1e-9, None)
        return summed / counts

    def _normalize(self, vecs) -> np.ndarray:
        np = self._np
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return (vecs / np.clip(norms, 1e-12, None)).astype(np.float32)
