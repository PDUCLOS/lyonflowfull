"""Le rate limit ne doit pas faire confiance à l'IP choisie par le client.

Nginx ajoute l'IP réelle en FIN de X-Forwarded-For : un client qui envoie
lui-même « X-Forwarded-For: 1.2.3.4 » ne doit pas changer de compartiment.
"""

from starlette.requests import Request

from src.api.middleware.rate_limit import RateLimitMiddleware


def _request(xff: str | None, peer: str = "10.0.0.5") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def _ip(xff: str | None) -> str:
    return RateLimitMiddleware(app=None)._get_client_ip(_request(xff))


def test_ip_ajoutee_par_le_proxy_est_retenue():
    # Le client forge « 1.2.3.4 », nginx ajoute l'IP réelle 203.0.113.7.
    assert _ip("1.2.3.4, 203.0.113.7") == "203.0.113.7"


def test_entete_unique_pose_par_le_proxy():
    assert _ip("203.0.113.7") == "203.0.113.7"


def test_sans_entete_on_prend_le_pair_tcp():
    assert _ip(None) == "10.0.0.5"
