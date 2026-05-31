from pathlib import Path

_CHROMA_DIR = str(Path(__file__).parent.parent / "chroma")
_chroma_client = None
_chroma_collection = None

def _get_chroma():
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    try:
        import chromadb
        _chroma_client = chromadb.PersistentClient(path=_CHROMA_DIR)
        _chroma_collection = _chroma_client.get_or_create_collection("agent_memory")
    except Exception:
        _chroma_collection = None
    return _chroma_collection

def _embed_memory(task: str, result: str, agents: list[str], timestamp: str):
    col = _get_chroma()
    if col is None:
        return
    try:
        doc = f"Task: {task}\nAgents: {', '.join(agents)}\nResult: {result[:600]}"
        col.add(documents=[doc], ids=[timestamp],
                metadatas=[{"task": task, "agents": ", ".join(agents), "timestamp": timestamp}])
    except Exception:
        pass

def _relevant_memory(task: str, k: int = 5) -> str:
    col = _get_chroma()
    if col is None:
        return ""
    try:
        count = col.count()
        if count == 0:
            return ""
        results = col.query(query_texts=[task], n_results=min(k, count))
        docs = results.get("documents", [[]])[0]
        if not docs:
            return ""
        return "Semantically relevant past tasks:\n" + "\n---\n".join(docs[:k])
    except Exception:
        return ""


def _within_ttl(timestamp: str, ttl_hours: float) -> bool:
    """True if an ISO timestamp is within ttl_hours of now. ttl_hours<=0 disables the check."""
    if ttl_hours <= 0:
        return True
    if not timestamp:
        return False
    try:
        from datetime import datetime
        ts = datetime.fromisoformat(timestamp)
        age_hours = (datetime.now() - ts).total_seconds() / 3600.0
        return age_hours <= ttl_hours
    except Exception:
        return False


def _cache_lookup(task: str, max_distance: float = 0.15, ttl_hours: float | None = None) -> str | None:
    """Check if a near-identical task was run recently. Returns cached result or None.
    ChromaDB distances: 0.0 = identical, lower = more similar.
    Default threshold 0.15 ≈ cosine similarity 0.92.
    A cached hit is only returned if its timestamp is within ttl_hours
    (defaults to limits.cache_ttl_hours from config)."""
    col = _get_chroma()
    if col is None:
        return None
    if ttl_hours is None:
        try:
            from helpers.config import cfg
            ttl_hours = float(cfg.get("limits", "cache_ttl_hours", 24))
        except Exception:
            ttl_hours = 24
    try:
        count = col.count()
        if count == 0:
            return None
        results = col.query(
            query_texts=[task],
            n_results=1,
            include=["documents", "distances", "metadatas"],
        )
        distances = results.get("distances", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        if distances and distances[0] <= max_distance and docs:
            meta = metas[0] if metas else {}
            ts = (meta or {}).get("timestamp", "")
            if _within_ttl(ts, ttl_hours):
                return docs[0]
    except Exception:
        pass
    return None


def clear_cache() -> int:
    """Delete all stored memory/cache entries. Returns count removed (best-effort)."""
    col = _get_chroma()
    if col is None:
        return 0
    try:
        count = col.count()
        if count == 0:
            return 0
        got = col.get()
        ids = got.get("ids", [])
        if ids:
            col.delete(ids=ids)
        return len(ids)
    except Exception:
        return 0
