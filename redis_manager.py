import os
import json
import logging
import asyncio
from typing import Optional, Any, Dict

logger = logging.getLogger("VoiceClaw.Redis")

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None

class RedisManager:
    """
    Asynchronous Redis Manager for VoiceClaw.
    Provides fast in-memory caching, distributed rate-limiting,
    and Pub/Sub message broker for real-time web dashboard synchronization.
    """
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.client: Optional[aioredis.Redis] = None
        self.is_ready = False
        self._pubsub_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        if not REDIS_AVAILABLE:
            logger.warning("[Redis] redis-py library not installed. Running in memory-only fallback mode.")
            return False

        try:
            self.client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=3.0,
                socket_connect_timeout=3.0
            )
            await self.client.ping()
            self.is_ready = True
            print(f"[VoiceClaw] [Redis] Connected successfully to {self.redis_url}")
            return True
        except Exception as e:
            self.is_ready = False
            self.client = None
            print(f"[VoiceClaw] [Redis Warning] Could not connect to Redis: {e}. Bot will safely fallback to local cache.")
            return False

    async def close(self):
        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
        if self.client:
            try:
                await self.client.aclose()
            except Exception:
                pass
            self.is_ready = False
            print("[VoiceClaw] [Redis] Connection closed cleanly.")

    # ==========================================
    # Caching: Channel Owners & State
    # ==========================================
    async def set_channel_owner(self, voice_id: int, user_id: int, ttl: int = 86400) -> None:
        if not self.is_ready or not self.client:
            return
        try:
            await self.client.set(f"voiceclaw:owner:{voice_id}", str(user_id), ex=ttl)
        except Exception as e:
            logger.debug(f"[Redis] set_channel_owner error: {e}")

    async def get_channel_owner(self, voice_id: int) -> Optional[int]:
        if not self.is_ready or not self.client:
            return None
        try:
            val = await self.client.get(f"voiceclaw:owner:{voice_id}")
            return int(val) if val else None
        except Exception as e:
            logger.debug(f"[Redis] get_channel_owner error: {e}")
            return None

    async def delete_channel_owner(self, voice_id: int) -> None:
        if not self.is_ready or not self.client:
            return
        try:
            await self.client.delete(f"voiceclaw:owner:{voice_id}")
        except Exception as e:
            logger.debug(f"[Redis] delete_channel_owner error: {e}")

    # ==========================================
    # Active Guild Room Sets
    # ==========================================
    async def add_active_room(self, guild_id: int, voice_id: int) -> None:
        if not self.is_ready or not self.client:
            return
        try:
            await self.client.sadd(f"voiceclaw:guild_rooms:{guild_id}", str(voice_id))
        except Exception as e:
            logger.debug(f"[Redis] add_active_room error: {e}")

    async def remove_active_room(self, guild_id: int, voice_id: int) -> None:
        if not self.is_ready or not self.client:
            return
        try:
            await self.client.srem(f"voiceclaw:guild_rooms:{guild_id}", str(voice_id))
        except Exception as e:
            logger.debug(f"[Redis] remove_active_room error: {e}")

    async def get_active_rooms(self, guild_id: int) -> list:
        if not self.is_ready or not self.client:
            return []
        try:
            rooms = await self.client.smembers(f"voiceclaw:guild_rooms:{guild_id}")
            return [int(r) for r in rooms]
        except Exception as e:
            logger.debug(f"[Redis] get_active_rooms error: {e}")
            return []

    # ==========================================
    # Rate Limiting & Cooldowns
    # ==========================================
    async def set_cooldown(self, key: str, duration_sec: int) -> bool:
        """Sets a cooldown key with TTL. Returns True if key was newly set, False if cooldown still active."""
        if not self.is_ready or not self.client:
            return True
        try:
            # SET NX returns True if key was set, None if key already existed
            res = await self.client.set(f"voiceclaw:cooldown:{key}", "1", ex=duration_sec, nx=True)
            return bool(res)
        except Exception:
            return True

    # ==========================================
    # Web Dashboard Real-Time Pub/Sub
    # ==========================================
    async def publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Publishes a real-time event to the 'voiceclaw:events' channel.
        The web dashboard or external services can listen to this stream.
        """
        if not self.is_ready or not self.client:
            return
        try:
            payload = json.dumps({
                "event": event_type,
                "data": data,
                "timestamp": asyncio.get_event_loop().time()
            })
            await self.client.publish("voiceclaw:events", payload)
        except Exception as e:
            logger.debug(f"[Redis] publish_event error: {e}")

redis_manager = RedisManager()
