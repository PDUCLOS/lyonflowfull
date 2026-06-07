"""Middleware rate limit — FastAPI.

Limite par IP :
- /api/ : 10 req/s burst 20
- /api/v1/auth/login : 5 req/min (anti brute force)
- /api/v1/rgpd/* : 3 req/h (anti spam)

Implémentation simple in-memory (production : Redis backend).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.rgpd.service import log_audit


logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit basique par IP avec buckets en mémoire.

    IMPORTANT : dispatch() doit retourner un Response, jamais lever d'exception.
    On retourne un JSONResponse 429 si limite dépassée.
    """

    def __init__(self, app):
        super().__init__(app)
        # IP → {bucket_name: [(timestamp, count), ...]}
        self._buckets: dict[str, dict[str, list[tuple[float, int]]]] = defaultdict(lambda: defaultdict(list))

    async def dispatch(self, request: Request, call_next):
        ip = self._get_client_ip(request)
        path = request.url.path

        # Identifier la règle applicable
        rule = self._match_rule(path)
        if not rule:
            return await call_next(request)

        bucket_name, max_requests, window_seconds = rule

        # Vérifier et nettoyer
        now = time.time()
        key = f"{ip}:{bucket_name}"
        bucket = self._buckets[key][bucket_name]

        # Purge les anciens
        bucket[:] = [(t, c) for t, c in bucket if now - t < window_seconds]

        # Compte total
        total = sum(c for _, c in bucket)

        if total >= max_requests:
            # Audit
            log_audit(
                actor="rate_limit",
                action="rate_limit_exceeded",
                resource_type="endpoint",
                resource_id=path,
                ip_address=ip,
                details={"bucket": bucket_name, "limit": max_requests, "window": window_seconds},
            )
            # JSONResponse (pas HTTPException, car dispatch doit retourner Response)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded: {max_requests} req / {window_seconds}s",
                    "retry_after": window_seconds,
                },
                headers={"Retry-After": str(window_seconds)},
            )

        # Enregistrer la requête
        bucket.append((now, 1))

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        """Récupère l'IP client (X-Forwarded-For en priorité)."""
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _match_rule(self, path: str) -> Optional[tuple[str, int, int]]:
        """Matche le path avec une règle de rate limit.

        Returns:
            Tuple (bucket_name, max_requests, window_seconds) ou None.
        """
        if "/api/v1/auth/login" in path:
            return ("login", 5, 60)  # 5 req/min
        if "/api/v1/rgpd/" in path:
            return ("rgpd", 3, 3600)  # 3 req/h
        if path.startswith("/api/"):
            return ("api", 10, 1)  # 10 req/s burst 20
        return None
