"""Fetch + extract readable text from a web URL using httpx + lxml (no extra deps)."""
from __future__ import annotations

import re
from typing import Any

import httpx
from lxml import html

TIMEOUT = 60.0
MAX_BYTES = 2_000_000  # refuse downloads larger than ~2MB of response body
MAX_TEXT = 12_000      # chars of extracted text we return
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_IGNORE_TAGS = {"script", "style", "noscript", "svg", "iframe", "nav", "footer", "aside", "header", "form", "button", "canvas"}
_PARENT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "article", "section", "main"}

# 语义容器优先选择：XPath，命中即取（内容通常集中在这些标签里）
_CONTENT_SELECTORS = [
    "//article",
    "//main",
    "//*[@role='main']",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' article ')]",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' post-content ')]",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' entry-content ')]",
    "//*[contains(concat(' ', normalize-space(@class), ' '), ' content ')]",
]

_HREF_RE = re.compile(r"href\s*=\s*[\"']?([^\"' >]+)", re.I)


class FetchError(RuntimeError):
    pass


def _system_proxies() -> str | None:
    """Read Windows Internet Settings proxy so httpx can reach the internet on hosts
    that route outbound traffic through a corporate proxy. Returns a proxy URL string."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
        if enabled and server:
            return f"http://{server}"
    except Exception:
        pass
    return None


def _is_local_host(url: str) -> bool:
    """Bypass proxy for local / intra-network hosts (matches common NO_PROXY)."""
    import urllib.parse
    host = urllib.parse.urlparse(url).netloc
    return (
        host in ("localhost", "127.0.0.1", "::1")
        or host.endswith((".local", ".inhuawei.com", ".yinwang.com"))
    )


def fetch_text(url: str) -> dict[str, Any]:
    """Fetch a URL and return {url, title, text, source}."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url if "://" not in url else url
    proxy = None if _is_local_host(url) else _system_proxies()
    try:
        with httpx.Client(timeout=httpx.Timeout(TIMEOUT), verify=False, follow_redirects=True, headers={"User-Agent": USER_AGENT}, proxy=proxy) as client:
            resp = client.get(url)
            resp.raise_for_status()
            if len(resp.content) > MAX_BYTES:
                raise FetchError(f"页面过大（>{MAX_BYTES//1024//1024}MB），已拒绝下载")
            ctype = resp.headers.get("content-type", "") or ""
            if "text/html" not in ctype and "html" not in ctype:
                # 非 HTML（PDF 等）——原样保留其文本化前的内容能力有限，提示
                if "application/pdf" in ctype:
                    raise FetchError("目标为 PDF，请先下载后走「本地上传/复制文本」抽取")
                text = resp.text[:MAX_TEXT]
                return {"url": str(resp.url), "title": _guess_title(text), "text": text, "source": "raw"}
    except httpx.HTTPStatusError as exc:
        raise FetchError(f"HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout)):
            raise FetchError(
                f"目标网页响应超时（>{int(TIMEOUT)} 秒），可能站点较慢或网络受限，请稍后再试或换一个 URL"
            ) from exc
        raise FetchError(f"网络请求失败: {exc}") from exc

    return extract_html(resp.text, final_url=str(resp.url))


def extract_html(raw: str, final_url: str = "") -> dict[str, Any]:
    """Parse HTML and pull out title + main text (semantic tag first, density fallback)."""
    doc = html.fromstring(raw)
    _remove_nodes(doc, _IGNORE_TAGS)

    title = _extract_title(doc, final_url)

    # 1) 语义容器优先
    best = _pick_semantic(doc)
    # 2) 回退：按文本密度选主区域
    if best is None:
        best = _density_fallback(doc)

    text = "".join(best.itertext()) if best is not None else ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
    return {"url": final_url, "title": title, "text": text, "source": "html"}


def _remove_nodes(doc, tags: set[str]) -> None:
    for t in tags:
        for node in doc.xpath(f"//{t}"):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)


def _extract_title(doc, fallback: str = "") -> str:
    for sel in [".//title", "//meta[@property='og:title']", "//h1", "//h2"]:
        try:
            nodes = doc.xpath(sel)
            if nodes:
                v = (nodes[0].text_content() or "").strip()
                if v:
                    return re.sub(r"\s+", " ", v)
        except Exception:
            continue
    return fallback


def _pick_semantic(doc):
    for sel in _CONTENT_SELECTORS:
        nodes = doc.xpath(sel)
        if nodes:
            cand = max(nodes, key=lambda n: len(n.text_content() or ""), default=None)
            if cand is not None and len((cand.text_content() or "").strip()) > 200:
                return cand
    return None


def _density_fallback(doc):
    """Choose the region with the most text among top-level content blocks."""
    best = None
    best_len = 0
    for el in doc.body.iter() if doc.body is not None else []:
        tag = el.tag
        if not isinstance(tag, str):  # lxml: comment / PI 的 tag 是 callable，跳过
            continue
        tag = tag.lower()
        if tag in _PARENT_TAGS:
            txt = (el.text_content() or "").strip()
            if len(txt) > best_len:
                best_len = len(txt)
                best = el
    return best


def _guess_title(text: str) -> str:
    m = _HREF_RE.search(text)
    return ""
