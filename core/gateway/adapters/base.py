"""
Gateway Adapter abstract base class

All IM platform adapters must inherit BaseGatewayAdapter and implement the following methods:
- verify_request()   Verify webhook signature/Challenge
- parse_message()    Parse the original request as GatewayMessage
- send_response()    Push GatewayResponse to the platform
- format_report()    Format analysis reports into the best presentation format for the platform
"""

import abc
import logging
from typing import Any, Dict, Optional, Tuple

from core.gateway.models import (
    ChannelType,
    GatewayMessage,
    GatewayResponse,
    ResponseType,
)

logger = logging.getLogger(__name__)


class BaseGatewayAdapter(abc.ABC):
    """IM Platform adapter abstract base class"""

    channel_type: ChannelType  # Subclasses must declare

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: platform configuration (app_id, app_secret, webhook_token etc.),
                    Read from system_configs collection
        """
        self.config = config

    # ------------------------------------------------------------------ #
    # Abstract methods that must be implemented
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    async def verify_request(
        self, headers: Dict[str, str], body: bytes
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Verify the legitimacy of platform webhook requests.

        Returns:
            (is_valid, challenge_response)
            - is_valid: Is the signature legal?
            - challenge_response: If it is a platform verification request (such as Feishu Challenge),
              Return JSON that needs to be returned directly to the platform; for ordinary messages, it is None
        """
        ...

    @abc.abstractmethod
    async def parse_message(
        self, headers: Dict[str, str], body: bytes
    ) -> Optional[GatewayMessage]:
        """
        Parse the original webhook body into a unified GatewayMessage.

        Some events (such as users entering the group, message withdrawal) do not need to be processed and will be skipped by returning None.
        """
        ...

    @abc.abstractmethod
    async def send_response(self, response: GatewayResponse) -> bool:
        """
        Push the GatewayResponse to the IM platform.

        Returns:
            Whether sent successfully
        """
        ...

    # ------------------------------------------------------------------ #
    # Optional overridable methods (providing reasonable default implementations)
    # ------------------------------------------------------------------ #

    def format_report_as_response(
        self, report_text: str, channel_id: str
    ) -> GatewayResponse:
        """
        Convert analysis report text to a platform-appropriate GatewayResponse.
        Markdown is returned by default, and subclasses can override it as card messages.
        """
        return GatewayResponse(
            channel_type=self.channel_type.value,
            channel_id=channel_id,
            response_type=ResponseType.MARKDOWN,
            content=report_text,
        )

    def truncate_for_platform(self, text: str, max_length: int = 4000) -> str:
        """Truncate overly long text to adapt to the platform message length limit"""
        if len(text) <= max_length:
            return text
        return text[: max_length - 20] + "\n\n… (The content is too long and has been cut off)"

