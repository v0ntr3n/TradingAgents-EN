"""
Webhook push sender

Supports three webhook robot formats: Feishu, DingTalk, and WeChat Enterprise.
The protocol is the same, only the JSON body format is slightly different.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from app.models.channel_config import ChannelConfig, ChannelType

logger = logging.getLogger("webapi.channel_senders.webhook")

# HTTP Request timeout (seconds)
WEBHOOK_TIMEOUT = 10


def _build_feishu_payload(title: str, content: str) -> Dict[str, Any]:
    """
    Feishu custom robot message format
    https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
    """
    return {
        "msg_type": "text",
        "content": {
            "text": f"【{title}】\n{content}"
        }
    }


def _build_dingtalk_payload(title: str, content: str) -> Dict[str, Any]:
    """
    DingTalk custom robot message format
    https://open.dingtalk.com/document/robots/custom-robot-access
    """
    return {
        "msgtype": "text",
        "text": {
            "content": f"【{title}】\n{content}"
        }
    }


def _build_wechatwork_payload(title: str, content: str) -> Dict[str, Any]:
    """
    Enterprise WeChat custom robot message format
    https://developer.work.weixin.qq.com/document/path/91770
    """
    return {
        "msgtype": "text",
        "text": {
            "content": f"【{title}】\n{content}"
        }
    }


_BUILDERS = {
    ChannelType.FEISHU: _build_feishu_payload,
    ChannelType.DINGTALK: _build_dingtalk_payload,
    ChannelType.WECHATWORK: _build_wechatwork_payload,
}


async def send_webhook(
    channel: ChannelConfig,
    title: str,
    content: str,
) -> bool:
    """
    Send webhook notification

    Returns:
        True  — Sent successfully
        False — Sending failed
    """
    if not channel.webhook_url:
        logger.warning(f"渠道 [{channel.name}] 未配置 Webhook URL，跳过")
        return False

    builder = _BUILDERS.get(channel.type)
    if not builder:
        logger.warning(f"未知渠道类型: {channel.type}，跳过")
        return False

    payload = builder(title, content)

    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            resp = await client.post(
                channel.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()

            # The success signs of each platform are different, but HTTP 2xx is enough to judge
            logger.info(
                f"✅ Webhook Push successful: [{channel.name}({channel.type})] "
                f"status={resp.status_code}"
            )
            return True

    except httpx.TimeoutException:
        logger.warning(f"⚠️ Webhook timeout: [{channel.name}] url={channel.webhook_url}")
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"⚠️ Webhook HTTP Error: [{channel.name}] status={e.response.status_code} "
            f"body={e.response.text[:200]}"
        )
    except Exception as e:
        logger.error(f"❌ Webhook Push failed: [{channel.name}] {e}")

    return False

