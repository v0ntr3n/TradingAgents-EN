"""Use the Q&A bot tool: Read the user manual by chapter name.

Allows using Q&A Assistant to"Check"Specific chapter content of the user manual to avoid cramming all 139KB into system prompt words.
Slice by secondary title and return by fuzzy matching of chapter name.

Jingdong cloud version (JDYUN_MODE=true) It will automatically switch to jdyun-user-manual-v3.0.md,
The content is specifically for JD Cloud Edition users (deployment, speed limit, volume name issues, etc.).
"""

import logging
import os
import re
from typing import Annotated, List, Tuple

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _is_jdyun_mode() -> bool:
    """判断是否为京东云模式"""
    return os.environ.get("JDYUN_MODE", "false").lower() == "true"


def _resolve_manual_path() -> str:
    """Locate the current user manual that should be used.

    Jingdong cloud version (JDYUN_MODE=true) → priority use jdyun-user-manual-v3.0.md
    Standard Edition → priority use user-manual-v3.0.md
    When the corresponding version cannot be found, fall back to the standard version to avoid the manual becoming completely unusable.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # core/tools/implementations/assistant_ops/manual_reader.py -> Project root directory
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))
    user_guide_dir = os.path.join(project_root, "docs", "02-user-guide")

    if _is_jdyun_mode():
        # JD Cloud version searches jdyun-user-manual-v3.0.md first and returns to the main manual.
        candidates = [
            os.path.join(user_guide_dir, "jdyun-user-manual-v3.0.md"),
            os.path.join(user_guide_dir, "user-manual-v3.0.md"),
            os.path.join(user_guide_dir, "user-manual.md"),
        ]
    else:
        candidates = [
            os.path.join(user_guide_dir, "user-manual-v3.0.md"),
            os.path.join(user_guide_dir, "user-manual.md"),
            os.path.join(user_guide_dir, "jdyun-user-manual-v3.0.md"),
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def _resolve_all_manual_paths() -> List[Tuple[str, str]]:
    """Lists all available user manuals (in order of priority) for multi-manual searches.

    Return [(manual path, Manual type), ...]
    Manual type: "jdyun" | "standard"
    For the JD Cloud version, put the JD Cloud manual first, and for the standard version, put the main manual first.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))
    user_guide_dir = os.path.join(project_root, "docs", "02-user-guide")

    standard_path = os.path.join(user_guide_dir, "user-manual-v3.0.md")
    jdyun_path = os.path.join(user_guide_dir, "jdyun-user-manual-v3.0.md")

    manuals = []
    if _is_jdyun_mode():
        if os.path.exists(jdyun_path):
            manuals.append((jdyun_path, "jdyun"))
        if os.path.exists(standard_path):
            manuals.append((standard_path, "standard"))
    else:
        if os.path.exists(standard_path):
            manuals.append((standard_path, "standard"))
        if os.path.exists(jdyun_path):
            manuals.append((jdyun_path, "jdyun"))
    return manuals


def _split_sections(content: str) -> List[Tuple[str, str, int]]:
    """Slice by markdown header.

    Return [(title, body, level), ...]
    level Yes # quantity (1-4)
    """
    sections: List[Tuple[str, str, int]] = []
    # Matches 1-4 at the beginning of the line # followed by space and title
    parts = re.split(r'\n(?=#{1,4}\s+[^\n]+)', content)
    for part in parts:
        match = re.match(r'^(#{1,4})\s+([^\n]+)\n(.*)', part, re.DOTALL)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            body = match.group(3).strip()
            sections.append((title, body, level))
    return sections


def _truncate_to_next_level(body: str, current_level: int) -> str:
    """Cut to the next sibling or higher heading"""
    pattern = re.compile(rf'\n#{{1,{current_level}}}\s+')
    match = pattern.search(body)
    if match:
        return body[:match.start()].strip()
    return body.strip()


def _extract_keyword_fragments(keyword: str, min_len: int = 2) -> List[str]:
    """Extract all contiguous subsegments from the keyword that can be used for fuzzy matching.

    solve"Single container data loss"Unable to match"Q5: Data is lost after a single container is restarted"problem.
    Extract all lengths >= min_len Continuous substrings of , arranged in reverse order of length (long segments are matched first).

    Example:
        "Single container data loss" → ["single container", "data", "lost", "Container data", "data lost", ...]
        "data loss" → ["data", "lost", "data lost"]
    """
    if not keyword or len(keyword) < min_len:
        return []
    fragments = set()
    n = len(keyword)
    for length in range(min_len, n + 1):
        for i in range(n - length + 1):
            frag = keyword[i:i + length]
            if len(frag) >= min_len:
                fragments.add(frag)
    # Sort by length in descending order (longer fragments preferred, more accurate)
    return sorted(fragments, key=len, reverse=True)


def _extract_two_char_fragments(keyword: str) -> List[str]:
    """Extract all 2-word consecutive fragments in the keyword (duplication removed, in order of appearance).

    used for"Most hits"Fuzzy match: A match is considered as long as 60% of the fragments are included in the title.
    solve"Single container data loss" vs "Q5: Data is lost after a single container is restarted" This type of long sentence reorganization problem.

    Example:
        "Single container data loss" → ["single container", "Number of containers", "lost", "lost"]  (Actually"single container","container","According to","lost"Wait)
        Actually take a fixed 2-word window:"Single capacity","container","data","lost"
    """
    if not keyword or len(keyword) < 2:
        return []
    frags = []
    seen = set()
    for i in range(len(keyword) - 1):
        frag = keyword[i:i + 2]
        if frag not in seen:
            seen.add(frag)
            frags.append(frag)
    return frags


@tool
@register_tool(
    tool_id="read_user_manual_section",
    name="读取用户手册章节",
    description="Read the contents of the user manual by chapter name. Support fuzzy matching, such as input'Installation'Can match'Installation and deployment'chapter. When the user asks'How to configure Token''How to activate simulated trading''How to add discretionary stocks''429 What to do about speed limit''Single container data loss'Used when there are operational process issues. JD Cloud Edition users will automatically read the JD Cloud Edition special manual (including answers to JD Cloud-specific questions such as deployment, speed limits, data volumes, etc.).",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "manual", "documentation", "user_guide", "operation_flow", "jdyun_manual"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["怎么配置 Token", "模拟交易怎么开通", "怎么加自选股", "License 怎么激活", "429 限速", "单容器数据丢失", "操作流程", "京东云部署"],
    when_to_use="When users ask about specific operating procedures, function configuration steps, or how to use the system, they should give priority to calling this tool to check the documentation instead of answering from memory.",
    returns="Returns the user manual chapter content in text format. If there is no match, return the list of optional chapters.",
)
async def read_user_manual_section(
    section_name: Annotated[str, "Chapter name or keyword, such as'Installation and deployment', 'Data source configuration', 'simulated trading', 'License', 'timing analysis', 'Stock Watchlist', '429 speed limit', 'Single container data loss'"],
) -> str:
    """Read the contents of the user manual by chapter name."""
    manual_paths = _resolve_all_manual_paths()
    if not manual_paths:
        return "❌ User manual file does not exist. Please check if there is user-manual-v3.0.md file in the docs/02-user-guide/ directory."

    keyword = (section_name or "").strip().lower()
    is_jdyun = _is_jdyun_mode()
    current_manual_label = "京东云版专用手册" if is_jdyun else "标准版主手册"

    # 1) List of chapter overviews for all manuals
    if not keyword:
        # Collect all manual chapters
        overview_lines = [f"📖 当前模式: {current_manual_label}", ""]
        for path, manual_type in manual_paths:
            label = "京东云版专用手册" if manual_type == "jdyun" else "标准版主手册"
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                sections = _split_sections(content)
                if not sections:
                    continue
                overview_lines.append(f"━━━ {label} ({os.path.basename(path)}) ━━━")
                for title, body, level in sections:
                    if level <= 2:  # List only first- and second-level headings
                        prefix = "  " * (level - 1) + "-"
                        overview_lines.append(f"{prefix} {title}")
                overview_lines.append("")
            except Exception as exc:
                logger.warning("[read_user_manual_section] Overview read failed %s: %s", path, exc)
        overview_lines.append("💡 Please provide specific chapter names or keywords (such as 'Installation and deployment', '429 speed limit', 'Single container data loss') ")
        return "\n".join(overview_lines)

    # 2) Keyword search: Search JD Cloud version first(if exists), Search the standard version again, merge and remove duplicates
    all_matches = []  # [(Manual type, Manual name, title, body, level)]
    primary_label = manual_paths[0][1] if manual_paths else "standard"
    seen_titles = set()  # Used to remove duplicates

    for path, manual_type in manual_paths:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            sections = _split_sections(content)
        except Exception as exc:
            logger.warning("[read_user_manual_section] Failed to read manual %s: %s", path, exc)
            continue

        # Primary match: The title contains exactly the keyword
        primary_hits = 0
        for title, body, level in sections:
            if keyword in title.lower():
                dedup_key = f"{manual_type}:{title}"
                if dedup_key not in seen_titles:
                    seen_titles.add(dedup_key)
                    all_matches.append((manual_type, path, title, body, level))
                    primary_hits += 1

        # Fuzzy matching: only tried if there is no main matching result in the current manual (to avoid polluting the main match)
        if primary_hits == 0:
            # Option 1: Use the longest 2-word fragment of the keyword(Take the first 2-3)do"Most hits"judge
            # solve"Single container data loss"No match found"Q5: Data is lost after a single container is restarted"question
            # Both share fragments: "single container" / "data" / "lost" - 3 2-word fragments
            two_char_frags = _extract_two_char_fragments(keyword)
            if two_char_frags:
                # A match must hit at least 60% of 2-word fragments
                threshold = max(1, int(len(two_char_frags) * 0.6))
                for title, body, level in sections:
                    title_lower = title.lower()
                    hit_count = sum(1 for f in two_char_frags if f in title_lower)
                    if hit_count >= threshold:
                        dedup_key = f"{manual_type}:{title}"
                        if dedup_key not in seen_titles:
                            seen_titles.add(dedup_key)
                            all_matches.append((manual_type, path, title, body, level))

    # If the main match has no results, try splitting the match by word
    if not all_matches:
        keywords = [k for k in keyword.split() if len(k) >= 2]
        if keywords:
            for path, manual_type in manual_paths:
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                    sections = _split_sections(content)
                except Exception:
                    continue
                for title, body, level in sections:
                    if any(k in title.lower() for k in keywords):
                        dedup_key = f"{manual_type}:{title}"
                        if dedup_key not in seen_titles:
                            seen_titles.add(dedup_key)
                            all_matches.append((manual_type, path, title, body, level))

    if not all_matches:
        # Collect the first and second level titles of all manuals as an optional list
        all_titles = []
        for path, manual_type in manual_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                sections = _split_sections(content)
                label = "京东云版" if manual_type == "jdyun" else "标准版"
                for title, _, level in sections:
                    if level <= 2 and (label, title) not in all_titles:
                        all_titles.append((label, title))
            except Exception:
                continue
        titles_text = "\n".join(f"  - [{label}] {t}" for label, t in all_titles[:40])
        return f"❌ 未找到章节 '{section_name}'。\n\n📖 可选章节:\n{titles_text}"

    # 3) Splice matching results and control the total length
    parts = []
    total_len = 0
    max_len = 6000  # Truncate to prevent overlength
    matches_to_show = all_matches[:3]  # Returns up to 3 matching chapters

    for manual_type, path, title, body, level in matches_to_show:
        truncated = _truncate_to_next_level(body, level)
        prefix = "#" * level
        manual_label = "📕 京东云版" if manual_type == "jdyun" else "📘 标准版"
        section_text = f"{manual_label} | {prefix} {title}\n\n{truncated}"
        if total_len + len(section_text) > max_len:
            remaining = max_len - total_len
            if remaining > 200:
                section_text = section_text[:remaining] + "\n\n...(The content has been truncated. If you need the complete content, please provide a more precise chapter name.)"
                parts.append(section_text)
                total_len = max_len
            break
        parts.append(section_text)
        total_len += len(section_text)

    header = f"📖 用户手册搜索结果（keyword='{section_name}', 当前模式: {current_manual_label}）:\n\n"
    return header + "\n\n---\n\n".join(parts)


# ============================================================
# Vector retrieval tool: Based on semantic matching, it solves the problem that natural language problems cannot match chapters.
# ============================================================


@tool
@register_tool(
    tool_id="search_user_manual",
    name="语义搜索用户手册",
    description=(
        "Retrieve user manuals based on vector semantics and find relevant chapters in natural language."
        "When a user asks a question in natural language (e.g.'How to do analysis''How to research a stock''How to use position analysis''How to configure Token') When using this tool,"
        "It returns the top-5 semantically most relevant chapters."
        "This tool is more suitable for handling users natural language questions than read_user_manual_section."
        "It is recommended to use this tool to search first, and then use read_user_manual_section to read the complete content according to the precise chapter name."
    ),
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "manual", "vector_search", "semantic_search", "user_guide"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "怎么做分析", "怎么研究股票", "如何分析一只股票", "单股分析怎么用",
        "分析在哪", "怎么发起分析", "研究流程", "怎么用平台做分析",
        "持仓分析", "选股助手怎么用", "怎么配置 Token", "怎么加自选",
    ],
    when_to_use=(
        "This tool is used first when users use natural language to ask about system usage, functional processes, and operating steps."
        "This tool is based on vector semantic matching and can understand'How to do analysis'Wait for natural language questions and recall relevant chapters."
    ),
    returns="Returns the titles and content fragments of the Top-5 relevant chapters, sorted in descending order of similarity.",
)
async def search_user_manual(
    query: Annotated[
        str,
        "User s natural language questions such as'How to do analysis''How to research a stock''How to use position analysis''How to configure Token''429 What to do about speed limit'",
    ],
) -> str:
    """Retrieve user manuals based on vector semantics and find relevant chapters in natural language."""
    try:
        from core.knowledge.user_manual_manager import UserManualManager

        manager = UserManualManager()

        # Check if the vector library is available; try to reinitialize if not
        #  (The user may have configured the Embedding Key, reinit will re-read the configuration without restarting the backend)
        if not manager.available:
            try:
                if manager.reinit() and manager.available:
                    logger.info("[search_user_manual] Vector retrieval is reinitialized successfully and semantic retrieval continues.")
                else:
                    raise RuntimeError("reinit 失败")
            except Exception as e:
                # Graceful degradation: fallback to read_user_manual_section keyword matching
                logger.warning(
                    "[search_user_manual] Vector search is not available (%s), fallback to keyword matching."
                    "It is recommended to check the Embedding configuration (system settings -> LLM/Embedding) Or restart the backend.",
                    e,
                )
                return (
                    "⚠️ Vector retrieval is currently unavailable (Embedding or vector database is not ready) and has fallen back to keyword matching mode.\n\n"
                    "Please try calling the read_user_manual_section tool with a more precise section name,"
                    "Such as 'single stock research', 'Data source configuration', 'simulated trading' wait."
                )

        # Check if the index has been built
        count = manager.get_count()
        if count == 0:
            logger.warning("[search_user_manual] Manual index is empty, try to trigger a rebuild")
            # Trigger a rebuild synchronously (do not block for too long, or downgrade if failed)
            try:
                manager.ensure_indexed(force=False)
            except Exception as e:
                logger.error(f"[search_user_manual] Trigger rebuild failed: {e}")

            count = manager.get_count()
            if count == 0:
                return (
                    "⚠️ The user manual index has not been built yet, and vector search is not available yet.\n"
                    "You can instead use the read_user_manual_section tool to read accurately by chapter name."
                )

        # Perform semantic searches
        results = manager.search(query, top_k=5)

        if not results:
            return (
                f"❌ 未找到与 '{query}' 语义相关的手册章节。\n"
                "Try calling the read_user_manual_section tool with more specific keywords."
            )

        # Formatted output
        import os
        is_jdyun = _is_jdyun_mode()
        current_label = "京东云版专用手册" if is_jdyun else "标准版主手册"

        lines = [
            f"📖 用户手册语义检索结果（query='{query}', 当前模式: {current_label}）",
            f"找到 {len(results)} 个相关章节（按相似度降序）：",
            "",
        ]

        for i, r in enumerate(results, 1):
            manual_label = "📕 京东云版" if r.manual_type == "jdyun" else "📘 标准版"
            sim_pct = f"{r.similarity * 100:.0f}%"
            parent_hint = f" (Belongs to:{r.parent_title}) " if r.parent_title else ""

            # Control the length of individual results to avoid the total output being too long
            content_display = r.content
            if len(content_display) > 800:
                content_display = content_display[:800] + "\n...(The content has been truncated. If you need the complete content, please use read_user_manual_section to read by title.)"

            lines.append(f"━━━ #{i} {manual_label} | 相似度 {sim_pct} ━━━")
            lines.append(f"📌 标题: {r.title}{parent_hint}")
            lines.append(f"📄 内容:")
            lines.append(content_display)
            lines.append("")

        lines.append(
            "💡 If you want to view the complete content of a section, you can use the read_user_manual_section tool to read it exactly by the above title."
        )

        return "\n".join(lines)

    except ImportError:
        logger.error("[search_user_manual] UserManualManager Module not found")
        return "❌ The vector retrieval module is not installed. Please use the read_user_manual_section tool instead."
    except Exception as e:
        logger.error(f"[search_user_manual] Retrieval exception: {e}", exc_info=True)
        return f"❌ 检索失败: {e}\n请改用 read_user_manual_section 工具按章节名精确读取。"

