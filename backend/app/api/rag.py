"""
RAG endpoints — enterprise design: all operations use POST with JSON body.
No document IDs or query params ever appear in URLs.
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, DocumentChunk
from app.rag.chunker import extract_text_from_bytes
from app.rag.retriever import index_document, hybrid_search
from app.shared import upload_and_index_document
from app.schemas import (
    DocumentOut,
    RagSearchResult,
    RagSearchRequest,
    RagDocumentListRequest,
    RagDocumentGetRequest,
    RagDocumentDeleteRequest,
)


router = APIRouter()

# ---- Upload (multipart — unchanged, file upload requires form-data) ----

@router.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a document to the knowledge base.
    File is parsed, chunked, embedded, and stored in pgvector.
    Supported: PDF, DOCX, TXT, MD
    """
    doc = await upload_and_index_document(file, db, source="user")
    return doc


# ---- List (POST body) ----

@router.post("/documents/list", response_model=list[DocumentOut])
async def list_documents(
    request: RagDocumentListRequest,
    db: AsyncSession = Depends(get_db),
):
    """List all documents (pagination in POST body, not query string)."""
    result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(request.skip)
        .limit(request.limit)
    )
    return result.scalars().all()


# ---- Get (POST body) ----

@router.post("/documents/get", response_model=DocumentOut)
async def get_document(
    request: RagDocumentGetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Get a single document's metadata (doc_id in POST body)."""
    result = await db.execute(select(Document).where(Document.id == request.id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# ---- Delete (POST body) ----

@router.post("/documents/delete")
async def delete_document(
    request: RagDocumentDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and all its chunks (doc_id in POST body)."""
    result = await db.execute(select(Document).where(Document.id == request.id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.execute(delete(Document).where(Document.id == request.id))
    await db.commit()
    return {"detail": f"Document '{doc.filename}' deleted successfully"}


# ---- Search (POST body — already was POST) ----

@router.post("/search", response_model=list[RagSearchResult])
async def search_knowledge_base(
    request: RagSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Hybrid search the knowledge base (semantic + BM25 keyword)."""
    results = await hybrid_search(
        db,
        query=request.query,
        top_k=request.top_k,
    )
    return results


# ---- Stats (POST — no params needed) ----

@router.post("/stats")
async def knowledge_base_stats(db: AsyncSession = Depends(get_db)):
    """Get knowledge base statistics (POST, no sensitive params)."""
    doc_count = await db.execute(select(func.count(Document.id)))
    chunk_count = await db.execute(select(func.count(DocumentChunk.id)))
    total_size = await db.execute(select(func.sum(Document.file_size)))

    return {
        "document_count": doc_count.scalar(),
        "chunk_count": chunk_count.scalar(),
        "total_size_mb": round((total_size.scalar() or 0) / 1024 / 1024, 2),
    }
