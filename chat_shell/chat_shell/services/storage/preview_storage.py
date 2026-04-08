# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Redis-based preview storage for subscription tools.

Stores preview data in Redis with TTL (default 30 minutes).
Replaces the previous in-memory storage.
"""

import json
import logging
from typing import Any, Optional

import redis

from chat_shell.core.config import settings

logger = logging.getLogger(__name__)

# Redis key prefix for preview data
PREVIEW_KEY_PREFIX = "chat_shell:preview:"


def _get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client from settings."""
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        logger.error(f"[PreviewStorage] Failed to connect to Redis: {e}")
        return None


def _make_key(preview_id: str) -> str:
    """Generate Redis key for preview_id."""
    return f"{PREVIEW_KEY_PREFIX}{preview_id}"


def store_preview(preview_id: str, data: dict) -> bool:
    """Store preview data in Redis with TTL.

    Args:
        preview_id: The preview ID
        data: Preview data dict (will be JSON serialized)

    Returns:
        True if stored successfully, False otherwise
    """
    client = _get_redis_client()
    if not client:
        logger.error(f"[PreviewStorage] Redis not available, cannot store preview {preview_id}")
        return False

    try:
        key = _make_key(preview_id)
        ttl = settings.PREVIEW_STORAGE_TTL_SECONDS
        client.setex(key, ttl, json.dumps(data))
        logger.debug(f"[PreviewStorage] Stored preview {preview_id} with TTL {ttl}s")
        return True
    except Exception as e:
        logger.error(f"[PreviewStorage] Failed to store preview {preview_id}: {e}")
        return False


def get_preview(preview_id: str) -> Optional[dict]:
    """Retrieve preview data from Redis.

    Args:
        preview_id: The preview ID

    Returns:
        Preview data dict if found and not expired, None otherwise
    """
    client = _get_redis_client()
    if not client:
        logger.error(f"[PreviewStorage] Redis not available, cannot get preview {preview_id}")
        return None

    try:
        key = _make_key(preview_id)
        data = client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.error(f"[PreviewStorage] Failed to get preview {preview_id}: {e}")
        return None


def delete_preview(preview_id: str) -> bool:
    """Delete preview data from Redis (called after successful creation).

    Args:
        preview_id: The preview ID to delete

    Returns:
        True if deleted or not found, False on error
    """
    client = _get_redis_client()
    if not client:
        return False

    try:
        key = _make_key(preview_id)
        client.delete(key)
        logger.debug(f"[PreviewStorage] Deleted preview {preview_id}")
        return True
    except Exception as e:
        logger.error(f"[PreviewStorage] Failed to delete preview {preview_id}: {e}")
        return False


def clear_preview(preview_id: str) -> None:
    """Public interface to clear preview (alias for delete_preview).

    Args:
        preview_id: The preview ID to clear
    """
    delete_preview(preview_id)
