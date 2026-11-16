"""
Redis cache helpers with graceful fallback.

If Redis is unreachable, every helper silently degrades to a no-op (cache miss),
and a short back-off window prevents each request from paying the connect timeout.
"""
import json
import logging
import time

import redis

REDIS_URL = 'redis://localhost:6379/0'
CACHE_TTL = 60  # seconds

ADMIN_COURSES_KEY = 'cache:admin:courses'
STUDENT_DASHBOARD_PREFIX = 'cache:student:dashboard:'

log = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(
    REDIS_URL,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
    decode_responses=True,
)

_RETRY_AFTER = 30  # seconds to skip Redis after a failure
_down_until = 0.0


def _available():
    return time.time() >= _down_until


def _mark_down(err):
    global _down_until
    _down_until = time.time() + _RETRY_AFTER
    log.warning("Redis unavailable (%s); caching disabled for %ss", err, _RETRY_AFTER)


def cache_get(key):
    if not _available():
        return None
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except (redis.RedisError, ValueError) as err:
        _mark_down(err)
        return None


def cache_set(key, value, ttl=CACHE_TTL):
    if not _available():
        return
    try:
        redis_client.setex(key, ttl, json.dumps(value))
    except (redis.RedisError, TypeError) as err:
        _mark_down(err)


def student_dashboard_key(student_id):
    return f"{STUDENT_DASHBOARD_PREFIX}{student_id}"


def invalidate_portal_cache():
    """Drop admin course list and every student dashboard cache entry."""
    if not _available():
        return
    try:
        keys = [ADMIN_COURSES_KEY] + list(redis_client.scan_iter(f"{STUDENT_DASHBOARD_PREFIX}*", count=200))
        redis_client.delete(*keys)
    except redis.RedisError as err:
        _mark_down(err)
