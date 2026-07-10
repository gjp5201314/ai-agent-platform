"""
Vector retrieval: search document chunks by semantic similarity.
Uses pgvector cosine distance operator (<=>).
"""
from typing import List
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk
from app.rag.embeddings import embed_query
from app.rag.chunker import split_text, extract_text_from_bytes
from app.schemas import RagSearchResult


async def search_similar(
    db: AsyncSession,
    query: str,
    top_k: int = 4,
    similarity_threshold: float = 0.5,
) -> List[RagSearchResult]:
    """
    Search for similar document chunks using pgvector cosine distance.
    Returns results sorted by similarity (highest first).
    """
    query_embedding = await embed_query(query)

    # pgvector cosine distance: <=> operator
    # distance = 1 - cosine_similarity, so similarity = 1 - distance
    stmt = (
        select(
            DocumentChunk,
            Document.filename,
            (1 - DocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity"),
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )

    result = await db.execute(stmt)
    rows = result.all()

    results = []
    for chunk, filename, similarity in rows:
        if similarity >= similarity_threshold:
            results.append(RagSearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                content=chunk.content,
                score=float(similarity),
            ))

    return results


async def index_document(
    db: AsyncSession,
    document_id: str,
    file_bytes: bytes,
    file_type: str,
    filename: str,
) -> int:
    """
    Process and index a document:
    1. Extract text
    2. Split into chunks
    3. Generate embeddings
    4. Store in database

    Returns the number of chunks created.
    """
    # 1. Extract text
    text = extract_text_from_bytes(file_bytes, file_type)
    if not text.strip():
        raise ValueError("No text content found in document")

    # 2. Split into chunks
    chunks = split_text(text, chunk_size=500, chunk_overlap=50)
    if not chunks:
        raise ValueError("Text splitting produced no chunks")

    # 3. Generate embeddings (batch)
    chunk_texts = [c.text for c in chunks]
    from app.rag.embeddings import embed_texts
    embeddings = await embed_texts(chunk_texts)

    # 4. Store chunks with embeddings
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

    # Update document chunk count and status
    from sqlalchemy import update
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(chunk_count=len(chunks), status="ready")
    )

    return len(chunks)
