"""
Hybrid retrieval: vector semantic search + BM25 keyword search.
Fuses results via Reciprocal Rank Fusion (RRF) for enterprise-grade accuracy.

Chinese text support: pre-tokenizes CJK characters for PostgreSQL tsvector
since the 'simple' config cannot segment Chinese words. Each Chinese character
becomes a separate token; English words stay intact.
"""
import re
from typing import List, Tuple, Optional
from uuid import uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk
from app.rag.embeddings import embed_query, embed_texts
from app.rag.chunker import split_text, extract_text_from_bytes
from app.schemas import RagSearchResult
from app.core.logger import logger


# ============================================================
#  CJK Tokenizer — makes Chinese searchable via tsvector
# ============================================================

# Regex: match any single CJK Unified Ideograph
_CJK_RE = re.compile(r'([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])')


def _cjk_tokenize(text: str) -> str:
    """
    Insert spaces around each CJK character so PostgreSQL tsvector
    treats them as separate tokens for proper Chinese keyword matching.

    Example: "你好世界AI agent" → "你 好 世 界 AI agent"
    """
    spaced = _CJK_RE.sub(r' \1 ', text)
    return re.sub(r'\s+', ' ', spaced).strip().lower()


# ============================================================
#  Keyword (BM25-style) Search — PostgreSQL tsvector/tsquery
# ============================================================

async def keyword_search(
    db: AsyncSession,
    query: str,
    top_k: int = 6,
    source: Optional[str] = None,
) -> List[Tuple[str, str, str, str, float]]:
    """
    Full-text keyword search using PostgreSQL tsvector/tsquery.
    Chinese text is pre-tokenized into individual characters for matching.
    If source is set, filters to only that document source ("user" / "admin").
    Returns list of (chunk_id, document_id, filename, content, score).
    """
    tokenized_query = _cjk_tokenize(query)

    source_filter = "AND d.source = :source" if source else ""

    stmt = text(f"""
        SELECT
            dc.id AS chunk_id,
            dc.document_id,
            d.filename,
            dc.content,
            ts_rank(dc.search_vector, plainto_tsquery('simple', :query)) AS score
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE dc.search_vector @@ plainto_tsquery('simple', :query)
        {source_filter}
        ORDER BY score DESC
        LIMIT :top_k
    """)

    result = await db.execute(stmt, {"query": tokenized_query, "top_k": top_k, "source": source} if source else {"query": tokenized_query, "top_k": top_k})
    return [(row[0], row[1], row[2], row[3], float(row[4])) for row in result.fetchall()]


# ============================================================
#  Vector (Semantic) Search — pgvector cosine distance
# ============================================================

async def vector_search(
    db: AsyncSession,
    query: str,
    top_k: int = 6,
    source: Optional[str] = None,
) -> List[Tuple[str, str, str, str, float]]:
    """
    Semantic search using pgvector cosine distance.
    If source is set, filters to only that document source ("user" / "admin").
    Returns list of (chunk_id, document_id, filename, content, similarity).
    """
    query_embedding = await embed_query(query)

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.filename,
            DocumentChunk.content,
            (1 - DocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity"),
        )
        .join(Document, DocumentChunk.document_id == Document.id)
    )

    if source:
        stmt = stmt.where(Document.source == source)

    stmt = stmt.order_by(DocumentChunk.embedding.cosine_distance(query_embedding)).limit(top_k)

    result = await db.execute(stmt)
    return [(row[0], row[1], row[2], row[3], float(row[4])) for row in result.fetchall()]


# ============================================================
#  Reciprocal Rank Fusion (RRF)
# ============================================================

def _rrf_fuse(
    vector_rows: List[Tuple[str, str, str, str, float]],
    keyword_rows: List[Tuple[str, str, str, str, float]],
    k: int = 60,
) -> List[Tuple[str, str, str, str, float]]:
    """
    Merge two ranked result lists using Reciprocal Rank Fusion.

    RRF score = Σ 1 / (k + rank_i)
    where rank_i is the position (0-based) in each list.

    Args:
        vector_rows: results from semantic search
        keyword_rows: results from keyword search
        k: RRF constant (default 60, per research standard)

    Returns:
        Merged list sorted by combined RRF score, best first.
    """
    # Build id → row map
    row_map: dict[str, Tuple[str, str, str, str, float]] = {}
    for row in vector_rows + keyword_rows:
        row_map[row[0]] = row

    # Compute RRF scores
    rrf_scores: dict[str, float] = {}
    for rank, row in enumerate(vector_rows):
        rrf_scores[row[0]] = rrf_scores.get(row[0], 0.0) + 1.0 / (k + rank + 1)
    for rank, row in enumerate(keyword_rows):
        rrf_scores[row[0]] = rrf_scores.get(row[0], 0.0) + 1.0 / (k + rank + 1)

    # Sort by RRF score descending
    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

    return [row_map[cid] for cid in sorted_ids]


# ============================================================
#  Hybrid Search — main entry point
# ============================================================

async def hybrid_search(
    db: AsyncSession,
    query: str,
    top_k: int = 4,
    similarity_threshold: float = 0.5,
    source: Optional[str] = None,
) -> List[RagSearchResult]:
    """
    Hybrid search combining vector semantics + BM25 keyword matching.
    If source is set, only searches that document source ("user" / "admin").
    """
    fetch_k = max(top_k * 3, 10)

    # DEBUG: Log search parameters
    logger.debug(f"hybrid_search: query='{query[:50]}', top_k={top_k}, threshold={similarity_threshold}, source={source}")

    # Run both searches in parallel
    try:
        vector_rows = await vector_search(db, query, top_k=fetch_k, source=source)
        logger.debug(f"vector_search returned {len(vector_rows)} results")
    except Exception as e:
        logger.warning(f"vector_search FAILED: {e}")
        vector_rows = []
    try:
        keyword_rows = await keyword_search(db, query, top_k=fetch_k, source=source)
        logger.debug(f"keyword_search returned {len(keyword_rows)} results")
    except Exception as e:
        logger.warning(f"keyword_search FAILED: {e}")
        keyword_rows = []

    # RRF fusion
    fused = _rrf_fuse(vector_rows, keyword_rows)
    logger.debug(f"RRF fused: {len(fused)} results")

    # Build result objects with threshold filtering
    results: List[RagSearchResult] = []
    for chunk_id, doc_id, filename, content, _score in fused:
        if len(results) >= top_k:
            break
        results.append(RagSearchResult(
            chunk_id=chunk_id,
            document_id=doc_id,
            filename=filename,
            content=content,
            score=round(_score, 4),
        ))

    return results


# ============================================================
#  Legacy semantic-only search (kept for backward compat)
# ============================================================

async def search_similar(
    db: AsyncSession,
    query: str,
    top_k: int = 4,
    similarity_threshold: float = 0.5,
) -> List[RagSearchResult]:
    """
    Pure semantic search (pgvector only).
    Kept for backward compatibility; prefer hybrid_search() for production.
    """
    rows = await vector_search(db, query, top_k=top_k)

    results = []
    for chunk_id, doc_id, filename, content, similarity in rows:
        if similarity >= similarity_threshold:
            results.append(RagSearchResult(
                chunk_id=chunk_id,
                document_id=doc_id,
                filename=filename,
                content=content,
                score=float(similarity),
            ))
    return results


# ============================================================
#  Document Indexing (updated to populate tsvector)
# ============================================================

async def index_document(
    db: AsyncSession,
    document_id: str,
    file_bytes: bytes,
    file_type: str,
    filename: str,
) -> int:
    """
    Process and index a document: extract → chunk → embed → store.
    Also populates search_vector (tsvector) for hybrid BM25 search.
    Returns chunk count.
    """
    # 1. Extract text
    text_content = extract_text_from_bytes(file_bytes, file_type)
    if not text_content.strip():
        raise ValueError("No text content found in document")

    # 2. Split into chunks
    chunks = split_text(text_content, chunk_size=500, chunk_overlap=50)
    if not chunks:
        raise ValueError("Text splitting produced no chunks")

    # 3. Generate embeddings (batch)
    chunk_texts = [c.text for c in chunks]
    embeddings = await embed_texts(chunk_texts)

    # 4. Store chunks with embeddings, then populate tsvector via raw SQL
    chunk_records = []
    for chunk, embedding in zip(chunks, embeddings):
        chunk_record = DocumentChunk(
            id=str(uuid4()),
            document_id=document_id,
            chunk_index=chunk.index,
            content=chunk.text,
            embedding=embedding,
            token_count=chunk.token_count,
        )
        db.add(chunk_record)
        chunk_records.append(chunk_record)

    await db.flush()

    # Populate tsvector with CJK-tokenized content for BM25 keyword index
    for cr in chunk_records:
        tokenized = _cjk_tokenize(cr.content)
        await db.execute(
            text("""
                UPDATE document_chunks
                SET search_vector = to_tsvector('simple', :content)
                WHERE id = :chunk_id
            """),
            {"content": tokenized, "chunk_id": cr.id},
        )

    # Update document chunk count and status
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(chunk_count=len(chunks), status="ready")
    )

    return len(chunks)
