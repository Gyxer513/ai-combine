"""Local semantic search over the combine's own Markdown docs.

EmbeddingGemma-300m (int8) via ONNX Runtime + FAISS — fully local, offline, no torch
and no API. Separate from the Nextcloud RAG. Build the index with
`python -m src.docs_search.index`; agents query it through the `search_docs` tool.
"""
