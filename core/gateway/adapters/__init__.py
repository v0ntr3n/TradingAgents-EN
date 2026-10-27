"""
Gateway adapter pack

Each IM platform implements an adapter subclass responsible for:
1. Verify webhook signature
2. Parse the platform message as GatewayMessage
3. Send GatewayResponse to platform
"""

