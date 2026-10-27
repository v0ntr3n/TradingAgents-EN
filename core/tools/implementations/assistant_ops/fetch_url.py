"""Web Content Scraping Tool - Get the complete body content of a web page."""

import logging
import random
from typing import Annotated
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
MAX_CONTENT_LENGTH = 8000

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Tags that need to be removed (navigation, advertising, etc. noise)
REMOVE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "iframe", "noscript", "form", "button", "input", "select",
    "svg", "img", "video", "audio",
]

# Noisy text features (navigation menus, copyright notices, etc.)
NOISE_PATTERNS = [
    "首页", "登录", "注册", "VIP邮箱", "免费下载", "客户端下载",
    "快速导航", "网易首页", "应用", "安全退出", "移动端",
    " COPYRIGHT ", "@版权", "举报", "分享至", "微信扫码",
    "申请入驻", "客户端", "关注我们", "返回首页", "网站地图",
]


def _resolve_baidu_link(url: str) -> str:
    """If it is a Baidu jump link, parse out the real URL."""
    if "baidu.com/link" not in url and "baidu.php" not in url:
        return url
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        if resp.url and resp.url != url:
            return resp.url
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"http-equiv": "refresh"})
        if meta:
            content = meta.get("content", "")
            if "url=" in content.lower():
                real_url = content.split("url=", 1)[-1].strip()
                if real_url.startswith("http"):
                    return real_url
    except Exception as exc:
        logger.warning("Failed to parse Baidu jump link: %s", exc)
    return url


def _is_noise(text: str) -> bool:
    """Determine whether the text is noise such as navigation menu."""
    if not text or len(text) < 10:
        return True
    # If the text is too short, it is most likely a navigation link
    if len(text) < 15 and any(kw in text for kw in ["登录", "注册", "首页", "退出", "关注", "分享"]):
        return True
    # If it contains too many noisy keywords
    noise_count = sum(1 for pattern in NOISE_PATTERNS if pattern in text)
    if noise_count >= 3:
        return True
    return False


def _extract_main_content(soup: BeautifulSoup) -> str:
    """Extract body content from BeautifulSoup, giving priority to the body container."""
    # priority 1: explicit body container
    for selector in [
        ("article", None),
        ("div", "post_body"),  # Baidu Baijiahao
        ("div", "article-content"),  # General articles
        ("div", "post_content"),  # Blog category
        ("div", "main-content"),  # Universal
        ("div", "content"),  # Universal
        ("div", "article_content"),  # NetEase
        ("div", "text"),  # Universal
        ("div", "detail"),  # Details page
        ("div", "post_body"),
        ("div", "art_content"),
        ("div", "article-body"),
        ("div", "news_content"),
        ("div", "TRS_Editor"),
        ("main", None),
    ]:
        tag, cls = selector
        if cls:
            el = soup.find(tag, class_=cls)
        else:
            el = soup.find(tag)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text

    # priority 2: body the longest within div
    body = soup.find("body")
    if not body:
        return ""

    best_text = ""
    best_len = 0
    for div in body.find_all("div"):
        text = div.get_text(separator="\n", strip=True)
        # filter noise
        if _is_noise(text):
            continue
        if len(text) > best_len:
            best_text = text
            best_len = len(text)

    return best_text


def _clean_content(text: str) -> str:
    """Clean up body text, removing redundant blank lines and noise."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _is_noise(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _fetch_page(url: str) -> str:
    """Crawl web content and extract body text."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    resp = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove unnecessary tags
    for tag in soup(REMOVE_TAGS):
        tag.decompose()

    # Extract title
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    # Extract text
    content = _extract_main_content(soup)
    content = _clean_content(content)

    if not content or len(content) < 50:
        return f"Title:{title}\n Links:{url}\n\n Unable to extract body content (page may require JavaScript rendering)."

    # Limit return length
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n\n[The content has been truncated, please visit the original webpage for the complete content]"

    return f"Title:{title}\n Links:{url}\n\n{content}"


def run_fetch_url(url: str) -> str:
    """Crawl web content."""
    if not url or not url.strip():
        return "Please provide a link to the web page you want to crawl."

    url = url.strip()

    # If it is a Baidu jump link, first parse the real URL
    if "baidu.com/link" in url or "baidu.php" in url:
        logger.info("解析百度跳转链接: %s", url[:80])
        real_url = _resolve_baidu_link(url)
        if real_url != url:
            logger.info("真实URL: %s", real_url[:80])
            url = real_url

    # Check if it is a Baidu verification page
    if "wappass.baidu.com" in url or "captcha" in url:
        return f"The link jumps to the Baidu security verification page and the content cannot be crawled. Please try other search results."

    try:
        logger.info("抓取网页: %s", url[:80])
        return _fetch_page(url)
    except requests.exceptions.Timeout:
        return f"Fetch timeout:{url}"
    except requests.exceptions.ConnectionError as exc:
        return f"Connection failed:{url}\n Error:{exc}"
    except Exception as exc:
        return f"Fetch failed:{url}\n Error:{exc}"


@tool
@register_tool(
    tool_id="fetch_url",
    name="网页内容抓取",
    description="Fetch the complete text content of the specified web page. Use this tool to crawl the full page linked to the search results when the summary information returned by web_search is not detailed enough. Supports parsing Baidu jump links to obtain real URLs. Automatically extract text content and filter out noise such as navigation menus and advertisements.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    data_source_handling="local_only",
    capability_tags=[
        "web_fetch", "content_extraction", "url_read",
        "page_scrape", "information_retrieval", "real_time_info",
    ],
    tool_role_hint="specialized",
    output_shape="report",
    preferred_for=[
        "Get the complete web content of the search results",
        "读取新闻文章原文",
        "查看公告或报告的详细内容",
        "补充搜索摘要中缺失的细节",
    ],
    when_to_use="Used when the summary information of web_search search results is not enough and the complete web page content needs to be obtained.",
    returns="Return the webpage title and body text (up to 8000 characters), and automatically remove irrelevant content such as navigation and advertisements.",
)
def fetch_url(
    url: Annotated[str, "The web link to be crawled can be a direct URL or a jump link from Baidu search results."],
) -> str:
    """Crawl the complete text content of the web page."""
    return run_fetch_url(url)
