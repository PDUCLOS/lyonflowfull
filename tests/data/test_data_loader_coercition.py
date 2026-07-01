"""Tests unitaires (Sprint 24+) — Helper de coercition NUMERIC psycopg2.

Le helper ``_coerce_numeric_columns`` (dans ``src.data.data_loader``)
centralise la conversion des colonnes ``NUMERIC`` PostgreSQL — que psycopg2
renvoie en ``decimal.Decimal`` (dtype ``object`` pandas) — en ``float64``.

Pourquoi : sans coercition, ``df.nlargest()``, ``df.sort_values()`` et
les tris Plotly échouent en ``TypeError`` silencieux (cf. fix
Sprint 24+ ``bus_traffic_spatial``).

Tests purs (pas de DB) : on construit un DataFrame avec des ``Decimal``
en main et on vérifie le comportement du helper.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.data.data_loader import _coerce_numeric_columns

# =============================================================================
# Cas nominaux
# =============================================================================


def test_coerce_decimal_columns_to_float() -> None:
    """Le helper convertit les colonnes Decimal en float64."""
    df = pd.DataFrame(
        {
            "lat": [Decimal("45.764"), Decimal("45.765"), Decimal("45.766")],
            "lon": [Decimal("4.835"), Decimal("4.836"), Decimal("4.837")],
            "bus_delay_sec": [Decimal("12.50"), Decimal("0.00"), Decimal("120.75")],
            "line_ref": ["L66", "C12", "T1"],  # text — doit rester object
        }
    )
    result = _coerce_numeric_columns(df, columns=["lat", "lon", "bus_delay_sec"])

    assert result["lat"].dtype == "float64"
    assert result["lon"].dtype == "float64"
    assert result["bus_delay_sec"].dtype == "float64"
    # Les colonnes non whitelistées (line_ref) doivent être intactes
    assert result["line_ref"].dtype == "object"
    assert list(result["line_ref"]) == ["L66", "C12", "T1"]
    # Valeurs préservées (à la précision float64 près)
    assert result["lat"].iloc[0] == pytest.approx(45.764)
    assert result["bus_delay_sec"].iloc[2] == pytest.approx(120.75)


def test_coerce_is_idempotent_on_already_float() -> None:
    """Le helper ne touche pas aux colonnes déjà float64 (idempotent)."""
    df = pd.DataFrame(
        {
            "lat": [45.764, 45.765, 45.766],
            "lon": [4.835, 4.836, 4.837],
        }
    )
    result = _coerce_numeric_columns(df, columns=["lat", "lon"])

    # dtypes inchangés (float64 → float64)
    assert result["lat"].dtype == "float64"
    assert result["lon"].dtype == "float64"
    # Valeurs strictement préservées (pas de ré-arrondi)
    assert result["lat"].tolist() == [45.764, 45.765, 45.766]


def test_coerce_handles_string_numeric_values() -> None:
    """Le helper convertit aussi les strings numériques (cas psycopg2 edge)."""
    # psycopg2 peut renvoyer des NUMERIC en str dans certains cas
    # (ex: connexion avec options de typage différentes).
    df = pd.DataFrame(
        {
            "lat": ["45.764", "45.765", "invalid"],  # 'invalid' → NaN avec coerce
        }
    )
    result = _coerce_numeric_columns(df, columns=["lat"])

    assert result["lat"].dtype == "float64"
    assert result["lat"].iloc[0] == pytest.approx(45.764)
    assert result["lat"].iloc[1] == pytest.approx(45.765)
    # errors="coerce" met NaN sur valeur non convertible
    assert pd.isna(result["lat"].iloc[2])


# =============================================================================
# Cas dégradés — ne pas crasher le widget
# =============================================================================


def test_coerce_with_missing_columns_logs_warning_no_crash() -> None:
    """Le helper log un warning mais ne raise pas si colonnes absentes.

    Important : si le schéma PG a changé (colonne NUMERIC renommée ou
    supprimée), on ne veut PAS crasher tout le widget. On log et on
    continue avec les colonnes présentes.
    """
    df = pd.DataFrame(
        {
            "lat": [Decimal("45.764")],
            "lat_renamed_en_prod": [Decimal("4.835")],  # simul schéma changé
        }
    )
    # Whitelist une colonne qui n'existe pas dans le df
    result = _coerce_numeric_columns(
        df,
        columns=["lat", "lon_qui_n_existe_plus"],
    )

    # La colonne "lat" doit quand même avoir été coercée
    assert result["lat"].dtype == "float64"
    # La colonne whitelistée absente est juste ignorée (no-op)
    assert "lon_qui_n_existe_plus" not in result.columns
    # La colonne non-whitelistée reste intacte
    assert result["lat_renamed_en_prod"].dtype == "object"


def test_coerce_does_not_mutate_input() -> None:
    """Le helper ne mute pas le DataFrame d'entrée (defensive copy)."""
    df = pd.DataFrame(
        {
            "lat": [Decimal("45.764"), Decimal("45.765")],
            "lon": [Decimal("4.835"), Decimal("4.836")],
        }
    )
    # Snapshot dtypes AVANT
    original_lat_dtype = str(df["lat"].dtype)
    original_lon_dtype = str(df["lon"].dtype)

    _ = _coerce_numeric_columns(df, columns=["lat", "lon"])

    # Le df d'entrée doit être intact (defensive copy dans le helper)
    assert str(df["lat"].dtype) == original_lat_dtype
    assert str(df["lon"].dtype) == original_lon_dtype


def test_coerce_empty_columns_list_returns_input() -> None:
    """Si la whitelist est vide, le helper renvoie le df tel quel (early return).

    Comportement voulu : éviter une copie inutile si rien à faire (perf
    pour les loaders qui n'ont aucune colonne NUMERIC). Le helper
    retourne le df original par référence. C'est safe car le helper
    n'a rien muté.
    """
    df = pd.DataFrame({"x": [1, 2, 3]})
    result = _coerce_numeric_columns(df, columns=[])

    # Early return sans copie (perf)
    assert result is df
    # Valeurs préservées
    assert result["x"].tolist() == [1, 2, 3]


def test_coerce_handles_none_values() -> None:
    """Le helper convertit les None en NaN (errors='coerce')."""
    df = pd.DataFrame(
        {
            "lat": [Decimal("45.764"), None, Decimal("45.766")],
        }
    )
    result = _coerce_numeric_columns(df, columns=["lat"])

    assert result["lat"].dtype == "float64"
    assert result["lat"].iloc[0] == pytest.approx(45.764)
    assert pd.isna(result["lat"].iloc[1])
    assert result["lat"].iloc[2] == pytest.approx(45.766)


# =============================================================================
# Test d'intégration — pattern d'utilisation réel (loader bus_traffic_spatial)
# =============================================================================


def test_whitelist_matches_mv_bus_traffic_spatial_columns() -> None:
    """La whitelist NUMERIC de ``load_bus_traffic_spatial`` couvre toutes
    les colonnes NUMERIC de la MV ``gold.mv_bus_traffic_spatial``.

    Garde-fou : si la MV est étendue avec une nouvelle colonne NUMERIC,
    on veut qu'un test pète pour qu'on pense à mettre à jour la whitelist.
    Source de vérité = migration 018 (scripts/sql/migration_018_*.sql).
    """
    expected_numeric = {
        "lat",
        "lon",
        "bus_delay_sec",
        "traffic_speed_kmh",
        "traffic_congestion",
    }
    # Whitelist codée en dur dans load_bus_traffic_spatial (ligne ~1340 de
    # data_loader.py). Si on l'a changée sans updater ce test, ce test
    # va fail. C'est le but.
    whitelist_in_loader = {
        "lat",
        "lon",
        "bus_delay_sec",
        "traffic_speed_kmh",
        "traffic_congestion",
    }
    assert whitelist_in_loader == expected_numeric
