"""ai3 retrieval stack (zip manifest, ingest, search, rerank, citations)."""

from .zip_manifest import sync_zip_manifest
from .zip_ingest import index_zip_archive
from .vault_catalog import load_catalog, sync_catalog, index_catalog
from .fts import search_fts
from .vector_lancedb import search_vectors, upsert_vector
from .reranker import merge_and_rerank
from .citations import persist_citations
from .citation_verify import verify_run_citations

__all__ = [
    "sync_zip_manifest",
    "index_zip_archive",
    "load_catalog",
    "sync_catalog",
    "index_catalog",
    "search_fts",
    "search_vectors",
    "upsert_vector",
    "merge_and_rerank",
    "persist_citations",
    "verify_run_citations",
]
