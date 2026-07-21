"""
================================================================================
  文档分块工具（Document Chunker）
================================================================================

本模块负责将文档内容切分成适合 RAG 检索的文本块（chunks）。

================================================================================
  分块策略（Chunking Strategy）
================================================================================

  使用 LangChain 的 RecursiveCharacterTextSplitter 进行递归分块：

  1. 递归分割顺序
     按以下分隔符顺序逐级尝试分割，优先在自然边界断开：
       "\n\n"  → 段落边界（最高优先级，尽量不破坏段落完整性）
       "\n"    → 行边界
       "。"    → 中文句号
       "."     → 英文句号
       "!"     → 感叹号
       "?"     → 问号
       " "     → 空格
       ""      → 字符级（最后手段，逐字分割）

  2. 块参数
     - chunk_size = 500（字符数，非 token 数，适合中英混合文本）
     - chunk_overlap = 50（相邻块重叠 50 字符，保证上下文连续性）
     - length_function = len(t)（基于字符数而非 token 数，统一度量）

  3. 重叠机制的意义
     块之间的重叠确保关键信息不会因刚好落在分割边界而丢失。
     例如：一段文字"数据库索引优化策略"若恰好被"数据库索引 | 优化策略"
     分割，重叠部分保证"索引"和"优化策略"的关系在相邻块中都被保留。

  4. Token 估算
     中英文混合文本粗略按 2 字符 ≈ 1 token 估算：
     token_count = len(chunk_text) // 2

================================================================================
  支持的文件格式（Supported File Types）
================================================================================

  ┌─────────┬────────────────────┬─────────────────────────────────┐
  │ 格式     │ 后缀               │ 说明                            │
  ├─────────┼────────────────────┼─────────────────────────────────┤
  │ PDF     │ .pdf               │ 使用 pypdf 提取文本层内容         │
  │         │                    │ 注意：扫描版 PDF（图片）无法提取   │
  ├─────────┼────────────────────┼─────────────────────────────────┤
  │ Word    │ .docx              │ 使用 python-docx 提取段落文本     │
  │         │                    │ 仅提取正文，不包含表格/图片       │
  ├─────────┼────────────────────┼─────────────────────────────────┤
  │ 纯文本  │ .txt               │ UTF-8 解码，遇非法字符时替换     │
  ├─────────┼────────────────────┼─────────────────────────────────┤
  │ Markdown│ .md, .markdown     │ UTF-8 解码，保留原始格式标记     │
  └─────────┴────────────────────┴─────────────────────────────────┘

  extract_text_from_bytes() 是统一的入口函数，根据 file_type 自动分发到
  对应的提取函数。
"""
from typing import List
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class Chunk:
    """
    文档块数据结构

    Attributes:
        text: 块文本内容（最多 chunk_size 字符）
        index: 块在原文档中的序号（从 0 开始）
        token_count: 估算的 token 数量（字符数 / 2）
    """
    text: str
    index: int
    token_count: int


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[Chunk]:
    """
    使用递归字符分割器将文本切分为重叠的文本块。

    分割策略：按段落 → 行 → 句子 → 字符的优先级递归分割，
    确保尽量在自然边界处断开。

    Args:
        text: 要分割的纯文本
        chunk_size: 每块最大字符数（默认 500 字符）
                    注意这是字符数而非 token 数，中英混合文本适用
        chunk_overlap: 相邻块重叠字符数（默认 50 字符）
                       重叠保证关键信息不因切分边界而丢失

    Returns:
        Chunk 对象列表，按原文档顺序排列
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # 分割符优先级：段落 > 行 > 中文句号 > 英文句号 > 感叹号 > 问号 > 空格 > 字符
        separators=["\n\n", "\n", "。", ".", "!", "?", " ", ""],
        length_function=lambda t: len(t),  # 基于字符数（适合中英混合文本）
    )
    chunks = splitter.split_text(text)
    return [
        Chunk(text=c, index=i, token_count=len(c) // 2)
        for i, c in enumerate(chunks)
    ]


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    从 PDF 文件的字节内容中提取纯文本。

    使用 pypdf 库逐页提取文本层内容。
    注意：仅支持含有文本层的 PDF（电子生成或 OCR 后），
    纯图片扫描版 PDF 无法提取文字。

    Args:
        file_bytes: PDF 文件的原始字节

    Returns:
        提取的纯文本，各页之间以两个换行分隔
    """
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
    """
    从 DOCX 文件的字节内容中提取纯文本。

    使用 python-docx 库提取所有段落文本。
    当前仅提取段落正文，不包含表格、图片、页眉页脚。

    Args:
        file_bytes: DOCX 文件的原始字节

    Returns:
        提取的纯文本，各非空段落以两个换行分隔
    """
    from docx import Document
    import io

    doc = Document(io.BytesIO(file_bytes))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text_from_bytes(file_bytes: bytes, file_type: str) -> str:
    """
    根据文件类型从字节内容中提取纯文本（统一入口）。

    支持的文件类型：
    - pdf  → 调用 extract_text_from_pdf()
    - docx → 调用 extract_text_from_docx()
    - txt, md, markdown → 直接 UTF-8 解码

    Args:
        file_bytes: 文件的原始字节内容
        file_type: 文件类型后缀（不区分大小写，可选带 "."）

    Returns:
        提取的纯文本字符串

    Raises:
        ValueError: 文件类型不在支持列表中
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
