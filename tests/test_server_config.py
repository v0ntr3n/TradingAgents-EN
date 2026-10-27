#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test data server configuration functionality
"""

import pytest
pytest.importorskip("enhanced_stock_list_fetcher")
pytestmark = pytest.mark.integration

from enhanced_stock_list_fetcher import load_tdx_servers_config, get_mainmarket_ip
import json

def test_server_config():
    """Test server configuration loading function"""
    print("=== Test data server configuration functionality ===")

    # Test loading server configuration
    print("\n1. Test loading server configuration:")
    servers = load_tdx_servers_config()
    print(f"✅ successfully loaded {len(servers)} server configuration")

    # Show top 5 servers
    print("\n Top 5 server configurations:")
    for i, server in enumerate(servers[:5]):
        print(f"  {i+1}. {server.get('name', 'Unnamed')} - {server['ip']}:{server['port']}")

    # Test to get the main market IP
    print("\n2. Test to get the main market IP:")
    for i in range(3):
        ip, port = get_mainmarket_ip()
        print(f"  No.{i+1}randomly selected: {ip}:{port}")

    # Test specified IP and port
    print("\n3. Test specified IP and port:")
    ip, port = get_mainmarket_ip('192.168.1.1', 8888)
    print(f"  Specify IP and port: {ip}:{port}")

    # Display complete server configuration information
    print("\n4. Complete server configuration information:")
    print(json.dumps(servers, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_server_config()