import re
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse


def _search(query: str, max_results: int = 5) -> list[dict]:
    """Returns list of {title, body, url} dicts."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as e:
        return []


def _format_search_results(results: list[dict]) -> str:
    if not results:
        return "[Search unavailable]"
    return "\n\n".join([f"**{r['title']}**\n{r.get('body', '')}\n{r.get('href', '')}" for r in results])


def _strip_html(html: str) -> str:
    """Basic HTML → text. No deps."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>',  '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>',       '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _robots_allowed(url: str) -> bool:
    """Check robots.txt. Permissive on error."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch("*", url)
    except Exception:
        return True  # assume allowed on error


def _fetch_page(url: str, max_chars: int = 5000) -> str:
    """Fetch URL, return cleaned text. Respects robots.txt, 10s timeout."""
    try:
        if not _robots_allowed(url):
            return f"[{url}: blocked by robots.txt]"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; agents-bot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Only process HTML
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype:
                return f"[{url}: skipped non-HTML content ({ctype})]"
            html = resp.read(200_000).decode("utf-8", errors="replace")
        text = _strip_html(html)
        return text[:max_chars]
    except Exception as e:
        return f"[Could not fetch {url}: {e}]"
