"""Codebase indexing and semantic search (Option C).

Indexes a code repository into ChromaDB — one collection per project.
Chunks files by logical boundaries, embeds, stores with metadata.
Query returns the most relevant code chunks for a given question.

Usage:
    from helpers.codebase import CodebaseIndex
    idx = CodebaseIndex("/path/to/project")
    idx.index()                          # first-time indexing
    ctx = idx.query("how does auth work?")  # returns relevant code context
"""

import hashlib
import os
from pathlib import Path

# File extensions to index
_INDEX_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go",
    ".java", ".cpp", ".c", ".h", ".rb", ".php", ".swift",
    ".kt", ".cs", ".md", ".txt", ".yaml", ".yml", ".toml",
    ".json", ".sh", ".bash", ".zsh",
}

# Dirs / files to always skip
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", "target",
    ".cargo", "vendor", "chroma", ".pytest_cache", ".mypy_cache",
    "coverage", ".coverage", "htmlcov",
}

# Max file size to index (skip large generated files)
_MAX_FILE_BYTES = 100_000

# Chunk size in characters (overlapping chunks for better retrieval)
_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100

_CHROMA_DIR = str(Path(__file__).parent.parent / "chroma")


def _collection_name(project_path: str) -> str:
    """Stable collection name derived from absolute project path."""
    abspath = str(Path(project_path).resolve())
    return "codebase_" + hashlib.md5(abspath.encode()).hexdigest()[:12]


def _iter_files(root: Path):
    """Walk project, yield (path, relative_path) for indexable files."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in _INDEX_EXTS:
                continue
            if fpath.stat().st_size > _MAX_FILE_BYTES:
                continue
            rel = fpath.relative_to(root)
            yield fpath, str(rel)


def _chunk_file(content: str, file_path: str) -> list[dict]:
    """Split file content into overlapping chunks with metadata."""
    chunks = []
    lines = content.splitlines(keepends=True)

    # For Python files, try to chunk by top-level functions/classes
    if file_path.endswith(".py"):
        current_chunk: list[str] = []
        current_start = 1
        chunk_chars = 0

        for i, line in enumerate(lines, 1):
            is_boundary = (
                line.startswith("def ") or
                line.startswith("class ") or
                line.startswith("async def ")
            )
            if is_boundary and chunk_chars > _CHUNK_SIZE // 2 and current_chunk:
                chunks.append({
                    "content": "".join(current_chunk),
                    "file": file_path,
                    "start_line": current_start,
                    "end_line": i - 1,
                })
                # Overlap: keep last few lines
                overlap_lines = current_chunk[-3:] if len(current_chunk) > 3 else current_chunk[:]
                current_chunk = overlap_lines + [line]
                current_start = max(1, i - len(overlap_lines))
                chunk_chars = sum(len(ln) for ln in current_chunk)
            else:
                current_chunk.append(line)
                chunk_chars += len(line)

        if current_chunk:
            chunks.append({
                "content": "".join(current_chunk),
                "file": file_path,
                "start_line": current_start,
                "end_line": len(lines),
            })
        return chunks

    # For other files: fixed-size character chunking with overlap
    text = content
    pos = 0
    line_num = 1
    while pos < len(text):
        end = min(pos + _CHUNK_SIZE, len(text))
        chunk_text = text[pos:end]
        # Count newlines for rough line number tracking
        start_line = line_num
        line_num += chunk_text.count("\n")
        chunks.append({
            "content": chunk_text,
            "file": file_path,
            "start_line": start_line,
            "end_line": start_line + chunk_text.count("\n"),
        })
        pos += _CHUNK_SIZE - _CHUNK_OVERLAP
        if pos >= len(text):
            break

    return chunks


class CodebaseIndex:
    """ChromaDB-backed index for a code repository."""

    def __init__(self, project_path: str):
        self.project_path = str(Path(project_path).resolve())
        self._collection_name = _collection_name(self.project_path)
        self._col = None

    def _get_collection(self):
        if self._col is not None:
            return self._col
        try:
            import chromadb
            client = chromadb.PersistentClient(path=_CHROMA_DIR)
            self._col = client.get_or_create_collection(self._collection_name)
        except Exception:
            self._col = None
        return self._col

    def is_indexed(self) -> bool:
        col = self._get_collection()
        if col is None:
            return False
        return col.count() > 0

    def index(self, force: bool = False) -> int:
        """Index the project. Returns number of chunks stored.
        Skips if already indexed unless force=True."""
        col = self._get_collection()
        if col is None:
            return 0
        if self.is_indexed() and not force:
            return col.count()

        if force:
            try:
                import chromadb
                client = chromadb.PersistentClient(path=_CHROMA_DIR)
                client.delete_collection(self._collection_name)
                self._col = client.get_or_create_collection(self._collection_name)
                col = self._col
            except Exception:
                pass

        root = Path(self.project_path)
        all_docs = []
        all_ids = []
        all_meta = []

        for fpath, rel_path in _iter_files(root):
            try:
                content = fpath.read_text(errors="replace")
            except Exception:
                continue
            if not content.strip():
                continue

            chunks = _chunk_file(content, rel_path)
            for i, chunk in enumerate(chunks):
                chunk_id = hashlib.md5(f"{rel_path}:{i}".encode()).hexdigest()
                all_docs.append(chunk["content"])
                all_ids.append(chunk_id)
                all_meta.append({
                    "file": chunk["file"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "project": self.project_path,
                })

        if not all_docs:
            return 0

        # Batch upsert (ChromaDB has a batch size limit)
        batch_size = 100
        for i in range(0, len(all_docs), batch_size):
            try:
                col.upsert(
                    documents=all_docs[i:i+batch_size],
                    ids=all_ids[i:i+batch_size],
                    metadatas=all_meta[i:i+batch_size],
                )
            except Exception:
                pass

        return col.count()

    def query(self, question: str, k: int = 6) -> str:
        """Semantic search over indexed codebase. Returns formatted context string."""
        col = self._get_collection()
        if col is None:
            return ""
        count = col.count()
        if count == 0:
            return ""
        try:
            results = col.query(
                query_texts=[question],
                n_results=min(k, count),
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return ""

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            return ""

        parts = []
        for doc, meta, dist in zip(docs, metas, distances, strict=False):
            if dist > 1.5:  # very distant → skip
                continue
            file_ref = f"{meta.get('file', '?')} (lines {meta.get('start_line', '?')}-{meta.get('end_line', '?')})"
            parts.append(f"### {file_ref}\n```\n{doc.strip()}\n```")

        if not parts:
            return ""

        return "Relevant code from indexed project:\n\n" + "\n\n".join(parts)

    def stats(self) -> dict:
        col = self._get_collection()
        if col is None:
            return {"chunks": 0, "indexed": False}
        return {"chunks": col.count(), "indexed": col.count() > 0, "project": self.project_path}
