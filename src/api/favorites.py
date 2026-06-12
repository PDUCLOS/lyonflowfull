"""FastAPI — Endpoints /api/favorites (favoris usager).

Sprint 10 (2026-06-12) — Remplace les MOCK_FAVORITES par de la donnée DB.
GET  /api/favorites        → liste des favoris
POST /api/favorites        → ajouter un favori
DELETE /api/favorites/{id} → supprimer
PATCH /api/favorites/{id}  → toggle alert_subscribed
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.main import verify_api_key
from src.db.connection import execute_query

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


# -----------------------------------------------------------------------------
# Pydantic models
# -----------------------------------------------------------------------------
class FavoriteItem(BaseModel):
    """Un favori usager."""

    id: str
    name: str
    origin: str
    destination: str
    usual_mode: str
    usual_duration_min: int
    alert_subscribed: bool
    created_at: str | None = None
    updated_at: str | None = None


class FavoriteCreate(BaseModel):
    """Payload pour créer un favori."""

    name: str = Field(..., min_length=1, max_length=255)
    origin: str = Field(..., min_length=1, max_length=255)
    destination: str = Field(..., min_length=1, max_length=255)
    usual_mode: str = Field(..., min_length=1, max_length=50)
    usual_duration_min: int = Field(..., ge=0, le=999)
    alert_subscribed: bool = False


class FavoriteToggleAlert(BaseModel):
    """Payload pour toggler alert_subscribed."""

    alert_subscribed: bool


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
# Hardcodé pour Sprint 10. Plus tard, viendra du JWT / session.
CURRENT_USER_ID = "default_user"


def _row_to_favorite(row: dict) -> FavoriteItem:
    """Convertit une row DB en FavoriteItem."""
    return FavoriteItem(
        id=str(row["id"]),
        name=str(row["name"]),
        origin=str(row["origin"]),
        destination=str(row["destination"]),
        usual_mode=str(row["usual_mode"]),
        usual_duration_min=int(row["usual_duration_min"]),
        alert_subscribed=bool(row["alert_subscribed"]),
        created_at=str(row.get("created_at")) if row.get("created_at") else None,
        updated_at=str(row.get("updated_at")) if row.get("updated_at") else None,
    )


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@router.get("", response_model=list[FavoriteItem], summary="Liste des favoris")
async def list_favorites(api_key: None = Depends(verify_api_key)) -> list[FavoriteItem]:
    """Retourne tous les favoris de l'utilisateur courant."""
    rows = execute_query(
        """
        SELECT id, name, origin, destination, usual_mode, usual_duration_min,
               alert_subscribed, created_at, updated_at
        FROM public.user_favorites
        WHERE user_id = %s
        ORDER BY created_at ASC
        """,
        (CURRENT_USER_ID,),
    )
    return [_row_to_favorite(r) for r in rows]


@router.post(
    "",
    response_model=FavoriteItem,
    status_code=status.HTTP_201_CREATED,
    summary="Ajouter un favori",
)
async def create_favorite(
    fav: FavoriteCreate,
    api_key: None = Depends(verify_api_key),
) -> FavoriteItem:
    """Crée un nouveau favori pour l'utilisateur courant."""
    fav_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    execute_query(
        """
        INSERT INTO public.user_favorites
            (user_id, id, name, origin, destination, usual_mode,
             usual_duration_min, alert_subscribed, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            CURRENT_USER_ID,
            fav_id,
            fav.name,
            fav.origin,
            fav.destination,
            fav.usual_mode,
            fav.usual_duration_min,
            fav.alert_subscribed,
            now,
            now,
        ),
    )
    rows = execute_query(
        """
        SELECT id, name, origin, destination, usual_mode, usual_duration_min,
               alert_subscribed, created_at, updated_at
        FROM public.user_favorites
        WHERE user_id = %s AND id = %s
        """,
        (CURRENT_USER_ID, fav_id),
    )
    if not rows:
        raise HTTPException(status_code=500, detail="Échec de l'insertion du favori")
    return _row_to_favorite(rows[0])


@router.delete(
    "/{fav_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un favori",
)
async def delete_favorite(
    fav_id: str,
    api_key: None = Depends(verify_api_key),
) -> None:
    """Supprime un favori par son ID."""
    result = execute_query(
        """
        DELETE FROM public.user_favorites
        WHERE user_id = %s AND id = %s
        RETURNING id
        """,
        (CURRENT_USER_ID, fav_id),
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Favori {fav_id} non trouvé",
        )


@router.patch(
    "/{fav_id}/alert",
    response_model=FavoriteItem,
    summary="Toggle alert_subscribed",
)
async def toggle_alert(
    fav_id: str,
    payload: FavoriteToggleAlert,
    api_key: None = Depends(verify_api_key),
) -> FavoriteItem:
    """Active ou désactive les alertes pour un favori."""
    now = datetime.now(UTC)
    result = execute_query(
        """
        UPDATE public.user_favorites
        SET alert_subscribed = %s, updated_at = %s
        WHERE user_id = %s AND id = %s
        RETURNING id, name, origin, destination, usual_mode,
                  usual_duration_min, alert_subscribed, created_at, updated_at
        """,
        (payload.alert_subscribed, now, CURRENT_USER_ID, fav_id),
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Favori {fav_id} non trouvé",
        )
    return _row_to_favorite(result[0])


# -----------------------------------------------------------------------------
# Recommandation multimodale (Sprint 10)
# -----------------------------------------------------------------------------
from src.routing.recommendation import get_alternatives  # noqa: E402


class AlternativeItem(BaseModel):
    mode: str
    mode_label: str
    mode_icon: str
    temps_min: int
    score_confiance: float
    raison: str


@router.get(
    "/{fav_id}/alternatives",
    response_model=list[AlternativeItem],
    summary="Alternatives multimodales pour un favori",
)
async def get_favorite_alternatives(
    fav_id: str,
    api_key: None = Depends(verify_api_key),
) -> list[AlternativeItem]:
    """Retourne des alternatives multimodales pour un trajet favori.

    Basé sur silver.velov_clean (stations dispo) et
    silver.trafic_boucles_clean (temps réels) via les règles métier
    de src.routing.recommendation.get_alternatives().
    """
    # Récupérer le favori
    rows = execute_query(
        """
        SELECT id, name, origin, destination, usual_mode, usual_duration_min
        FROM public.user_favorites
        WHERE user_id = %s AND id = %s
        """,
        (CURRENT_USER_ID, fav_id),
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Favori {fav_id} non trouvé",
        )

    fav = dict(rows[0])
    # Coordinates par défaut (snap depuis les noms origin/dest)
    # Pour Sprint 10, on utilise des coords par défaut réalistes
    # basées sur les noms des lieux.
    # TODO Sprint 11 : géocodage des noms origin/destination
    fav["origin_lat"] = 45.7600
    fav["origin_lon"] = 4.8500
    fav["dest_lat"] = 45.7640
    fav["dest_lon"] = 4.8350

    alternatives = get_alternatives(fav)
    return [AlternativeItem(**alt) for alt in alternatives]
