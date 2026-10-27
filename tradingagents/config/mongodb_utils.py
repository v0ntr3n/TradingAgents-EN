#!/usr/bin/env python3
"""
MongoDB Connect string utility function
Unified management of MongoDB connection string construction logic
"""

import os
from typing import Optional


def build_mongodb_connection_string(
    host: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    database: Optional[str] = None,
    auth_source: Optional[str] = None
) -> str:
    """
    Build the MongoDB connection string
    
    priority:
    1. If the MONGODB_CONNECTION_STRING environment variable is set, use it directly
    2. If parameters are passed in, use the parameters passed in
    3. Otherwise read from environment variables MONGODB_HOST, MONGODB_PORT Wait
    
    Args:
        host: MongoDB host address
        port: MongoDB port
        username: Username
        password: Password
        database: Database name
        auth_source: Authentication database
    
    Returns:
        str: MongoDB connection string
        
    Examples:
        >>> # Use environment variables
        >>> conn_str = build_mongodb_connection_string()
        
        >>> # Use custom parameters
        >>> conn_str = build_mongodb_connection_string(
        ...     host='localhost',
        ...     port=27017,
        ...     username='admin',
        ...     password='password123'
        ... )
    """
    # Prefer using the MONGODB_CONNECTION_STRING environment variable
    env_conn_str = os.getenv('MONGODB_CONNECTION_STRING')
    if env_conn_str:
        return env_conn_str
    
    # Get configuration from parameters or environment variables
    host = host or os.getenv('MONGODB_HOST', 'localhost')
    port = port or int(os.getenv('MONGODB_PORT', '27017'))
    username = username or os.getenv('MONGODB_USERNAME', '')
    password = password or os.getenv('MONGODB_PASSWORD', '')
    database = database or os.getenv('MONGODB_DATABASE', 'tradingagents')
    auth_source = auth_source or os.getenv('MONGODB_AUTH_SOURCE', 'admin')
    
    # Build connection string
    if username and password:
        # Authentication connection string
        connection_string = f"mongodb://{username}:{password}@{host}:{port}/"
        # Add authSource parameter
        if database:
            connection_string += f"{database}?authSource={auth_source}"
        else:
            connection_string += f"?authSource={auth_source}"
    else:
        # Connection string without authentication
        connection_string = f"mongodb://{host}:{port}/"
        if database:
            connection_string += database
    
    return connection_string


def get_mongodb_database_name() -> str:
    """
    Get MongoDB database name
    
    priority:
    1. MONGODB_DATABASE_NAME environment variables
    2. MONGODB_DATABASE environment variables
    3. Default value 'tradingagents'
    
    Returns:
        str: Database name
    """
    return os.getenv('MONGODB_DATABASE_NAME') or os.getenv('MONGODB_DATABASE', 'tradingagents')


def get_mongodb_config() -> dict:
    """
    Get the complete MongoDB configuration

    Returns:
        dict: A dictionary containing connection_string and database_name
    """
    return {
        'connection_string': build_mongodb_connection_string(),
        'database_name': get_mongodb_database_name(),
        'auth_source': os.getenv('MONGODB_AUTH_SOURCE', 'admin')
    }


def build_redis_connection_string(
    host: Optional[str] = None,
    port: Optional[int] = None,
    password: Optional[str] = None,
    db: Optional[int] = None
) -> str:
    """
    Build a Redis connection string

    priority:
    1. If the REDIS_URL environment variable is set, use it directly
    2. If parameters are passed in, use the parameters passed in
    3. Otherwise read from environment variables REDIS_HOST, REDIS_PORT Wait

    Args:
        host: Redis host address
        port: Redis port
        password: Password
        db: database number

    Returns:
        str: Redis connection string

    Examples:
        >>> # Use environment variables
        >>> conn_str = build_redis_connection_string()

        >>> # Use custom parameters
        >>> conn_str = build_redis_connection_string(
        ...     host='localhost',
        ...     port=6379,
        ...     password='password123',
        ...     db=0
        ... )
    """
    # Prefer using the REDIS_URL environment variable
    env_conn_str = os.getenv('REDIS_URL')
    if env_conn_str:
        return env_conn_str

    # Get configuration from parameters or environment variables
    host = host or os.getenv('REDIS_HOST', 'localhost')
    port = port or int(os.getenv('REDIS_PORT', '6379'))
    password = password or os.getenv('REDIS_PASSWORD', '')
    db = db if db is not None else int(os.getenv('REDIS_DB', '0'))

    # Build connection string
    if password:
        # Connection string with password
        connection_string = f"redis://:{password}@{host}:{port}/{db}"
    else:
        # Connection string without password
        connection_string = f"redis://{host}:{port}/{db}"

    return connection_string

