"""FastAPI — REST endpoints LyonFlowFull.

Expose :
- /health : health check public
- /api/v1/models : liste des modèles MLflow
- /api/v1/predict/traffic : prédiction vitesse trafic par nœud/horizon
- /api/v1/predict/velov : prédiction dispo Vélov
- /api/v1/recommend : recommandation trajet multimodale
- /api/v1/bottlenecks : liste des bottlenecks infrastructure
- /api/v1/rgpd/request : demande RGPD (accès/suppression)
"""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from src.api.metrics import (
    PREDICTION_LATENCY,
    PREDICTIONS_TOTAL,
)
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.config import get_settings, validate_settings
from src.db import execute_query, test_connection
from src.rgpd.service import log_audit, log_data_subject_request

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# App init — lifespan (FastAPI moderne, on_event est déprécié)
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validation settings au démarrage, log au shutdown."""
    try:
        validate_settings()
        logger.info("LyonFlowFull API started")
    except RuntimeError as e:
        logger.error(f"Settings validation failed: {e}")
        # On ne lève pas pour permettre /health de répondre
    yield
    logger.info("LyonFlowFull API shutting down")


app = FastAPI(
    title="LyonFlowFull API",
    version="0.6.1",
    description="API REST pour la plateforme MLOps LyonFlowFull",
    lifespan=lifespan,
)


# CORS
s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=s.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limit (en mémoire — Redis en prod)
app.add_middleware(RateLimitMiddleware)

# Prometheus instrumentation (Sprint VPS-4) — expose /metrics
# - http_requests_total{job="fastapi",method,handler,status}
# - http_request_duration_seconds histogram
# - process_* metrics (CPU, RAM, fds)
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/metrics"],
    inprogress_name="lyonflow_http_inprogress",
    inprogress_labels=True,
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


# -----------------------------------------------------------------------------
# JWT helpers
# -----------------------------------------------------------------------------
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


def create_jwt(user_id: str, username: str, persona_id: str) -> str:
    """Génère un JWT signé pour un utilisateur authentifié.

    Args:
        user_id: UUID de l'utilisateur
        username: nom d'utilisateur
        persona_id: 'pro_tcl' | 'elu' | 'admin'

    Returns:
        Token JWT signé.

    Raises:
        RuntimeError: si JWT_SECRET_KEY absent en env.
    """
    s = get_settings()
    # Variable env dédiée JWT_SECRET_KEY, sinon fallback sur api.key
    secret = os.getenv("JWT_SECRET_KEY") or s.api.key
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY ou LYONFLOW_API_KEY requis pour signer les tokens. "
            "Définir dans .env (générer via `openssl rand -base64 32`)."
        )
    payload = {
        "sub": user_id,
        "username": username,
        "persona": persona_id,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=JWT_EXPIRY_HOURS),
        "jti": secrets.token_urlsafe(16),  # unique token id
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Décode et vérifie un JWT. Lève HTTPException si invalide."""
    s = get_settings()
    secret = os.getenv("JWT_SECRET_KEY") or s.api.key
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY ou LYONFLOW_API_KEY requis")
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")


# -----------------------------------------------------------------------------
# Auth — header X-API-Key
# -----------------------------------------------------------------------------
async def verify_api_key(x_api_key: str | None = Header(None)):
    """Vérifie la présence de l'API key (sauf pour /health).

    Sécurité : l'auth est TOUJOURS vérifiée sauf si DISABLE_AUTH=true
    (uniquement pour dev local, JAMAIS en prod).
    """
    s = get_settings()
    if os.getenv("DISABLE_AUTH", "false").lower() == "true":
        return  # dev only — JAMAIS en prod

    if not s.api.key:
        raise HTTPException(status_code=500, detail="LYONFLOW_API_KEY non configuré sur le serveur")
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="X-API-Key header requis",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    # Comparaison constant-time (anti timing attack)
    import hmac

    if not hmac.compare_digest(x_api_key, s.api.key):
        raise HTTPException(status_code=401, detail="API key invalide")


# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    version: str
    db: bool
    timestamp: str


class PredictTrafficRequest(BaseModel):
    node_idx: int
    horizon_minutes: int = 30
    measurement_time: datetime | None = None


class PredictTrafficResponse(BaseModel):
    node_idx: int
    horizon_minutes: int
    predicted_speed_kmh: float
    confidence_low: float
    confidence_high: float
    model_name: str
    model_version: str
    prediction_timestamp: str


class PredictVelovRequest(BaseModel):
    station_id: str
    horizon_minutes: int = 30


class PredictVelovResponse(BaseModel):
    station_id: str
    horizon_minutes: int
    predicted_bikes: float
    actual_bikes: int | None
    model_name: str
    prediction_timestamp: str


class RecommendRequest(BaseModel):
    origin: str
    destination: str
    departure_time: datetime | None = None
    modes_allowed: list[str] = Field(default_factory=lambda: ["transit", "bike", "walk"])


class RecommendResponse(BaseModel):
    options: list[dict]
    recommended: dict
    score_breakdown: dict


class ItineraryRequest(BaseModel):
    origin_lon: float
    origin_lat: float
    destination_lon: float
    destination_lat: float
    horizon_minutes: int = 0


class ItinerarySegmentResponse(BaseModel):
    channel_id: str
    length_m: float
    speed_kmh: float
    duration_s: float
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float


class ItineraryResponse(BaseModel):
    origin_node: str
    destination_node: str
    horizon_minutes: int
    segments: list[ItinerarySegmentResponse]
    total_length_m: float
    total_duration_s: float
    average_speed_kmh: float
    total_duration_min: float
    confiance: float


class BottleneckItem(BaseModel):
    id: int
    segment_id: str
    line_ref: str | None
    diagnosis: str
    bus_delay_seconds: float | None
    traffic_speed_kmh: float | None
    traffic_congestion: float | None
    n_observations: int | None


class RgpdRequest(BaseModel):
    user_identifier: str  # hash anonyme
    request_type: str  # 'access' | 'deletion' | 'portability' | 'rectification'
    notes: str | None = None


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    """Health check (pas d'auth requise)."""
    s = get_settings()
    return HealthResponse(
        status="ok",
        version=s.app_version,
        db=test_connection(),
        timestamp=datetime.now().isoformat(),
    )


@app.get("/api/v1/models", tags=["models"])
async def list_models(api_key: None = Depends(verify_api_key)):
    """Liste les modèles MLflow disponibles."""
    from src.ml.mlflow_integration import is_mlflow_available, list_registered_models

    if not is_mlflow_available():
        # Fallback si MLflow est indisponible
        return {
            "models": [
                {
                    "name": "xgboost_speed",
                    "version": "1.2.0",
                    "stage": "Production",
                    "metrics": {"mae": 1.96, "r2": 0.947},
                },
                {
                    "name": "xgboost_velov",
                    "version": "1.0.0",
                    "stage": "Production",
                    "metrics": {"mae": 4.2, "r2": 0.331},
                },
                {"name": "stgcn_gnn", "version": "0.3.0", "stage": "Staging", "metrics": {"mae": 2.8, "r2": 0.92}},
            ]
        }

    models = list_registered_models()
    return {"models": models}


@app.post("/api/v1/predict/traffic", response_model=PredictTrafficResponse, tags=["predict"])
async def predict_traffic(req: PredictTrafficRequest, api_key: None = Depends(verify_api_key)):
    """Prédit la vitesse trafic pour un nœud et un horizon."""
    # Sprint VPS-4 : métriques ML
    with PREDICTION_LATENCY.labels(model="xgboost_speed").time():
        from src.models.xgboost_speed import XGBoostSpeedModel

        # TODO: Câbler la récupération du modèle depuis MLflow Registry en priorité
        # En attendant, on utilise la logique locale/fallback du modèle XGBoost
        model = XGBoostSpeedModel()
        prediction = model.predict(req.node_idx, req.horizon_minutes)

    PREDICTIONS_TOTAL.labels(
        model="xgboost_speed",
        horizon_minutes=str(req.horizon_minutes),
        status="success",
    ).inc()
    log_audit(
        actor="api",
        action="predict_traffic",
        resource_type="traffic_node",
        resource_id=str(req.node_idx),
        details={"horizon": req.horizon_minutes},
    )
    return PredictTrafficResponse(
        node_idx=req.node_idx,
        horizon_minutes=req.horizon_minutes,
        prediction_timestamp=datetime.now().isoformat(),
        **prediction,
    )


@app.post("/api/v1/predict/velov", response_model=PredictVelovResponse, tags=["predict"])
async def predict_velov(req: PredictVelovRequest, api_key: None = Depends(verify_api_key)):
    """Prédit la disponibilité Vélov pour une station et un horizon."""
    # Sprint VPS-4 : métriques ML
    with PREDICTION_LATENCY.labels(model="xgboost_velov").time():
        from src.models.xgboost_velov import XGBoostVelovModel

        model = XGBoostVelovModel()
        # Fallback local le temps que MLflow soit câblé
        pred_dict = model.predict(req.station_id, req.horizon_minutes)
        predicted = pred_dict["predicted_bikes"]
    PREDICTIONS_TOTAL.labels(
        model="xgboost_velov",
        horizon_minutes=str(req.horizon_minutes),
        status="success",
    ).inc()
    return PredictVelovResponse(
        station_id=req.station_id,
        horizon_minutes=req.horizon_minutes,
        predicted_bikes=predicted,
        actual_bikes=None,
        model_name="xgboost_velov",
        prediction_timestamp=datetime.now().isoformat(),
    )


@app.post("/api/v1/recommend", response_model=RecommendResponse, tags=["recommend"])
async def recommend(req: RecommendRequest, api_key: None = Depends(verify_api_key)):
    """Recommandation trajet multimodale (basée sur prédictions)."""
    # Placeholder — utilise src/routing/travel_recommender
    options = [
        {
            "mode": "transit",
            "mode_label": "Métro A",
            "duration_min": 18,
            "cost_eur": 1.90,
            "co2_g": 30,
            "confidence_pct": 78,
        },
        {
            "mode": "bike",
            "mode_label": "Vélov",
            "duration_min": 22,
            "cost_eur": 0.0,
            "co2_g": 0,
            "confidence_pct": 65,
        },
        {
            "mode": "car",
            "mode_label": "Voiture",
            "duration_min": 24,
            "cost_eur": 4.20,
            "co2_g": 1800,
            "confidence_pct": 82,
        },
    ]
    return RecommendResponse(
        options=options,
        recommended=options[0],
        score_breakdown={"time": 0.5, "cost": 0.3, "eco": 0.2},
    )


@app.post("/api/v1/itinerary", response_model=ItineraryResponse, tags=["routing"])
async def itinerary(req: ItineraryRequest, api_key: None = Depends(verify_api_key)):
    """Calcule un itinéraire traffic-aware.

    Body:
    - origin_lon, origin_lat : coords GPS du départ
    - destination_lon, destination_lat : coords GPS de l'arrivée
    - horizon_minutes : 0 = maintenant, sinon H+ (utilise vitesse prédite)

    Returns:
    - Itinéraire complet avec segments détaillés (length, speed, duration)
    - Total durée / longueur / vitesse moyenne
    - Confiance (0..1) basée sur fraîcheur des données
    """
    from src.routing import compute_itinerary

    itin = compute_itinerary(
        origin_lon=req.origin_lon,
        origin_lat=req.origin_lat,
        destination_lon=req.destination_lon,
        destination_lat=req.destination_lat,
        horizon_minutes=req.horizon_minutes,
    )
    if not itin or not itin.segments:
        raise HTTPException(
            status_code=404,
            detail="Pas d'itinéraire trouvé. Vérifiez les coordonnées.",
        )

    return ItineraryResponse(
        origin_node=itin.origin_node,
        destination_node=itin.destination_node,
        horizon_minutes=itin.horizon_minutes,
        segments=[
            ItinerarySegmentResponse(
                channel_id=s.channel_id,
                length_m=s.length_m,
                speed_kmh=s.speed_kmh,
                duration_s=s.duration_s,
                start_lon=s.start_lon,
                start_lat=s.start_lat,
                end_lon=s.end_lon,
                end_lat=s.end_lat,
            )
            for s in itin.segments
        ],
        total_length_m=itin.total_length_m,
        total_duration_s=itin.total_duration_s,
        average_speed_kmh=itin.average_speed_kmh,
        total_duration_min=itin.total_duration_min,
        confiance=itin.confidence,
    )


@app.get("/api/v1/bottlenecks", response_model=list[BottleneckItem], tags=["bottlenecks"])
async def list_bottlenecks(limit: int = 10, api_key: None = Depends(verify_api_key)):
    """Top bottlenecks infrastructure (par retard bus)."""
    query = """
        SELECT id, segment_id, line_ref, diagnosis,
               bus_delay_seconds, traffic_speed_kmh,
               traffic_congestion, n_observations
        FROM gold.infrastructure_bottlenecks
        ORDER BY bus_delay_seconds DESC NULLS LAST
        LIMIT %s
    """
    rows = execute_query(query, (limit,))
    return [BottleneckItem(**r) for r in rows]


@app.post("/api/v1/rgpd/request", tags=["rgpd"])
async def rgpd_request(req: RgpdRequest):
    """Enregistre une demande RGPD (accès/suppression/portabilité/rectification).

    Endpoint public (pas d'auth) — c'est un droit utilisateur.
    """
    if req.request_type not in ("access", "deletion", "portability", "rectification"):
        raise HTTPException(status_code=400, detail="request_type invalide")

    request_id = log_data_subject_request(
        user_identifier=req.user_identifier,
        request_type=req.request_type,
        notes=req.notes,
    )
    log_audit(
        actor="user",
        action=f"rgpd_{req.request_type}_requested",
        details={"request_id": request_id, "user_hash_prefix": req.user_identifier[:8]},
    )
    return {
        "request_id": request_id,
        "status": "pending",
        "message": "Votre demande a été enregistrée. Délai légal : 30 jours.",
    }


# -----------------------------------------------------------------------------
# Auth endpoints (login pour Pro TCL / Élu)
# -----------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id: str
    persona_id: str
    username: str
    token: str  # placeholder — JWT à implémenter


@app.post("/api/v1/auth/login", response_model=LoginResponse, tags=["auth"])
async def login(req: LoginRequest, request: Request):
    """Login utilisateur (persona protégé)."""
    query = "SELECT user_id, persona_id, username, password_hash FROM gold.app_users WHERE username = %s AND is_active = TRUE"
    rows = execute_query(query, (req.username,))
    if not rows:
        log_audit(
            actor="user",
            action="login_failed",
            ip_address=request.client.host,
            details={"username": req.username},
        )
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    user = rows[0]
    if not bcrypt.checkpw(req.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        log_audit(
            actor="user",
            action="login_failed",
            ip_address=request.client.host,
            details={"username": req.username, "reason": "bad_password"},
        )
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    # TODO: générer JWT
    token = create_jwt(
        user_id=str(user["user_id"]),
        username=user["username"],
        persona_id=user["persona_id"],
    )
    log_audit(
        actor=req.username,
        action="login_success",
        ip_address=request.client.host,
        details={"persona": user["persona_id"]},
    )
    return LoginResponse(
        user_id=str(user["user_id"]),
        persona_id=user["persona_id"],
        username=user["username"],
        token=token,
    )
