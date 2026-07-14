"""
Shared helpers used across API routers.
Reduces duplication between admin.py and rag.py upload logic.
"""
import hashlib
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.rag.retriever import index_document

SUPPORTED_RAG_TYPES = {
    "pdf", "docx", "txt", "md", "csv", "py", "js", "ts",
    "json", "yaml", "yml", "xml", "html", "css", "sql", "log",
}


def get_file_type(filename: str) -> str:
    """Extract lowercase file extension."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def upload_and_index_document(
    file: UploadFile,
    db: AsyncSession,
    *,
    source: str = "user",
    supported_types: set = None,
) -> Document:
    """
    Shared document upload + indexing pipeline.

    1. Validate file type
    2. Check for duplicate (SHA-256)
    3. Create Document row
    4. Index (chunk + embed + store)
    5. Return the Document ORM object

    Args:
        file: The uploaded file from FastAPI
        db: Async DB session
        source: "user" or "admin"
        supported_types: Set of allowed extensions (defaults to SUPPORTED_RAG_TYPES)

    Returns:
        The indexed Document ORM object.
    """
    if supported_types is None:
        supported_types = SUPPORTED_RAG_TYPES

    file_type = get_file_type(file.filename)
    if file_type not in supported_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_type}. Supported: {', '.join(sorted(supported_types))}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # Dedup by SHA-256
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    existing = await db.execute(
        select(Document).where(
            Document.content_hash == content_hash,
            Document.source == source,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This document has already been uploaded.")

    doc = Document(
        id=str(uuid4()),
        filename=file.filename,
        file_type=file_type,
        file_size=len(file_bytes),
        content_hash=content_hash,
        status="processing",
        source=source,
    )
    db.add(doc)
    await db.flush()

    try:
        await index_document(db, doc.id, file_bytes, file_type, file.filename)
        await db.commit()
    except Exception as e:
        doc.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Document indexing failed: {str(e)}")

    result = await db.execute(select(Document).where(Document.id == doc.id))
    return result.scalar_one()
