"""
Sample data provider

Shows how to create a new data source provider
"""

from .example_sdk import ExampleSDKProvider

__all__ = [
    'ExampleSDKProvider',
]


def get_example_sdk_provider(**kwargs):
    """获取示例SDK提供器实例"""
    return ExampleSDKProvider(**kwargs)

