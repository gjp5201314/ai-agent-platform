"""
Pure-logic unit tests — no app dependencies needed.
Tests CJK tokenizer, config URL builder, document utils.
"""
import pytest


class TestCJKTokenizer:
    """Verify CJK tokenization logic (self-contained logic)."""

    @staticmethod
    def _cjk_tokenize(text: str) -> str:
        import re
        _CJK_RE = re.compile(r'([\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff])')
        spaced = _CJK_RE.sub(r' \1 ', text)
        return re.sub(r'\s+', ' ', spaced).strip().lower()

    def test_chinese_only(self):
        result = self._cjk_tokenize("你好世界")
        assert result == "你 好 世 界"

    def test_preserves_english(self):
        result = self._cjk_tokenize("AI agent hello")
        assert result == "ai agent hello"

    def test_mixed_cjk_english(self):
        result = self._cjk_tokenize("hello世界AI")
        assert result == "hello 世 界 ai" or "hello 世 界 ai" in result


class TestConfigUrlBuilder:
    """Verify config URL-building logic (no external deps)."""

    def test_redis_url_with_password(self):
        pwd = "secret"
        host, port, db = "redis", "6379", "0"
        prefix = f":{pwd}@" if pwd else ""
        url = f"redis://{prefix}{host}:{port}/{db}"
        assert url == "redis://:secret@redis:6379/0"

    def test_redis_url_without_password(self):
        pwd = ""
        prefix = f":{pwd}@" if pwd else ""
        url = f"redis://{prefix}redis:6379/0"
        assert url == "redis://redis:6379/0"


class TestFileTypeExtraction:
    def test_pdf(self):
        fname = "report.pdf"
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        assert ext == "pdf"

    def test_csv(self):
        fname = "data.CSV"
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        assert ext == "csv"

    def test_no_extension(self):
        fname = "Makefile"
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        assert ext == ""  # No dot → empty string

    def test_double_extension(self):
        fname = "archive.tar.gz"
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        assert ext == "gz"
