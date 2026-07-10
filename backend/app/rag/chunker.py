"""
Document chunking utilities.
Splits documents into overlapping text chunks for RAG.
"""
from typing import List
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class Chunk:
    text: str
    index: int
    token_count: int


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[Chunk]:
    """
    Split text into overlapping chunks using recursive character splitter.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", ".", "!", "?", " ", ""],
        length_function=lambda t: len(t),  # character-based; good for mixed CN/EN
    )
    chunks = splitter.split_text(text)
    return [
        Chunk(text=c, index=i, token_count=len(c) // 2)
        for i, c in enumerate(chunks)
    ]


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes."""
    from pypdf import PdfReader
    import io

    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX bytes."""
    from docx import Document
    import io

    doc = Document(io.BytesIO(file_bytes))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text_from_bytes(file_bytes: bytes, file_type: str) -> str:
    """
    Extract plain text from file bytes based on type.
    Supported: pdf, docx, txt, md
    """
    file_type = file_type.lower().lstrip(".")
    if file_type == "pdf":
        return extract_text_from_pdf(file_bytes)
    elif file_type == "docx":
        return extract_text_from_docx(file_bytes)
    elif file_type in ("txt", "md", "markdown"):
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
