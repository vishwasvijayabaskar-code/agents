"""Tests for codebase indexing and query (Option C)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.codebase import (
    _INDEX_EXTS,
    _SKIP_DIRS,
    CodebaseIndex,
    _chunk_file,
    _collection_name,
    _iter_files,
)


class TestCollectionName:
    def test_returns_string(self, tmp_path):
        name = _collection_name(str(tmp_path))
        assert isinstance(name, str)

    def test_starts_with_codebase(self, tmp_path):
        name = _collection_name(str(tmp_path))
        assert name.startswith("codebase_")

    def test_same_path_same_name(self, tmp_path):
        assert _collection_name(str(tmp_path)) == _collection_name(str(tmp_path))

    def test_different_paths_different_names(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert _collection_name(str(a)) != _collection_name(str(b))


class TestIterFiles:
    def test_finds_python_files(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "helper.py").write_text("y = 2")
        files = list(_iter_files(tmp_path))
        names = [rel for _, rel in files]
        assert "main.py" in names
        assert "helper.py" in names

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "pkg.js").write_text("x")
        files = list(_iter_files(tmp_path))
        assert not any("node_modules" in rel for _, rel in files)

    def test_skips_pycache(self, tmp_path):
        pc = tmp_path / "__pycache__"
        pc.mkdir()
        (pc / "mod.pyc").write_text("")
        files = list(_iter_files(tmp_path))
        assert not any("__pycache__" in rel for _, rel in files)

    def test_skips_git(self, tmp_path):
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_text("")
        files = list(_iter_files(tmp_path))
        assert not any(".git" in rel for _, rel in files)

    def test_skips_large_files(self, tmp_path):
        big = tmp_path / "big.py"
        big.write_bytes(b"x" * 200_000)  # over limit
        files = list(_iter_files(tmp_path))
        assert not any("big.py" in rel for _, rel in files)

    def test_skips_unknown_extensions(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "data.csv").write_text("a,b,c")
        files = list(_iter_files(tmp_path))
        # .csv not in _INDEX_EXTS
        assert not any("data.csv" in rel for _, rel in files)

    def test_finds_markdown(self, tmp_path):
        (tmp_path / "README.md").write_text("# title")
        files = list(_iter_files(tmp_path))
        assert any("README.md" in rel for _, rel in files)

    def test_nested_directories(self, tmp_path):
        sub = tmp_path / "src" / "utils"
        sub.mkdir(parents=True)
        (sub / "helpers.py").write_text("def f(): pass")
        files = list(_iter_files(tmp_path))
        assert any("helpers.py" in rel for _, rel in files)


class TestChunkFile:
    def test_python_chunks_by_function(self):
        code = "def foo():\n    return 1\n\ndef bar():\n    return 2\n" * 10
        chunks = _chunk_file(code, "test.py")
        assert len(chunks) >= 2
        assert all("content" in c for c in chunks)
        assert all("file" in c for c in chunks)
        assert all("start_line" in c for c in chunks)

    def test_non_python_uses_fixed_chunks(self):
        code = "x " * 1000  # 2000 chars
        chunks = _chunk_file(code, "test.js")
        assert len(chunks) >= 2
        assert all(len(c["content"]) <= 900 for c in chunks)  # within chunk size + small tolerance

    def test_small_file_single_chunk(self):
        code = "const x = 1;\n"
        chunks = _chunk_file(code, "small.js")
        assert len(chunks) == 1
        assert chunks[0]["content"].strip() == "const x = 1;"

    def test_chunk_metadata_has_file_path(self):
        chunks = _chunk_file("def f(): pass", "src/module.py")
        assert chunks[0]["file"] == "src/module.py"

    def test_empty_file_returns_no_chunks(self):
        # Empty content: no chunks or one empty chunk
        chunks = _chunk_file("", "empty.py")
        # Either 0 chunks or the single chunk has empty content
        non_empty = [c for c in chunks if c["content"].strip()]
        assert len(non_empty) == 0


class TestCodebaseIndex:
    def test_not_indexed_initially(self, tmp_path):
        with patch("helpers.codebase._CHROMA_DIR", str(tmp_path / "chroma")):
            idx = CodebaseIndex(str(tmp_path / "project"))
            # Can't fully test without chromadb but mock it
            with patch.object(idx, "_get_collection", return_value=None):
                assert not idx.is_indexed()

    def test_index_returns_zero_without_chromadb(self, tmp_path):
        idx = CodebaseIndex(str(tmp_path))
        with patch.object(idx, "_get_collection", return_value=None):
            result = idx.index()
            assert result == 0

    def test_query_returns_empty_without_chromadb(self, tmp_path):
        idx = CodebaseIndex(str(tmp_path))
        with patch.object(idx, "_get_collection", return_value=None):
            result = idx.query("how does auth work?")
            assert result == ""

    def test_stats_without_chromadb(self, tmp_path):
        idx = CodebaseIndex(str(tmp_path))
        with patch.object(idx, "_get_collection", return_value=None):
            stats = idx.stats()
            assert stats["chunks"] == 0
            assert stats["indexed"] is False

    def test_index_skips_if_already_indexed(self, tmp_path):
        """index() returns early if already indexed and force=False."""
        idx = CodebaseIndex(str(tmp_path))
        mock_col = MagicMock()
        mock_col.count.return_value = 50
        with patch.object(idx, "_get_collection", return_value=mock_col):
            result = idx.index(force=False)
            assert result == 50
            # upsert should NOT have been called
            mock_col.upsert.assert_not_called()

    def test_query_formats_context(self, tmp_path):
        """query() returns formatted context string."""
        idx = CodebaseIndex(str(tmp_path))
        mock_col = MagicMock()
        mock_col.count.return_value = 10
        mock_col.query.return_value = {
            "documents": [["def auth(): pass"]],
            "metadatas": [[{"file": "auth.py", "start_line": 1, "end_line": 5}]],
            "distances": [[0.1]],
        }
        with patch.object(idx, "_get_collection", return_value=mock_col):
            result = idx.query("how does auth work?")
        assert "auth.py" in result
        assert "def auth()" in result

    def test_query_filters_distant_results(self, tmp_path):
        """Chunks with distance > 1.5 are excluded."""
        idx = CodebaseIndex(str(tmp_path))
        mock_col = MagicMock()
        mock_col.count.return_value = 10
        mock_col.query.return_value = {
            "documents": [["irrelevant content"]],
            "metadatas": [[{"file": "x.py", "start_line": 1, "end_line": 1}]],
            "distances": [[2.0]],  # very far
        }
        with patch.object(idx, "_get_collection", return_value=mock_col):
            result = idx.query("auth question")
        assert result == ""

    def test_collection_name_stable(self, tmp_path):
        idx = CodebaseIndex(str(tmp_path))
        assert idx._collection_name == _collection_name(str(tmp_path.resolve()))
