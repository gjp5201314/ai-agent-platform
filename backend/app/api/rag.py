"""
RAG endpoints: document upload, list, delete, and search.
"""
import hashlib
from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, DocumentChunk
from app.rag.chunker import extract_text_from_bytes
from app.rag.retriever import index_document, search_similar
from app.schemas import DocumentOut, RagSearchResult, RagSearchRequest


router = APIRouter()


SUPPORTED_TYPES = {"pdf", "docx", "txt", "md"}


def _get_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower().lstrip(".") if "." in filename else ""
    return ext


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a document to the knowledge base.
    The file is parsed, chunked, embedded, and stored in pgvector.

    Supported types: PDF, DOCX, TXT, MD
    """
    file_type = _get_file_type(file.filename)
    if file_type not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_type}. Supported: {', '.join(SUPPORTED_TYPES)}",
        )

    # Read file
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Dedup check
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = await db.execute(
        select(Document).where(Document.content_hash == content_hash)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This document has already been uploaded.")

    # Create document record
    doc = Document(
        id=str(uuid4()),
        filename=file.filename,
        file_type=file_type,
        file_size=len(file_bytes),
        content_hash=content_hash,
        status="processing",
    )
    db.add(doc)
    await db.flush()

    # Process and index (extract → chunk → embed → store)
    try:
        chunk_count = await index_document(db, doc.id, file_bytes, file_type, file.filename)
        await db.commit()
    except Exception as e:
        # Mark as error
        doc.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Document indexing failed: {str(e)}")

    # Return fresh
    result = await db.execute(select(Document).where(Document.id == doc.id))
    return result.scalar_one()


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all documents in the knowledge base."""
    result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single document's metadata."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a document and all its chunks."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Chunks cascade-delete via FK
    await db.execute(delete(Document).where(Document.id == doc_id))
    await db.commit()
    return {"detail": f"Document '{doc.filename}' deleted successfully"}


@router.post("/search", response_model=list[RagSearchResult])
async def search_knowledge_base(
    request: RagSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Search the knowledge base (pgvector semantic search).
    Returns matching document chunks with similarity scores.
    """
    results = await search_similar(
        db,
        query=request.query,
        top_k=request.top_k,
    )
    return results


@router.get("/stats")
async def knowledge_base_stats(db: AsyncSession = Depends(get_db)):
    """Get knowledge base statistics."""
    doc_count = await db.execute(select(func.count(Document.id)))
    chunk_count = await db.execute(select(func.count(DocumentChunk.id)))
    total_size = await db.execute(select(func.sum(Document.file_size)))

    return {
        "document_count": doc_count.scalar(),
        "chunk_count": chunk_count.scalar(),
        "total_size_mb": round((total_size.scalar() or 0) / 1024 / 1024, 2),
    }
