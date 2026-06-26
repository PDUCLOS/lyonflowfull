"""Middleware rate limit — FastAPI.

Limite par IP :
- /api/ : 10 req/s burst 20
- /api/v1/auth/login : 5 req/min (anti brute force)
- /api/v1/rgpd/* : 3 req/h (anti spam)

Implémentation simple in-memory (production : Redis backend).

Sprint P1.4 (2026-06-14) — AUDIT_INTEGRATION_LIVE.md § 2.2.3 :
- TTL idle sur les clés IP (1h) : les IPs qui n'ont pas fait de requête
  depuis > 1h sont purgées. Empêche l'OOM en cas d'attaque distribuée
  (botnet générant des millions d'IPs uniques).
- Trigger : lazy cleanup à chaque dispatch si la taille du dict dépasse
  un seuil (évite un scan O(n) à chaque requête).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.rgpd.service import log_audit

logger = logging.getLogger(__name__)


# Seuil au-delà duquel on déclenche un cleanup opportuniste des IPs inactives.
# 10k IPs x 3 buckets = 30k entrées = ~5 MB en RAM (acceptable).
# En dessous, on ne fait pas de scan (perf).
_BUCKETS_CLEANUP_THRESHOLD = 10_000

# Une clé IP non vue depuis > TTL_IDLE_SECONDS est purgée.
# 1h = largement suffisant pour les fenêtres de rate-limit (max 3600s pour rgpd).
_TTL_IDLE_SECONDS = 3600

# Sprint P2.4 (2026-06-14) — Sampling d'audit sous attaque.
# En cas de pic (même IP bloquee plusieurs fois dans la fenêtre), on ne
# loggue pas systematiquement chaque 429. Sinon un attaquant peut
# sature rgpd.audit_log et DoS la DB.
# 1.0 = audit 100% ; 0.1 = audit 10% (1 sur 10). On garde la première
# violation (toujours logguee) puis on sample.
_AUDIT_SAMPLE_RATE = 0.1


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit basique par IP avec buckets en mémoire.

    IMPORTANT : dispatch() doit retourner un Response, jamais lever d'exception.
    On retourne un JSONResponse 429 si limite dépassée.

    Sprint P1.4 : la structure ``_buckets`` est purgée des IPs inactives
    de manière opportuniste (lazy cleanup) pour éviter une croissance
    non bornée. Cf. constantes ``_BUCKETS_CLEANUP_THRESHOLD`` et
    ``_TTL_IDLE_SECONDS``.
    """

    def __init__(self, app):
        super().__init__(app)
        # IP → (last_seen_ts, {bucket_name: [(timestamp, count), ...]})
        # Le last_seen_ts permet le cleanup TTL sans scanner les buckets.
        self._buckets: dict[str, tuple[float, dict[str, list[tuple[float, int]]]]] = {}

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

        # Lazy cleanup : si on dépasse le seuil, on purge les IPs inactives.
        if len(self._buckets) > _BUCKETS_CLEANUP_THRESHOLD:
            self._purge_idle_keys(now)

        # Récupérer ou créer l'entrée
        if key in self._buckets:
            _last_seen, ip_buckets = self._buckets[key]
        else:
            ip_buckets = defaultdict(list)
            self._buckets[key] = (now, ip_buckets)

        bucket = ip_buckets[bucket_name]

        # Purge les anciens dans le bucket
        bucket[:] = [(t, c) for t, c in bucket if now - t < window_seconds]

        # Compte total
        total = sum(c for _, c in bucket)

        if total >= max_requests:
            # Sprint P2.4 (2026-06-14) — Sampling d'audit.
            # On loggue toujours la PREMIÈRE violation (compteur == 1
            # dans le bucket), puis on sample selon _AUDIT_SAMPLE_RATE
            # pour éviter de saturer rgpd.audit_log en cas d'attaque.
            should_audit = (total == 1) or (hash((ip, bucket_name, total)) % 100 < (_AUDIT_SAMPLE_RATE * 100))
            if should_audit:
                log_audit(
                    actor="rate_limit",
                    action="rate_limit_exceeded",
                    resource_type="endpoint",
                    resource_id=path,
                    ip_address=ip,
                    details={
                        "bucket": bucket_name,
                        "limit": max_requests,
                        "window": window_seconds,
                        "violation_count": total,
                    },
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
        # Mettre à jour last_seen (immutable update du tuple)
        self._buckets[key] = (now, ip_buckets)

        return await call_next(request)

    def _purge_idle_keys(self, now: float) -> None:
        """Purge les clés IP non vues depuis > _TTL_IDLE_SECONDS.

        Appelé en lazy cleanup (seulement quand _buckets > threshold).
        En dessous du threshold, on évite le coût du scan O(n).
        """
        before = len(self._buckets)
        self._buckets = {
            k: (last_seen, b)
            for k, (last_seen, b) in self._buckets.items()
            if now - last_seen < _TTL_IDLE_SECONDS
        }
        after = len(self._buckets)
        if before != after:
            logger.info(
                "RateLimit cleanup: %d → %d IPs (purgées %d inactives > %ds)",
                before, after, before - after, _TTL_IDLE_SECONDS,
            )

    def _get_client_ip(self, request: Request) -> str:
        """Récupère l'IP client (X-Forwarded-For en priorité)."""
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _match_rule(self, path: str) -> tuple[str, int, int] | None:
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
