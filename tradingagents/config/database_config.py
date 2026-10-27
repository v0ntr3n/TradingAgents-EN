#!/usr/bin/env python3
"""
Database configuration management module
Unified management of MongoDB and Redis connection configurations
"""

import os
from typing import Dict, Any, Optional
from .mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name


class DatabaseConfig:
    """Database configuration management class"""

    @staticmethod
    def get_mongodb_config() -> Dict[str, Any]:
        """
        Get MongoDB configuration

        Returns:
            Dict[str, Any]: MongoDB Configuration dictionary
        """
        return {
            'connection_string': build_mongodb_connection_string(),
            'database': get_mongodb_database_name(),
            'auth_source': os.getenv('MONGODB_AUTH_SOURCE', 'admin')
        }
    
    @staticmethod
    def get_redis_config() -> Dict[str, Any]:
        """
        Get Redis configuration
        
        Returns:
            Dict[str, Any]: Redis Configuration dictionary
            
        Raises:
            ValueError: When necessary configuration is not set
        """
        # Prefer connection strings
        connection_string = os.getenv('REDIS_CONNECTION_STRING')
        if connection_string:
            return {
                'connection_string': connection_string,
                'database': int(os.getenv('REDIS_DATABASE', 0))
            }
        
        # Use separate configuration parameters
        host = os.getenv('REDIS_HOST')
        port = os.getenv('REDIS_PORT')
        
        if not host or not port:
            raise ValueError(
                "Redis The connection configuration is not fully set up. Please set one of the following environment variables:\n"
                "1. REDIS_CONNECTION_STRING=redis://localhost:6379/0\n"
                "2. REDIS_HOST + REDIS_PORT (For example: REDIS_HOST=localhost, REDIS_PORT=6379)"
            )
        
        return {
            'host': host,
            'port': int(port),
            'password': os.getenv('REDIS_PASSWORD'),
            'database': int(os.getenv('REDIS_DATABASE', 0))
        }
    
    @staticmethod
    def validate_config() -> Dict[str, bool]:
        """
        Verify database configuration is complete
        
        Returns:
            Dict[str, bool]: Verification results
        """
        result = {
            'mongodb_valid': False,
            'redis_valid': False
        }
        
        try:
            DatabaseConfig.get_mongodb_config()
            result['mongodb_valid'] = True
        except ValueError:
            pass
        
        try:
            DatabaseConfig.get_redis_config()
            result['redis_valid'] = True
        except ValueError:
            pass
        
        return result
    
    @staticmethod
    def get_config_status() -> str:
        """
        Get a friendly description of configuration status
        
        Returns:
            str: Configuration status description
        """
        validation = DatabaseConfig.validate_config()
        
        if validation['mongodb_valid'] and validation['redis_valid']:
            return "✅ All database configurations are normal"
        elif validation['mongodb_valid']:
            return "⚠️ MongoDB The configuration is normal, but the Redis configuration is missing."
        elif validation['redis_valid']:
            return "⚠️ Redis Configuration is normal, MongoDB configuration is missing"
        else:
            return "❌ Database configuration is missing, please check environment variables"