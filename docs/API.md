# LyonFlowFull — API Reference

Documentation complète de l'API REST. Générée aussi automatiquement par
FastAPI à `/docs` (Swagger UI) et `/redoc`.

## Base URL

```
http://localhost/api/v1
```

En production : `https://lyonflow.example.com/api/v1`

## Authentification

Header requis : `X-API-Key: <LYONFLOW_API_KEY>`

Endpoints publics (pas d'auth) :
- `GET /health`
- `POST /api/v1/rgpd/request`
- `POST /api/v1/auth/login`

## Endpoints

### `GET /health` — Health check

```bash
curl http://localhost/api/health
```

Réponse 200 :
```json
{
  "status": "ok",
  "version": "0.1.0",
  "db": true,
  "timestamp": "2026-06-06T15:30:00"
}
```

### `POST /api/v1/auth/login` — Login Pro TCL / Élu

```bash
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "pro_tcl", "password": "***"}'
```

Réponse 200 :
```json
{
  "user_id": "uuid-here",
  "persona_id": "pro_tcl",
  "username": "pro_tcl",
  "token": "<JWT_TOKEN_RETORNE_PAR_LOGIN>"
}
```

Token JWT valide 24h. À passer en `Authorization: Bearer <token>`.

### `GET /api/v1/models` — Liste modèles MLflow

```bash
curl http://localhost/api/v1/models \
  -H "X-API-Key: $LYONFLOW_API_KEY"
```

Réponse 200 :
```json
{
  "models": [
    {"name": "xgboost_speed", "version": "1.2.0", "stage": "Production",
     "metrics": {"mae": 1.96, "r2": 0.947}},
    ...
  ]
}
```

### `POST /api/v1/predict/traffic` — Prédiction vitesse

```bash
curl -X POST http://localhost/api/v1/predict/traffic \
  -H "X-API-Key: $LYONFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"node_idx": 42, "horizon_minutes": 30}'
```

Body :
- `node_idx` (int) : index du nœud
- `horizon_minutes` (int, default 30) : 5, 30, 60, 180, 360
- `measurement_time` (datetime, optional) : défaut = now

Réponse 200 :
```json
{
  "node_idx": 42,
  "horizon_minutes": 30,
  "predicted_speed_kmh": 28.4,
  "confidence_low": 24.0,
  "confidence_high": 32.0,
  "model_name": "xgboost_speed",
  "model_version": "1.2.0",
  "prediction_timestamp": "2026-06-06T15:30:00"
}
```

### `POST /api/v1/predict/velov` — Prédiction Vélov

```bash
curl -X POST http://localhost/api/v1/predict/velov \
  -H "X-API-Key: $LYONFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"station_id": "1001", "horizon_minutes": 30}'
```

Body :
- `station_id` (str) : ID station
- `horizon_minutes` (int, default 30) : 30, 60, 180

Réponse 200 :
```json
{
  "station_id": "1001",
  "horizon_minutes": 30,
  "predicted_bikes": 8.0,
  "actual_bikes": null,
  "model_name": "xgboost_velov",
  "prediction_timestamp": "2026-06-06T15:30:00"
}
```

### `POST /api/v1/recommend` — Recommandation trajet

```bash
curl -X POST http://localhost/api/v1/recommend \
  -H "X-API-Key: $LYONFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "Villeurbanne",
    "destination": "Part-Dieu",
    "departure_time": null,
    "modes_allowed": ["transit", "bike", "walk"]
  }'
```

Body :
- `origin` (str) : adresse ou arrêt
- `destination` (str) : adresse ou arrêt
- `departure_time` (datetime, optional) : défaut = now
- `modes_allowed` (list) : transit, bike, walk, car

Réponse 200 :
```json
{
  "options": [
    {"mode": "transit", "mode_label": "Métro A", "duration_min": 18,
     "cost_eur": 1.90, "co2_g": 30, "confidence_pct": 78},
    {"mode": "bike", "mode_label": "Vélov", ...}
  ],
  "recommended": {...},
  "score_breakdown": {"time": 0.5, "cost": 0.3, "eco": 0.2}
}
```

### `GET /api/v1/bottlenecks` — Top bottlenecks

```bash
curl "http://localhost/api/v1/bottlenecks?limit=10" \
  -H "X-API-Key: $LYONFLOW_API_KEY"
```

Query params :
- `limit` (int, default 10) : nombre de bottlenecks

Réponse 200 : liste de BottleneckItem
```json
[
  {
    "bottleneck_id": 1,
    "segment_id": "...",
    "line_refs": ["T1", "C3", "C13"],
    "diagnosis": "infra",
    "impact_score": 8.5,
    "voyageurs_jour": 120000
  }
]
```

### `POST /api/v1/rgpd/request` — Data Subject Request

**Endpoint public** (droit utilisateur).

```bash
curl -X POST http://localhost/api/v1/rgpd/request \
  -H "Content-Type: application/json" \
  -d '{
    "user_identifier": "sha256-hash-of-something",
    "request_type": "access",
    "notes": "Optional"
  }'
```

Body :
- `user_identifier` (str) : identifiant hashé
- `request_type` (str) : `access` | `deletion` | `portability` | `rectification`
- `notes` (str, optional)

Réponse 200 :
```json
{
  "request_id": "uuid",
  "status": "pending",
  "message": "Votre demande a été enregistrée. Délai légal : 30 jours."
}
```

## Erreurs

Codes HTTP standard :
- `400` : requête invalide
- `401` : API key manquante ou invalide
- `403` : accès refusé
- `404` : ressource non trouvée
- `429` : rate limit dépassé (Retry-After header)
- `500` : erreur serveur
- `503` : service indisponible

Format :
```json
{
  "detail": "Description de l'erreur"
}
```

## Rate limits

| Endpoint | Limite |
|----------|--------|
| `/api/*` | 10 req/s par IP (burst 20) |
| `/api/v1/auth/login` | 5 req/min par IP (anti brute force) |
| `/api/v1/rgpd/*` | 3 req/h par IP (anti spam) |

## Exemples clients

### Python

```python
import httpx

API_BASE = "http://localhost/api/v1"
API_KEY = "your-api-key"

with httpx.Client(base_url=API_BASE, headers={"X-API-Key": API_KEY}) as client:
    # Prédiction
    r = client.post("/predict/traffic", json={"node_idx": 42, "horizon_minutes": 30})
    print(r.json())

    # Recommandation
    r = client.post("/recommend", json={
        "origin": "Villeurbanne",
        "destination": "Part-Dieu"
    })
    print(r.json())
```

### cURL

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"pro_tcl","password":"***"}' | jq -r .token)

# Utilisation
curl http://localhost/api/v1/models \
  -H "Authorization: Bearer $TOKEN"
```

### JavaScript

```javascript
const API_KEY = "your-api-key";
const response = await fetch("http://localhost/api/v1/predict/traffic", {
  method: "POST",
  headers: {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ node_idx: 42, horizon_minutes: 30 })
});
const data = await response.json();
```
