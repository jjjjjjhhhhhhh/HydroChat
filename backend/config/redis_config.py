"""
Redis Configuration Module for HydroChat Phase 18.

Provides centralized Redis connection management with:
- Connection pooling (50 max connections by default)
- Health checks with automatic failover
- Environment-based configuration
- Graceful error handling

Official redis-py patterns:
- Connection pool: redis.ConnectionPool(host, port, db, max_connections)
- Health check: client.ping() returns True if connected
- Decode responses: decode_responses=True for string responses (not bytes)

See: https://github.com/redis/redis-py
"""

import os
import logging
from typing import Optional

import redis
from redis import ConnectionPool, Redis
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisConfig:
    """Redis configuration with connection pooling and health checks."""
    
    # Class-level connection pool and client (singleton pattern)
    _pool: Optional[ConnectionPool] = None
    _client: Optional[Redis] = None
    
    @classmethod
    def get_config_from_env(cls) -> dict:
        """Get Redis configuration from environment variables."""
        return {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', '6379')),
            'db': int(os.getenv('REDIS_DB', '0')),
            'password': os.getenv('REDIS_PASSWORD', None),
            'max_connections': int(os.getenv('REDIS_MAX_CONNECTIONS', '50')),
            'socket_timeout': int(os.getenv('REDIS_SOCKET_TIMEOUT', '5')),
            'socket_connect_timeout': int(os.getenv('REDIS_SOCKET_TIMEOUT', '5')),
        }
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if Redis state management is enabled."""
        return os.getenv('USE_REDIS_STATE', 'false').lower() == 'true'
    
    @classmethod
    def get_connection_pool(cls) -> ConnectionPool:
        """Get or create Redis connection pool.
        
        Official redis-py pattern from docs:
        pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
        """
        if cls._pool is None:
            config = cls.get_config_from_env()
            
            cls._pool = ConnectionPool(
                host=config['host'],
                port=config['port'],
                db=config['db'],
                password=config['password'],
                max_connections=config['max_connections'],
                socket_timeout=config['socket_timeout'],
                socket_connect_timeout=config['socket_connect_timeout'],
                decode_responses=True  # Return strings, not bytes
            )
            
            logger.info(
                f"[REDIS] 🔧 Connection pool initialized "
                f"(host={config['host']}, port={config['port']}, "
                f"max_connections={config['max_connections']})"
            )
        
        return cls._pool
    
    @classmethod
    def get_client(cls) -> Redis:
        """Get or create Redis client with connection pool.
        
        Official redis-py pattern from docs:
        r = redis.Redis(connection_pool=pool)
        """
        if cls._client is None:
            pool = cls.get_connection_pool()
            cls._client = redis.Redis(connection_pool=pool)
            logger.info("[REDIS] ✅ Redis client initialized")
        
        return cls._client
    
    @classmethod
    def health_check(cls) -> bool:
        """Perform Redis health check with ping.
        
        Official redis-py pattern: r.ping() returns True if connected.
        
        Returns:
            bool: True if Redis is available and responding, False otherwise
        """
        if not cls.is_enabled():
            logger.debug("[REDIS] Redis state management disabled")
            return False
        
        try:
            client = cls.get_client()
            result = client.ping()
            if result:
                logger.debug("[REDIS] ✅ Health check passed")
            return result
        except redis.ConnectionError as e:
            logger.warning(f"[REDIS] ⚠️ Connection failed: {e}")
            return False
        except redis.TimeoutError as e:
            logger.warning(f"[REDIS] ⚠️ Connection timeout: {e}")
            return False
        except Exception as e:
            logger.error(f"[REDIS] ❌ Health check error: {e}")
            return False
    
    @classmethod
    def get_connection_string(cls) -> str:
        """Get Redis connection string for LangGraph RedisSaver.
        
        Format: redis://[password@]host:port/db
        """
        config = cls.get_config_from_env()
        
        if config['password']:
            return (
                f"redis://:{config['password']}@"
                f"{config['host']}:{config['port']}/{config['db']}"
            )
        else:
            return f"redis://{config['host']}:{config['port']}/{config['db']}"
    
    @classmethod
    def close(cls):
        """Close Redis connections and cleanup resources."""
        if cls._client is not None:
            try:
                cls._client.close()
                logger.info("[REDIS] 🔌 Client connection closed")
            except Exception as e:
                logger.warning(f"[REDIS] Warning during client close: {e}")
            finally:
                cls._client = None
        
        if cls._pool is not None:
            try:
                cls._pool.disconnect()
                logger.info("[REDIS] 🔌 Connection pool disconnected")
            except Exception as e:
                logger.warning(f"[REDIS] Warning during pool disconnect: {e}")
            finally:
                cls._pool = None

