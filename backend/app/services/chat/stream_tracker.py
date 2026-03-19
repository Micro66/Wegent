# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Stream Tracker for active task execution tracking.

This module provides Redis-based tracking of active streams to enable
real state verification (not just database status). It tracks:
- Active streams with heartbeats
- Stream metadata (shell type, executor location, start time)
- Orphaned task detection (database RUNNING but no active stream)

Key Design:
- Uses Redis Hash for stream metadata with TTL
- Uses Redis Sorted Set for stream list (by start time)
- Heartbeat updates keep stream alive
- Automatic cleanup via Redis TTL

Redis Key Design:
    # Active stream list (Sorted Set - score: start timestamp)
    active_streams:list

    # Stream metadata (Hash with TTL)
    active_streams:meta:{task_id}:{subtask_id}
    # Fields: task_id, subtask_id, shell_type, started_at,
    #         last_heartbeat, executor_location

    # Task-level stream count (String with TTL)
    active_streams:task:{task_id}:count
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import orjson
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis key prefixes
STREAM_LIST_KEY = "active_streams:list"
STREAM_META_PREFIX = "active_streams:meta"
STREAM_TASK_COUNT_PREFIX = "active_streams:task"

# Default TTL values (from config or defaults)
DEFAULT_STREAM_META_TTL = getattr(settings, "STREAM_META_TTL_SECONDS", 3600)  # 1 hour
DEFAULT_TASK_COUNT_TTL = getattr(settings, "STREAM_TASK_COUNT_TTL_SECONDS", 3600)


@dataclass
class StreamInfo:
    """Information about an active stream."""

    task_id: int
    subtask_id: int
    shell_type: str
    started_at: str
    last_heartbeat: float
    executor_location: str

    @property
    def stream_key(self) -> str:
        """Generate the stream key for this stream."""
        return f"{self.task_id}:{self.subtask_id}"

    @property
    def heartbeat_age_seconds(self) -> float:
        """Calculate how many seconds since last heartbeat."""
        return datetime.now(timezone.utc).timestamp() - self.last_heartbeat


class StreamTracker:
    """Redis-based tracker for active task streams.

    Tracks streams with heartbeat mechanism to enable real state verification.
    A stream is considered "active" if it has a recent heartbeat in Redis.
    """

    def __init__(self, redis_url: str):
        """Initialize the stream tracker.

        Args:
            redis_url: Redis connection URL
        """
        self._url = redis_url
        self._connection_params = {
            "encoding": "utf-8",
            "decode_responses": True,
            "max_connections": 10,
            "socket_timeout": 5.0,
            "socket_connect_timeout": 2.0,
            "retry_on_timeout": True,
        }

    async def _get_client(self) -> Redis:
        """Get Redis client."""
        return Redis.from_url(self._url, **self._connection_params)

    def _meta_key(self, task_id: int, subtask_id: int) -> str:
        """Generate metadata key for a stream."""
        return f"{STREAM_META_PREFIX}:{task_id}:{subtask_id}"

    def _task_count_key(self, task_id: int) -> str:
        """Generate task count key."""
        return f"{STREAM_TASK_COUNT_PREFIX}:{task_id}:count"

    def _get_stale_threshold_seconds(self) -> int:
        """Get the configured heartbeat staleness threshold."""
        return getattr(settings, "STREAM_STALE_THRESHOLD_SECONDS", 60)

    async def register_stream(
        self,
        task_id: int,
        subtask_id: int,
        shell_type: str,
        executor_location: str = "chat_shell",
        meta_ttl: int = DEFAULT_STREAM_META_TTL,
        count_ttl: int = DEFAULT_TASK_COUNT_TTL,
    ) -> bool:
        """Register a new active stream.

        Args:
            task_id: Task ID
            subtask_id: Subtask ID
            shell_type: Shell type (Chat, ClaudeCode, Agno, Dify)
            executor_location: Where the executor is running (chat_shell, executor_manager, inprocess)
            meta_ttl: TTL for stream metadata in seconds
            count_ttl: TTL for task count in seconds

        Returns:
            True if registration succeeded
        """
        try:
            client = await self._get_client()
            try:
                now = datetime.now(timezone.utc)
                timestamp = now.timestamp()
                started_at = now.isoformat()

                # Add to active streams list (Sorted Set)
                await client.zadd(
                    STREAM_LIST_KEY, {f"{task_id}:{subtask_id}": timestamp}
                )

                # Create metadata hash
                meta_key = self._meta_key(task_id, subtask_id)
                meta_data = {
                    "task_id": str(task_id),
                    "subtask_id": str(subtask_id),
                    "shell_type": shell_type,
                    "started_at": started_at,
                    "last_heartbeat": str(timestamp),
                    "executor_location": executor_location,
                }
                await client.hset(meta_key, mapping=meta_data)
                await client.expire(meta_key, meta_ttl)

                # Update task-level stream count
                count_key = self._task_count_key(task_id)
                count = await client.incr(count_key)
                await client.expire(count_key, count_ttl)

                logger.info(
                    f"[StreamTracker] Registered stream: task_id={task_id}, "
                    f"subtask_id={subtask_id}, shell_type={shell_type}, "
                    f"executor_location={executor_location}, count={count}"
                )
                return True
            finally:
                await client.aclose()
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to register stream: {e}")
            return False

    async def unregister_stream(self, task_id: int, subtask_id: int) -> bool:
        """Unregister a stream when execution completes.

        Args:
            task_id: Task ID
            subtask_id: Subtask ID

        Returns:
            True if unregistration succeeded
        """
        try:
            client = await self._get_client()
            try:
                stream_key = f"{task_id}:{subtask_id}"

                # Remove from active streams list
                await client.zrem(STREAM_LIST_KEY, stream_key)

                # Delete metadata
                meta_key = self._meta_key(task_id, subtask_id)
                await client.delete(meta_key)

                # Decrement task-level count (or delete if 0)
                count_key = self._task_count_key(task_id)
                count = await client.decr(count_key)
                if count <= 0:
                    await client.delete(count_key)

                logger.info(
                    f"[StreamTracker] Unregistered stream: task_id={task_id}, "
                    f"subtask_id={subtask_id}, remaining_count={max(0, count)}"
                )
                return True
            finally:
                await client.aclose()
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to unregister stream: {e}")
            return False

    async def update_heartbeat(
        self, task_id: int, subtask_id: int, ttl: int = DEFAULT_STREAM_META_TTL
    ) -> bool:
        """Update heartbeat timestamp for a stream.

        Args:
            task_id: Task ID
            subtask_id: Subtask ID
            ttl: TTL to refresh for metadata

        Returns:
            True if update succeeded
        """
        try:
            client = await self._get_client()
            try:
                meta_key = self._meta_key(task_id, subtask_id)

                # Check if stream exists first
                exists = await client.exists(meta_key)
                if not exists:
                    logger.warning(
                        f"[StreamTracker] Heartbeat for non-existent stream: "
                        f"task_id={task_id}, subtask_id={subtask_id}"
                    )
                    return False

                # Update heartbeat timestamp
                timestamp = datetime.now(timezone.utc).timestamp()
                await client.hset(meta_key, "last_heartbeat", str(timestamp))
                await client.expire(meta_key, ttl)

                return True
            finally:
                await client.aclose()
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to update heartbeat: {e}")
            return False

    async def is_stream_active(self, task_id: int, subtask_id: int) -> bool:
        """Check if a stream is currently active.

        A stream is active if its metadata exists in Redis (not expired).

        Args:
            task_id: Task ID
            subtask_id: Subtask ID

        Returns:
            True if stream is active
        """
        try:
            client = await self._get_client()
            try:
                meta_key = self._meta_key(task_id, subtask_id)
                exists = await client.exists(meta_key)
                return bool(exists)
            finally:
                await client.aclose()
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to check stream status: {e}")
            return False

    async def get_stream_info(
        self, task_id: int, subtask_id: int
    ) -> Optional[StreamInfo]:
        """Get detailed information about a stream.

        Args:
            task_id: Task ID
            subtask_id: Subtask ID

        Returns:
            StreamInfo if stream exists, None otherwise
        """
        try:
            client = await self._get_client()
            try:
                meta_key = self._meta_key(task_id, subtask_id)
                data = await client.hgetall(meta_key)

                if not data:
                    return None

                return StreamInfo(
                    task_id=int(data.get("task_id", 0)),
                    subtask_id=int(data.get("subtask_id", 0)),
                    shell_type=data.get("shell_type", "Unknown"),
                    started_at=data.get("started_at", ""),
                    last_heartbeat=float(data.get("last_heartbeat", 0)),
                    executor_location=data.get("executor_location", "unknown"),
                )
            finally:
                await client.aclose()
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to get stream info: {e}")
            return None

    async def get_task_active_streams(self, task_id: int) -> List[StreamInfo]:
        """Get all active streams for a task.

        Args:
            task_id: Task ID

        Returns:
            List of active StreamInfo objects
        """
        try:
            client = await self._get_client()
            try:
                # Scan for all metadata keys for this task
                pattern = f"{STREAM_META_PREFIX}:{task_id}:*"
                keys = []
                async for key in client.scan_iter(match=pattern):
                    keys.append(key)

                if not keys:
                    return []

                streams = []
                now = datetime.now(timezone.utc).timestamp()
                stale_threshold = self._get_stale_threshold_seconds()

                for key in keys:
                    data = await client.hgetall(key)
                    if not data:
                        continue

                    last_heartbeat = float(data.get("last_heartbeat", 0))
                    heartbeat_age = now - last_heartbeat

                    # Skip stale streams once heartbeat exceeds the configured threshold.
                    if heartbeat_age > stale_threshold:
                        logger.warning(
                            f"[StreamTracker] Skipping stale stream: "
                            f"task_id={data.get('task_id')}, subtask_id={data.get('subtask_id')}, "
                            f"heartbeat_age={heartbeat_age:.0f}s"
                        )
                        continue

                    streams.append(
                        StreamInfo(
                            task_id=int(data.get("task_id", 0)),
                            subtask_id=int(data.get("subtask_id", 0)),
                            shell_type=data.get("shell_type", "Unknown"),
                            started_at=data.get("started_at", ""),
                            last_heartbeat=last_heartbeat,
                            executor_location=data.get("executor_location", "unknown"),
                        )
                    )

                return streams
            finally:
                await client.aclose()
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to get task streams: {e}")
            return []

    async def get_all_active_streams(self) -> List[StreamInfo]:
        """Get all active streams across all tasks.

        Returns:
            List of all active StreamInfo objects
        """
        try:
            client = await self._get_client()
            try:
                # Scan for all metadata keys
                pattern = f"{STREAM_META_PREFIX}:*"
                keys = []
                async for key in client.scan_iter(match=pattern):
                    keys.append(key)

                if not keys:
                    return []

                streams = []
                now = datetime.now(timezone.utc).timestamp()
                stale_threshold = self._get_stale_threshold_seconds()

                for key in keys:
                    data = await client.hgetall(key)
                    if not data:
                        continue

                    last_heartbeat = float(data.get("last_heartbeat", 0))
                    heartbeat_age = now - last_heartbeat

                    # Skip stale streams once heartbeat exceeds the configured threshold.
                    if heartbeat_age > stale_threshold:
                        logger.warning(
                            f"[StreamTracker] Skipping stale stream: "
                            f"task_id={data.get('task_id')}, subtask_id={data.get('subtask_id')}, "
                            f"heartbeat_age={heartbeat_age:.0f}s"
                        )
                        continue

                    streams.append(
                        StreamInfo(
                            task_id=int(data.get("task_id", 0)),
                            subtask_id=int(data.get("subtask_id", 0)),
                            shell_type=data.get("shell_type", "Unknown"),
                            started_at=data.get("started_at", ""),
                            last_heartbeat=last_heartbeat,
                            executor_location=data.get("executor_location", "unknown"),
                        )
                    )

                return streams
            finally:
                await client.aclose()
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to get all streams: {e}")
            return []

    async def get_stale_streams(self, max_age_seconds: int = 3600) -> List[StreamInfo]:
        """Get streams that haven't had a heartbeat within the threshold.

        Note: This only returns streams that still exist in Redis but have
        stale heartbeats. Streams that have expired via TTL are already cleaned up.

        Args:
            max_age_seconds: Maximum age of last heartbeat

        Returns:
            List of stale StreamInfo objects
        """
        try:
            all_streams = await self.get_all_active_streams()
            now = datetime.now(timezone.utc).timestamp()

            stale_streams = []
            for stream in all_streams:
                if (now - stream.last_heartbeat) > max_age_seconds:
                    stale_streams.append(stream)

            return stale_streams
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to get stale streams: {e}")
            return []

    async def cleanup_stale_streams(self, max_age_seconds: int = 3600) -> int:
        """Clean up streams that are stale but somehow still in Redis.

        This is a safety cleanup for edge cases where TTL didn't work properly.

        Args:
            max_age_seconds: Maximum age of last heartbeat

        Returns:
            Number of streams cleaned up
        """
        try:
            stale_streams = await self.get_stale_streams(max_age_seconds)
            cleaned = 0

            for stream in stale_streams:
                # Double-check before cleaning up
                if await self.is_stream_active(stream.task_id, stream.subtask_id):
                    info = await self.get_stream_info(stream.task_id, stream.subtask_id)
                    if info and info.heartbeat_age_seconds > max_age_seconds:
                        await self.unregister_stream(stream.task_id, stream.subtask_id)
                        cleaned += 1
                        logger.warning(
                            f"[StreamTracker] Cleaned up stale stream: "
                            f"task_id={stream.task_id}, subtask_id={stream.subtask_id}, "
                            f"age={info.heartbeat_age_seconds:.0f}s"
                        )

            return cleaned
        except Exception as e:
            logger.error(f"[StreamTracker] Failed to cleanup stale streams: {e}")
            return 0


# Global stream tracker instance
stream_tracker = StreamTracker(settings.REDIS_URL)


def get_stream_tracker() -> StreamTracker:
    """Get the global stream tracker instance."""
    return stream_tracker
