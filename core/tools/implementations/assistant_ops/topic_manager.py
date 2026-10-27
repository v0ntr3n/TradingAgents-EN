"""
Smart assistant theme management tool

Allow AI to directly create research topics, create subtopics, view topic trees, and delete topic trees.
The user identity and current topic context are obtained through core.tools.context.
"""

import logging
from typing import Annotated, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, get_current_im_channel, require_current_user_id, set_current_assistant_thread_id

logger = logging.getLogger(__name__)


async def _load_threads(db, user_id: str) -> List[dict]:
    cursor = db.assistant_threads.find({
        "user_id": user_id,
        "archived": {"$ne": True},
    }).sort([("pinned", -1), ("updated_at", -1)])
    docs = await cursor.to_list(length=None)
    return [
        doc for doc in docs
        if (doc.get("topic_type") or "") != "im_session" and not _is_gateway_session_thread_id(doc.get("thread_id"))
    ]


def _is_gateway_session_thread_id(thread_id: Optional[str]) -> bool:
    return bool(thread_id and ":" in thread_id)


async def _get_current_im_session(db, user_id: str) -> Optional[dict]:
    im_channel = get_current_im_channel()
    if not im_channel:
        return None

    from core.gateway.session import SessionManager

    session_manager = SessionManager(db)
    return await session_manager.get_or_create(
        user_id,
        im_channel.get("channel_type") or "",
        im_channel.get("channel_id") or "",
    )


async def _bind_current_topic(db, user_id: str, thread_id: Optional[str]) -> None:
    session = await _get_current_im_session(db, user_id)
    if session:
        from core.gateway.session import SessionManager

        session_manager = SessionManager(db)
        await session_manager.set_current_topic_id(session.get("session_key") or "", thread_id)

    set_current_assistant_thread_id(thread_id)


async def _get_bound_current_topic_id(db, user_id: str) -> Optional[str]:
    current_thread_id = (get_current_assistant_thread_id() or "").strip() or None
    if current_thread_id and not _is_gateway_session_thread_id(current_thread_id):
        return current_thread_id

    session = await _get_current_im_session(db, user_id)
    if not session:
        return None

    context = session.get("context") or {}
    return (context.get("current_topic_id") or "").strip() or None


async def _get_bound_current_topic_doc(db, user_id: str) -> Optional[dict]:
    current_topic_id = await _get_bound_current_topic_id(db, user_id)
    if not current_topic_id:
        return None
    return await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": current_topic_id,
        "archived": {"$ne": True},
    })


def _normalize_title(title: str) -> str:
    text = (title or "").strip().lower()
    if not text:
        return ""

    replacements = {
        "新能源汽车": "新能源车",
        "新能源汽車": "新能源车",
        "个股": "公司",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    for token in ["（", "）", "(", ")", "-", "_", " ", "　", "/", "\\", "·", "、"]:
        text = text.replace(token, "")

    removable_suffixes = [
        "研究主题",
        "产业链研究",
        "行业研究",
        "板块研究",
        "公司研究",
        "个股研究",
        "深度研究",
        "专题研究",
        "课题研究",
        "产业链",
        "行业",
        "板块",
        "研究",
        "分析",
        "跟踪",
        "专题",
        "主题",
    ]
    changed = True
    while changed and len(text) > 2:
        changed = False
        for suffix in removable_suffixes:
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[: -len(suffix)]
                changed = True
                break

    return text


def _titles_match(first: str, second: str) -> bool:
    normalized_first = _normalize_title(first)
    normalized_second = _normalize_title(second)
    if not normalized_first or not normalized_second:
        return False
    return normalized_first == normalized_second


def _find_matching_thread(docs: List[dict], title: str, parent_thread_id: Optional[str] = None) -> Optional[dict]:
    normalized_parent_id = (parent_thread_id or "").strip() or None
    candidates = [doc for doc in docs if (doc.get("parent_thread_id") or None) == normalized_parent_id]
    for doc in candidates:
        if _titles_match(doc.get("title") or "", title):
            return doc
    return None


def _format_thread_tree(docs: List[dict]) -> str:
    by_parent = {}
    by_id = {}
    for doc in docs:
        thread_id = doc.get("thread_id")
        by_id[thread_id] = doc
        by_parent.setdefault(doc.get("parent_thread_id"), []).append(doc)

    def _sort(items: List[dict]) -> List[dict]:
        return sorted(
            items,
            key=lambda item: (
                0 if item.get("pinned") else 1,
                -(item.get("updated_at").timestamp() if item.get("updated_at") else 0),
            ),
        )

    lines: List[str] = []

    def _walk(parent_id: Optional[str], depth: int = 0):
        for item in _sort(by_parent.get(parent_id, [])):
            prefix = "  " * depth + ("- " if depth else "• ")
            label = item.get("title") or "未命名主题"
            count = int(item.get("message_count") or 0)
            lines.append(f"{prefix}{label} [{item.get('thread_id')}]（{count} 条消息）")
            _walk(item.get("thread_id"), depth + 1)

    _walk(None)
    return "\n".join(lines)


async def _resolve_parent_thread_id(db, user_id: str, parent_title: Optional[str]) -> Optional[str]:
    title = (parent_title or "").strip()
    if not title:
        return await _get_bound_current_topic_id(db, user_id)

    all_docs = await _load_threads(db, user_id)
    matched = _find_matching_thread(all_docs, title, parent_thread_id=None)
    if matched:
        return matched.get("thread_id")

    docs = await db.assistant_threads.find({
        "user_id": user_id,
        "title": title,
        "archived": {"$ne": True},
    }).to_list(length=5)

    if not docs:
        raise ValueError(f"未找到标题为「{title}」的主题")
    if len(docs) > 1:
        raise ValueError(f"找到多个同名主题「{title}」，请先让我列出主题树后再指定更精确的父主题")
    return docs[0].get("thread_id")


async def _resolve_target_thread_id(db, user_id: str, title: Optional[str]) -> Optional[str]:
    normalized_title = (title or "").strip()
    if not normalized_title:
        return await _get_bound_current_topic_id(db, user_id)

    all_docs = await _load_threads(db, user_id)
    exact_or_semantic = [doc for doc in all_docs if _titles_match(doc.get("title") or "", normalized_title)]
    if len(exact_or_semantic) == 1:
        return exact_or_semantic[0].get("thread_id")
    if len(exact_or_semantic) > 1:
        raise ValueError(f"找到多个语义相近的主题「{normalized_title}」，请先让我列出主题树后再指定更精确的目标主题")

    docs = await db.assistant_threads.find({
        "user_id": user_id,
        "title": normalized_title,
        "archived": {"$ne": True},
    }).to_list(length=5)

    if not docs:
        raise ValueError(f"未找到标题为「{normalized_title}」的主题")
    if len(docs) > 1:
        raise ValueError(f"找到多个同名主题「{normalized_title}」，请先让我列出主题树后再指定更精确的目标主题")
    return docs[0].get("thread_id")


@tool
@register_tool(
    tool_id="list_assistant_topics",
    name="查看研究主题树",
    description="Lists the current user s research topic tree. Returns the topic level indentation, topic ID, and number of messages for each topic to facilitate viewing the research directory structure.",
    when_to_use="Used when the user wants to view the current research directory, topic structure, industry and company subtopic levels.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "topic_tree", "list", "query", "assistant_ops", "thread_management", "topic_hierarchy", "topic_structure", "research_directory"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_tree_viewing", "research_structure_browsing", "topic_hierarchy_query", "thread_listing", "research_directory_viewing"],
    returns="Returns the topic tree in text format, including topic level indentation, topic ID, and number of messages in each topic.",
)
async def list_assistant_topics() -> str:
    """View the current user s research topic tree."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()
    docs = await _load_threads(db, user_id)
    if not docs:
        return "📁 There are currently no research topics. You can ask me to create an industry or company theme first."
    current_topic = await _get_bound_current_topic_doc(db, user_id)
    current_topic_line = ""
    if current_topic:
        current_topic_line = f"🎯 Current external conversation topic:{current_topic.get('title') or current_topic.get('thread_id')}\n"
    return current_topic_line + "📁 Current research topic tree:\n" + _format_thread_tree(docs)


@tool
@register_tool(
    tool_id="create_assistant_topic",
    name="创建研究主题",
    description="Create new top-level research topics for industry, strategy, or independent research lines. Returns the creation result (new/reused) and topic ID.",
    when_to_use="It is used when the user explicitly states that he wants to create a new research topic, industry directory, or research main line.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "create", "assistant_ops", "thread_management", "topic_creation", "research_mainline", "new_topic"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_creation", "research_mainline_setup", "new_topic_initialization", "research_directory_creation"],
    returns="Returns a text message, including the creation result (new/reused) and topic ID.",
)
async def create_assistant_topic(
    title: Annotated[str, "Topic name to create, such as Battery Industry Tracking or Brokerage Sector Research"],
) -> str:
    """Create top-level research topics."""
    from app.core.database import get_mongo_db
    from app.services.intelligent_assistant_service import create_assistant_thread

    user_id = require_current_user_id()
    db = get_mongo_db()
    current_topic = await _get_bound_current_topic_doc(db, user_id)
    if current_topic and _titles_match(current_topic.get("title") or "", title):
        await _bind_current_topic(db, user_id, current_topic.get("thread_id"))
        return (
            f"ℹ️ Currently on the topic with the same semantics {current_topic.get('title') or title}] down,"
            f"No need to re-create.\n- Topic ID: {current_topic.get('thread_id')}"
        )

    item = await create_assistant_thread(db, user_id, title=title, parent_thread_id=None)
    await _bind_current_topic(db, user_id, item["thread_id"])
    if _titles_match(item.get("title") or "", title):
        return f"✅ Created and switched to research topic {item['title']}] \n- Topic ID: {item['thread_id']}"
    return f"ℹ️ Reused and switched to an existing theme with similar semantics {item['title']}] \n- Topic ID: {item['thread_id']}"


@tool
@register_tool(
    tool_id="create_assistant_subtopic",
    name="创建研究子主题",
    description="Create subtopics (industry company splits, company split valuations, etc.) under the current or specified parent topic. Returns the child theme creation result, parent theme and child theme ID.",
    when_to_use="When the user says Add a new subtopic under this topic ,  Add a company under an industry ,  Break out a sub-problem when used.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "create", "subtopic", "assistant_ops", "thread_management", "topic_hierarchy", "subtopic_creation", "child_topic"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["subtopic_creation", "topic_branching", "research_subdivision", "child_topic_setup"],
    returns="Returns a text message, including the child topic creation result, parent topic ID, and child topic ID.",
)
async def create_assistant_subtopic(
    title: Annotated[str, "Subtopic names, such as CATL, valuation breakdown, risk points"],
    parent_title: Annotated[Optional[str], "Optional, parent topic title; if left blank, it will default to the topic currently being discussed."] = None,
) -> str:
    """Create research subtopics."""
    from app.core.database import get_mongo_db
    from app.services.intelligent_assistant_service import create_assistant_thread

    user_id = require_current_user_id()
    db = get_mongo_db()
    try:
        parent_thread_id = await _resolve_parent_thread_id(db, user_id, parent_title)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    if not parent_thread_id:
        return "❌ There is currently no available parent theme. Please create a research topic first, or tell me explicitly which topic you want to link to."

    all_docs = await _load_threads(db, user_id)
    similar_child = _find_matching_thread(all_docs, title, parent_thread_id=parent_thread_id)
    if similar_child:
        return (
            f"ℹ️ There are already sub-topics with similar semantics under the current topic {similar_child.get('title') or title}] , "
            f"No need to re-create.\n- subtopic ID: {similar_child.get('thread_id')}"
        )

    item = await create_assistant_thread(db, user_id, title=title, parent_thread_id=parent_thread_id)
    return (
        f"✅ 已创建子主题「{item['title']}」\n"
        f"- The current session is still bound to the parent topic: {parent_thread_id}\n"
        f"- Parent topic ID: {parent_thread_id}\n"
        f"- subtopic ID: {item['thread_id']}"
    )


@tool
@register_tool(
    tool_id="get_current_assistant_topic",
    name="查看当前研究主题",
    description="View current research topics on external session binding. Return the topic name and topic ID to facilitate confirmation of the main research line to which subsequent discussions belong.",
    when_to_use="It is used when the user asks which topic they are currently talking about, what this topic is, and which research directory it is currently hanging in.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "query", "current_topic", "assistant_ops", "thread_management", "context_query", "session_context"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["current_topic_query", "session_context_check", "active_topic_verification"],
    returns="Returns a text message containing the current topic name and topic ID.",
)
async def get_current_assistant_topic() -> str:
    """View current research topics on external session binding."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()
    current_topic = await _get_bound_current_topic_doc(db, user_id)
    if not current_topic:
        return "ℹ️ The current external session does not have a research topic bound to it. You can ask me to create a topic first, or explicitly say Switch to a topic . "
    return (
        f"🎯 当前研究主题：{current_topic.get('title') or current_topic.get('thread_id')}\n"
        f"- Topic ID: {current_topic.get('thread_id')}"
    )


@tool
@register_tool(
    tool_id="switch_assistant_topic",
    name="切换当前研究主题",
    description="Bind the current session switch to an existing research topic, and subsequent discussions will be directed to this topic by default. Returns the switching result and target topic ID.",
    when_to_use="Use when the user explicitly requests to switch to a certain topic, continue with another industry or company topic, or specify that the current session should be bound to a certain line of research.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "switch", "assistant_ops", "thread_management", "topic_switching", "context_binding", "active_topic_change"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_switching", "research_mainline_change", "session_binding_update", "active_topic_selection"],
    returns="Returns a text message containing the switch result and target topic ID.",
)
async def switch_assistant_topic(
    title: Annotated[str, "The topic title to be switched to, such as new energy vehicle research, CATL, securities sector research"],
) -> str:
    """Toggles the research topic bound to the current external session."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()
    try:
        thread_id = await _resolve_target_thread_id(db, user_id, title)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    if not thread_id:
        return "❌ No switchable target theme found. Please create a topic first, or provide a more precise topic title."

    target = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": thread_id,
        "archived": {"$ne": True},
    })
    if not target:
        return "❌ The target topic does not exist or has been deleted."

    await _bind_current_topic(db, user_id, thread_id)
    return (
        f"✅ The current research topic has been switched to {target.get('title') or thread_id}] \n"
        f"- Topic ID: {thread_id}"
    )


@tool
@register_tool(
    tool_id="delete_assistant_topic",
    name="删除研究主题树",
    description="Delete a research topic and all its subtopics, messages and abstracts (default current topic or by title). Returns the deleted topic number and topic ID list.",
    when_to_use="Only used when the user explicitly requests to delete a research topic, clean up a research main line, or delete the current topic and its subtopics. Involves destructive operations and must be called after the user clearly expresses the intention to delete.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "delete", "assistant_ops", "thread_management", "topic_deletion", "destructive_operation", "topic_tree_removal"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_deletion", "research_cleanup", "topic_tree_removal", "theme_removal"],
    returns="Returns a text message containing the deletion result, the number of deleted topics, and the list of deleted topic IDs.",
)
async def delete_assistant_topic(
    title: Annotated[Optional[str], "Optional, topic title to be deleted; if left blank, the current topic will be deleted by default"] = None,
) -> str:
    """Delete the research topic tree."""
    from app.core.database import get_mongo_db
    from app.services.intelligent_assistant_service import ASSISTANT_DEFAULT_THREAD_ID, delete_assistant_thread

    user_id = require_current_user_id()
    db = get_mongo_db()

    try:
        thread_id = await _resolve_target_thread_id(db, user_id, title)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    if not thread_id:
        return "❌ There are currently no target topics to delete. Please specify the topic title first, or perform deletion under a certain topic."
    if thread_id == ASSISTANT_DEFAULT_THREAD_ID:
        return "❌ The default theme cannot be deleted. Please switch to another theme or delete the child theme under the default theme."

    target = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": thread_id,
        "archived": {"$ne": True},
    })
    if not target:
        return "❌ The target topic does not exist or has been deleted."

    try:
        deleted_ids = await delete_assistant_thread(db, user_id, thread_id)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    current_topic_id = await _get_bound_current_topic_id(db, user_id)
    if current_topic_id and current_topic_id in deleted_ids:
        fallback_topic_id = (target.get("parent_thread_id") or "").strip() or None
        await _bind_current_topic(db, user_id, fallback_topic_id)

    deleted_count = len(deleted_ids)
    return (
        f"✅ 已删除主题树「{target.get('title') or thread_id}」\n"
        f"- Number of topics deleted: {deleted_count}\n"
        f"- Delete topic ID: {', '.join(deleted_ids)}"
    )