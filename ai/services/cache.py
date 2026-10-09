import hashlib
import json

from django.conf import settings
from django.core.cache import cache


def cached_ai_result(
    *,
    user_id,
    operation,
    payload,
    generate,
):
    """
    Return a cached result when available.

    Cache keys are scoped to the authenticated user.
    No CV content is stored directly inside cache keys.
    """

    fingerprint = {
        "version": "m6-v1",
        "model": settings.M6_GEMINI_MODEL,
        "operation": operation,
        "payload": payload,
    }

    serialized = json.dumps(
        fingerprint,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()

    cache_key = f"m6:ai:{user_id}:{digest}"

    cached = cache.get(cache_key)

    if cached is not None:
        return cached, True

    result = generate()

    ttl = getattr(
        settings,
        "M6_CACHE_SECONDS",
        3600,
    )

    if ttl > 0:
        cache.set(cache_key, result, timeout=ttl)

    return result, False