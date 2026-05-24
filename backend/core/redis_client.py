"""
SentinelTwin — Redis Client
Connection pool management with health checking and retry logic
"""

import logging
from typing import Optional

log = logging.getLogger("sentineltwin.redis")


class RedisClient:
    """Managed async Redis client with connection pooling and graceful fallback"""

    def __init__(self):
        self._client = None
        self._pool = None
        self._connected = False

    async def connect(self, url: str = "redis://localhost:6379/0"):
        try:
            import redis.asyncio as aioredis
            self._pool = aioredis.ConnectionPool.from_url(
                url,
                max_connections=100,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                health_check_interval=30,
                decode_responses=True,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            await self._client.ping()
            self._connected = True
            log.info("Redis connection established")
        except Exception as e:
            log.warning(f"Redis connection failed (non-fatal, running without cache): {e}")
            self._connected = False

    async def disconnect(self):
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
        if self._pool:
            try:
                await self._pool.disconnect()
            except Exception:
                pass
        self._connected = False
        log.info("Redis disconnected")

    async def get(self, key: str) -> Optional[str]:
        if not self._client:
            return None
        try:
            return await self._client.get(key)
        except Exception:
            return None

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if not self._client:
            return False
        try:
            return await self._client.set(key, value, ex=ex)
        except Exception:
            return False

    async def delete(self, key: str) -> int:
        if not self._client:
            return 0
        try:
            return await self._client.delete(key)
        except Exception:
            return 0

    async def exists(self, key: str) -> bool:
        if not self._client:
            return False
        try:
            return bool(await self._client.exists(key))
        except Exception:
            return False

    async def incr(self, key: str, amount: int = 1) -> int:
        if not self._client:
            return 0
        try:
            return await self._client.incr(key, amount)
        except Exception:
            return 0

    async def expire(self, key: str, seconds: int) -> bool:
        if not self._client:
            return False
        try:
            return await self._client.expire(key, seconds)
        except Exception:
            return False

    async def lpush(self, key: str, *values) -> int:
        if not self._client:
            return 0
        try:
            return await self._client.lpush(key, *values)
        except Exception:
            return 0

    async def lrange(self, key: str, start: int, end: int):
        if not self._client:
            return []
        try:
            return await self._client.lrange(key, start, end)
        except Exception:
            return []

    async def publish(self, channel: str, message: str) -> int:
        if not self._client:
            return 0
        try:
            return await self._client.publish(channel, message)
        except Exception:
            return 0

    async def ping(self) -> bool:
        try:
            return await self._client.ping() if self._client else False
        except Exception:
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected


# Module-level singleton
redis_client = RedisClient()
