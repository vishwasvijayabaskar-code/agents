def _search(query: str) -> str:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        return "\n\n".join([f"**{r['title']}**\n{r['body']}" for r in results])
    except Exception as e:
        return f"[Search unavailable: {e}]"
