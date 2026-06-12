"""Couche de chargement "intelligent" pour les widgets dashboard.

Cette couche abstrait le binding widgets ↔ DB. Les widgets appellent
``load_traffic()``, ``load_velov()``, etc. sans savoir si la donnée vient
de la DB Gold/Silver ou des mocks ``src.data.mock``.

Pattern d'utilisation dans un widget::

    from src.data.data_loader import load_traffic, load_velov
    from src.data.exceptions import DashboardDataError

    def render_X_widget(data=None):
        if data is None:
            try:
                data = load_traffic()  # DB (mode prod) ou mock (mode démo)
            except DashboardDataError as e:
                st.error(f"⚠️ Données pipeline indisponibles : {e.source}")
                return
        # ... reste du widget inchangé

Modes (Sprint VPS-6, 2026-06-11) :

* **Mode prod** (``LYONFLOW_DEMO_MODE=0`` ou absent, **défaut sur VPS**) :
  aucune donnée mock n'est jamais servie. Si la DB ne répond pas, la
  fonction lève ``DashboardDataError``. Le widget appelant catch et
  affiche ``st.error``. Le paramètre ``force_mock=True`` est IGNORÉ.
* **Mode démo** (``LYONFLOW_DEMO_MODE=1``, dev local uniquement) :
  comportement historique préservé. ``force_mock=True`` OU DB down
  → fallback mock transparent.

Avantages :

* **Un seul point de changement** — pour brancher un widget sur la DB,
  il suffit d'ajouter une fonction ici, pas de toucher au widget.
* **Fail loud en prod** — si la DB a un blip, le widget devient rouge
  immédiatement. Prometheus (Sprint VPS-3) alerte avant les users.
* **Démo opt-in** — le dev local peut mocker la DB via ``LYONFLOW_DEMO_MODE=1``
  pour développer ou faire des screenshots.
* **Testable** — les tests monkeypatchent ``_is_db_available`` et
  ``_is_demo_mode``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from src.data.db_query import (
    _is_db_available,
    get_infrastructure_bottlenecks,
    get_latest_traffic,
    get_predictions_vs_actuals,
    get_rgpd_audit_log,
    get_rgpd_consents_summary,
    get_traffic_bottlenecks,
    get_traffic_predictions,
    get_velov_predictions,
    get_velov_stations_geo,
)
from src.data.exceptions import DashboardDataError
from src.data.mock import elu as elu_mock
from src.data.mock import pro_tcl as pro_tcl_mock
from src.data.mock import usager as usager_mock
from src.db.connection import execute_query

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Mode démo (Sprint VPS-6, 2026-06-11)
# -----------------------------------------------------------------------------
# Variable d'env : LYONFLOW_DEMO_MODE
#   "1" → mode démo : fallback mock transparent si DB indisponible (dev local,
#          screenshots, démos Jedha). Comportement historique préservé.
#   "0" (ou absent) → mode production : aucune donnée mock, lève
#                      DashboardDataError si la DB ne répond pas.
# Sur le VPS, .env fixe LYONFLOW_DEMO_MODE=0 et check-deploy-env.sh valide
# la présence de cette variable avant chaque déploiement.
def _is_demo_mode() -> bool:
    """Lit LYONFLOW_DEMO_MODE au boot. Cache process (immuable par session)."""
    global _demo_mode_cache
    if _demo_mode_cache is None:
        val = os.getenv("LYONFLOW_DEMO_MODE", "0").strip()
        _demo_mode_cache = val == "1"
        logger.info(
            "Dashboard data_loader initialisé en mode %s (LYONFLOW_DEMO_MODE=%s)",
            "DÉMO" if _demo_mode_cache else "PRODUCTION",
            val,
        )
    return _demo_mode_cache


_demo_mode_cache: bool | None = None


def _maybe_force_mock(force_mock: bool) -> bool:
    """Retourne True si on doit utiliser le mock.

    Logique (Sprint VPS-6) :

    * **Mode démo** (``LYONFLOW_DEMO_MODE=1``) : force_mock=True OU DB down
      → utilise le mock. Comportement historique préservé pour le dev local.
    * **Mode prod** (``LYONFLOW_DEMO_MODE=0`` ou absent, défaut sur VPS) :
      ``force_mock=True`` est IGNORÉ. Si la DB ne répond pas, la fonction
      appelante doit lever ``DashboardDataError`` au lieu de servir un mock.

    Returns:
        True si un mock doit être servi. False si la fonction doit lire la DB
        (et lever ``DashboardDataError`` si elle échoue).
    """
    if _is_demo_mode():
        if force_mock:
            return True
        return not _is_db_available()
    # Mode prod : force_mock est ignoré (pas de mock sur le VPS).
    # Si DB down, la fonction appelante lèvera DashboardDataError.
    return False


def _require_db_or_raise(source: str) -> None:
    """Vérifie que la DB est dispo, sinon lève ``DashboardDataError``.

    Helper pour les fonctions du data_loader : à appeler en début de fonction
    après ``_maybe_force_mock`` a retourné False. Garantit le comportement
    fail loud en mode prod.
    """
    if not _is_db_available():
        raise DashboardDataError(
            source=source,
            detail="PostgreSQL ne répond pas. Vérifier POSTGRES_HOST/PORT/PASSWORD et docker compose ps postgres",
        )


def _approx_lonlat_from_channel_id(channel_id: Any) -> tuple[float, float]:
    """Position approximative (lat, lon) dérivée déterministe du channel_id.

    Contexte (Sprint VPS-5 + dette schéma v0.3.1) :
        ``get_traffic_bottlenecks()`` ne ramène plus ``node_idx`` ni lat/lon.
        Le mapping ``channel_id`` (str 'LYO00xxx') ↔ ``properties_twgid``
        (int) est cassé côté DB (cf. AGENTS.md). On dérive donc une
        pseudo-position dans la bounding box de Lyon à partir d'un hash
        stable, pour que les markers sur la carte soient distincts et
        reproductibles.

    Bounding box Lyon (approx) : lat 45.72-45.81, lon 4.81-4.90.
    """
    base_lat, base_lon = 45.72, 4.81
    span_lat, span_lon = 0.09, 0.09
    if channel_id is None or (isinstance(channel_id, float) and pd.isna(channel_id)):
        return base_lat + span_lat / 2, base_lon + span_lon / 2
    key = str(channel_id)
    h = abs(hash(key))
    return (
        base_lat + ((h % 1000) / 1000.0) * span_lat,
        base_lon + (((h // 1000) % 1000) / 1000.0) * span_lon,
    )


# =============================================================================
# Trafic routier
# =============================================================================


def load_traffic(force_mock: bool = False) -> dict[str, Any]:
    """Résumé trafic routier (vitesse moyenne, congestion, top jams).

    Returns:
        Dict compatible avec le format historique ``MOCK_TRAFFIC``::

            {
                "city": "Lyon",
                "timestamp": "...",
                "average_speed_kmh": ...,
                "congestion_level": "fluide|modéré|dense|bloqué",
                "congestion_color": "#...",
                "bottlenecks_count": N,
                "main_jams": [{road, lat, lon, speed_kmh, delay_min, severity}],
                "predictions": {h_plus_30min, h_plus_1h, h_plus_3h}
            }

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas ou si
            la table ``gold.traffic_features_live`` est vide (aucun capteur
            n'a remonté de données).
    """
    if _maybe_force_mock(force_mock):
        return usager_mock.MOCK_TRAFFIC

    _require_db_or_raise("traffic_features_live")
    df = get_latest_traffic(limit=1000)
    if df.empty:
        # DB répond mais vide : en mode démo on tolère (fallback mock),
        # en prod on signale explicitement.
        if _is_demo_mode():
            logger.warning("gold.traffic_features_live vide — fallback mock (mode démo)")
            return usager_mock.MOCK_TRAFFIC
        raise DashboardDataError(
            source="gold.traffic_features_live",
            detail="Table vide — aucun capteur trafic n'a remonté de données. "
            "Vérifier que le DAG collect_bronze s'exécute (Airflow UI)",
        )

    # Ne considérer que les voies en ville (vitesse limite <= 50) pour une moyenne réaliste
    city_df = df[df["vitesse_limite_kmh"] <= 50]
    avg_speed = float(city_df["speed_kmh"].mean()) if not city_df.empty else float(df["speed_kmh"].mean())
    bottlenecks_df = get_traffic_bottlenecks(top=10)
    n_bottlenecks = len(bottlenecks_df)

    # Mapping vitesse → niveau de congestion
    if avg_speed >= 35:
        level, color = "fluide", "#4CAF50"
    elif avg_speed >= 25:
        level, color = "modéré", "#FF9800"
    elif avg_speed >= 15:
        level, color = "dense", "#F44336"
    else:
        level, color = "bloqué", "#B71C1C"

    # Top 4 jams depuis bottlenecks
    main_jams = []
    for _, row in bottlenecks_df.head(4).iterrows():
        speed_val = float(row.get("avg_speed") or 0.0) if not pd.isna(row.get("avg_speed")) else 0.0
        lat_jam, lon_jam = _approx_lonlat_from_channel_id(row.get("channel_id"))
        main_jams.append(
            {
                "road": f"Channel {row['channel_id']}",
                "lat": lat_jam,
                "lon": lon_jam,
                "speed_kmh": speed_val,
                "delay_min": max(0, int((30 - speed_val) / 5)),
                "severity": "high" if speed_val < 15 else "medium" if speed_val < 25 else "low",
            }
        )

    # Prédictions
    predictions: dict[str, dict] = {"h_plus_30min": {}, "h_plus_1h": {}, "h_plus_3h": {}}
    for horizon, key in [(30, "h_plus_30min"), (60, "h_plus_1h"), (180, "h_plus_3h")]:
        pred_df = get_traffic_predictions(horizon_minutes=horizon, limit=200)
        # Nouveau schéma : speed_pred (alias predicted_speed posé par db_query)
        speed_col = "predicted_speed" if "predicted_speed" in pred_df.columns else "speed_pred"
        if not pred_df.empty and speed_col in pred_df.columns:
            mean_pred = float(pred_df[speed_col].mean())
            if mean_pred >= 35:
                pred_level = "fluide"
            elif mean_pred >= 25:
                pred_level = "modéré"
            elif mean_pred >= 15:
                pred_level = "dense"
            else:
                pred_level = "bloqué"
            predictions[key] = {"average_speed_kmh": round(mean_pred, 1), "congestion_level": pred_level}

    # Pas de fallback mock en prod. Si une fenêtre de prédiction est absente,
    # on laisse le dict vide — le widget affichera "—" pour cette fenêtre.
    # C'est le comportement attendu si dag_live_speed_retrain (Sprint VPS-5)
    # n'a pas encore tourné pour certains horizons.

    return {
        "city": "Lyon",
        "timestamp": str(pd.Timestamp.now(tz="UTC")),
        "average_speed_kmh": round(avg_speed, 1),
        "congestion_level": level,
        "congestion_color": color,
        "bottlenecks_count": n_bottlenecks,
        "main_jams": main_jams,
        "predictions": predictions,
        "data_source": "db_gold",
    }


def load_traffic_timeseries(node_idx: int, hours: int = 4, force_mock: bool = False) -> pd.DataFrame:
    """Série temporelle trafic pour un nœud donné.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
            Retourne un DataFrame vide si la DB répond mais n'a pas de série
            pour ce nœud (cas légitime, widget affichera un message vide).
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_TRAFFIC_TIMESERIES)
    # Si DB dispo, query (alias de get_traffic_for_node)
    from src.data.db_query import get_traffic_for_node

    _require_db_or_raise("fact_traffic_series")
    return get_traffic_for_node(node_idx=node_idx, hours=hours)


# =============================================================================
# Vélov
# =============================================================================


def load_velov_stations(force_mock: bool = False) -> list[dict]:
    """Stations Vélov proches avec dispo actuelle.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return usager_mock.VELOV_STATIONS

    _require_db_or_raise("velov_features")
    df = get_velov_stations_geo()
    if df.empty:
        # DB répond mais vide : situation légitime
        return []

    return [
        {
            "id": int(row.get("station_id", i)),
            "name": row.get("station_name", f"Station {i}"),
            "lat": float(row.get("lat") or 0.0) if not pd.isna(row.get("lat")) else 0.0,
            "lon": float(row.get("lng") or 0.0) if not pd.isna(row.get("lng")) else 0.0,
            "bikes_available": int(row.get("bikes_available", 0)),
            "stands_available": int(row.get("docks_available", 0)),
            "distance_m": 0,
            "is_operational": bool(row.get("is_operational", True)),
        }
        for i, row in df.iterrows()
    ]


def load_velov_predictions(horizon_minutes: int = 30, force_mock: bool = False) -> pd.DataFrame:
    """Prédictions disponibilité Vélov.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame([p for p in usager_mock.MOCK_VELOV_PREDICTIONS if p["horizon_minutes"] == horizon_minutes])
    _require_db_or_raise("velov_predictions")
    return get_velov_predictions(horizon_minutes=horizon_minutes, limit=200)


# =============================================================================
# =============================================================================
# Favoris usager (Sprint 10)
# =============================================================================


def load_favorites(force_mock: bool = False) -> list[dict]:
    """Favoris usager (itinéraires sauvegardés).

    Mode prod : lit ``public.user_favorites``.
    Mode démo (``LYONFLOW_DEMO_MODE=1``) OU DB down :
        retourne ``usager_mock.MOCK_FAVORITES`` (fallback transparent).

    Returns:
        Liste de dicts au format historique MOCK_FAVORITES
        (incluant next_departure absent en DB, laissé à None).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _is_demo_mode():
        return usager_mock.MOCK_FAVORITES

    _require_db_or_raise("public.user_favorites")
    rows = execute_query(
        """
        SELECT id, name, origin, destination, usual_mode,
               usual_duration_min, alert_subscribed
        FROM public.user_favorites
        WHERE user_id = 'default_user'
        ORDER BY created_at ASC
        """
    )
    if not rows:
        # DB répond mais vide : fallback mock pour ne pas casser le dashboard.
        logger.warning("user_favorites vide — fallback mock (mode démo implicite)")
        return usager_mock.MOCK_FAVORITES

    return [
        {
            "id": str(r["id"]),
            "name": str(r["name"]),
            "origin": str(r["origin"]),
            "destination": str(r["destination"]),
            "usual_mode": str(r["usual_mode"]),
            "usual_duration_min": int(r["usual_duration_min"]),
            "next_departure": None,  # non stocké en DB
            "alert_subscribed": bool(r["alert_subscribed"]),
        }
        for r in rows
    ]


# Bus & infrastructure
# =============================================================================


def load_bus_delays(line_ref: str | None = None, days: int = 7, force_mock: bool = False) -> pd.DataFrame:
    """Retards bus agrégés.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        df = pd.DataFrame(usager_mock.MOCK_BUS_DELAYS)
        if line_ref:
            df = df[df["line_ref"] == line_ref]
        return df
    from src.data.db_query import get_bus_delay_segments

    _require_db_or_raise("bus_delay_segments")
    return get_bus_delay_segments(line_ref=line_ref, days=days)


def load_infra_bottlenecks(top: int = 15, force_mock: bool = False) -> pd.DataFrame:
    """Bottlenecks infrastructure avec diagnostic.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_INFRA_BOTTLENECKS[:top])
    _require_db_or_raise("infrastructure_bottlenecks")
    return get_infrastructure_bottlenecks(top=top)


# =============================================================================
# Prédictions & monitoring
# =============================================================================


def load_predictions_vs_actuals(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Backtesting prédictions vs réalité.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_PREDICTIONS_VS_ACTUALS[:limit])
    _require_db_or_raise("predictions_vs_actuals")
    return get_predictions_vs_actuals(limit=limit)


def load_rgpd_audit(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Logs d'audit RGPD.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_RGPD_AUDIT[:limit])
    _require_db_or_raise("rgpd.audit_log")
    return get_rgpd_audit_log(limit=limit)


def load_rgpd_consents(force_mock: bool = False) -> pd.DataFrame:
    """Summary des consents RGPD.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_RGPD_CONSENTS_SUMMARY)
    _require_db_or_raise("rgpd.consents")
    return get_rgpd_consents_summary()


# =============================================================================
# Pro TCL (mock-only pour l'instant — ces KPIs sont des agrégats calculés)
# =============================================================================


def load_line_kpis(line_ids: list[str] | None = None, force_mock: bool = False) -> dict:
    """KPIs par ligne (OTP, retard, fréquence, charge).

    Mode prod (Sprint VPS-6+) : la source unique est la vue matérialisée
    ``gold.mv_line_kpis_live`` (créée Sprint 10). Si la vue n'existe pas
    encore ou si la DB est down, lève ``DashboardDataError``.

    Mode démo (``LYONFLOW_DEMO_MODE=1``) : fallback mock pro_tcl.LINE_KPIS.

    Raises:
        DashboardDataError: en mode prod, si la vue Gold n'est pas peuplée
            ou si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pro_tcl_mock.LINE_KPIS
    if _is_demo_mode():
        return pro_tcl_mock.LINE_KPIS
    from src.data.db_query import get_line_kpis

    _require_db_or_raise("mv_line_kpis_live")
    return get_line_kpis(line_ids=line_ids)


def load_otp_heatmap_data(force_mock: bool = False) -> pd.DataFrame:
    """Données heatmap OTP (ligne × heure).

    Mode prod : lit la vue Gold ``gold.mv_otp_heatmap`` (Sprint 10).
    Mode démo : aplatit le mock ``OTP_GRID`` en DataFrame ``[line_id, date, hour, otp_pct]``.

    Raises:
        DashboardDataError: en mode prod, si la DB ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        grid = pro_tcl_mock.OTP_GRID
        rows = []
        for line_id, by_date in grid.items():
            for date_str, hourly in by_date.items():
                for hour, otp in enumerate(hourly):
                    rows.append({"line_id": line_id, "date": date_str, "hour": hour, "otp_pct": float(otp)})
        return pd.DataFrame(rows)
    from src.data.db_query import get_otp_heatmap

    _require_db_or_raise("mv_otp_heatmap")
    return get_otp_heatmap()


# =============================================================================
# Élu (mock-only — agrégats ville)
# =============================================================================


def load_city_synthesis(force_mock: bool = False) -> dict:
    """Indicateurs de synthèse ville (vélov, traffic, bus, météo).

    Mode prod : agrégat multi-tables calculé en SQL (vue ``gold.v_city_synthesis``).
    Sprint 10+ — en attendant, lève ``DashboardDataError``.

    Raises:
        DashboardDataError: en mode prod, car la vue n'est pas encore implémentée.
    """
    if _maybe_force_mock(force_mock):
        return elu_mock.SYNTHESIS_DATA
    if _is_demo_mode():
        return elu_mock.SYNTHESIS_DATA
    raise DashboardDataError(
        source="gold.v_city_synthesis",
        detail="Vue matérialisée non créée. Sprint 10+ : créer gold.v_city_synthesis "
        "puis rebrancher cette fonction sur la vue.",
    )


def load_bottlenecks_summary(force_mock: bool = False) -> pd.DataFrame:
    """Résumé bottlenecks pour page Élu.

    Mode prod : lit ``gold.infrastructure_bottlenecks`` agrégé.
    Mode démo : retourne le mock ``BOTTLENECKS_LIST``.

    Raises:
        DashboardDataError: en mode prod, si la DB ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(elu_mock.BOTTLENECKS_LIST)
    if _is_demo_mode():
        return pd.DataFrame(elu_mock.BOTTLENECKS_LIST)
    from src.data.db_query import get_bottlenecks_summary

    _require_db_or_raise("infrastructure_bottlenecks")
    return get_bottlenecks_summary()


# =============================================================================
# Météo, alertes, segments, buses, kpis, amenagements (Sprint 8)
# =============================================================================


def load_weather_hourly(hours: int = 24, force_mock: bool = False) -> pd.DataFrame:
    """Météo horaire pour le widget météo.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_WEATHER_HOURLY)
    from src.data.db_query import get_weather_hourly

    _require_db_or_raise("silver.meteo_hourly")
    return get_weather_hourly(hours=hours)


def load_recent_alerts(hours: int = 24, limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Alertes récentes (predictions + events).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_RECENT_ALERTS[:limit])
    from src.data.db_query import get_recent_alerts

    _require_db_or_raise("gold.alerts")
    return get_recent_alerts(hours=hours, limit=limit)


def load_segments(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Liste des segments routiers.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_SEGMENTS[:limit])
    from src.data.db_query import get_segments

    _require_db_or_raise("gold.segments")
    return get_segments(limit=limit)


def load_correlation_matrix(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Matrice de corrélation features Gold.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_CORRELATION_MATRIX[:limit])
    from src.data.db_query import get_correlation_matrix

    _require_db_or_raise("gold.correlation_matrix")
    return get_correlation_matrix(limit=limit)


def load_buses_positions(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Positions temps réel des bus TCL.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_BUSES_POSITIONS[:limit])
    from src.data.db_query import get_buses_positions

    _require_db_or_raise("tcl_vehicles_clean")
    return get_buses_positions(limit=limit)


def load_kpis_12_months(force_mock: bool = False) -> pd.DataFrame:
    """KPIs ville 12 mois (vue matérialisée Gold) — format plat DataFrame.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(elu_mock.MOCK_KPIS_12_MONTHS_FLAT)
    from src.data.db_query import get_kpis_12_months

    _require_db_or_raise("gold.kpis_12_months")
    return get_kpis_12_months()


def _derive_label_unit(kpi_key: str) -> tuple[str, str]:
    """Dérive (label, unit) depuis le kpi_key — fallback générique."""
    known = {
        "part_modale_tc": ("Part modale TC", "%"),
        "ponctualite": ("Ponctualité", "%"),
        "co2_evite_tonnes": ("CO₂ évité", "t"),
        "bottlenecks_actifs": ("Bottlenecks", ""),
        "satisfaction_pct": ("Satisfaction", "%"),
        "total_trips": ("Trajets totaux", ""),
        "avg_speed_kmh": ("Vitesse moy.", "km/h"),
        "prediction_accuracy": ("Précision préd.", "%"),
        "congestion_index": ("Indice congestion", ""),
    }
    return known.get(kpi_key, (kpi_key.replace("_", " ").title(), ""))


def load_elu_kpis_dict(force_mock: bool = False) -> dict:
    """KPIs 12 mois au format dict attendu par les widgets Élu.

    Reconstitue le format ``{kpi_key: {current, delta_ytd, target_2026, history, ...}}``
    depuis le DataFrame plat. Le kpi_key est libre — label/unit sont déduits
    de la clé via ``_derive_label_unit()``.

    Returns:
        Dict avec les KPIs trouvés dans la MV (ou mock). Si la MV est vide,
        retourne un dict avec les 5 KPIs standards à zéro.
    """
    df = load_kpis_12_months(force_mock=force_mock)

    # Fallback si MV absente ou vide
    if df.empty:
        return {
            k: {"label": l, "current": 0, "unit": u, "delta_ytd": 0, "target_2026": 0, "history": []}
            for k, (l, u) in [  # noqa: E741
                ("part_modale_tc", ("Part modale TC", "%")),
                ("ponctualite", ("Ponctualité", "%")),
                ("co2_evite_tonnes", ("CO₂ évité", "t")),
                ("bottlenecks_actifs", ("Bottlenecks", "")),
                ("satisfaction_pct", ("Satisfaction", "%")),
            ]
        }

    kpis = {}
    for kpi_key in df["kpi_key"].unique():
        sub = df[df["kpi_key"] == kpi_key].sort_values("month")
        values = sub["value"].tolist()
        target = float(sub["target_value"].iloc[0]) if not sub.empty else 0
        label, unit = _derive_label_unit(kpi_key)
        current = values[-1] if values else 0
        delta_ytd = float(current - values[0]) if len(values) > 1 else 0.0
        kpis[kpi_key] = {
            "label": label,
            "current": current,
            "unit": unit,
            "delta_ytd": delta_ytd,
            "target_2026": target,
            "history": values,
        }
    return kpis


def load_bottlenecks_top(force_mock: bool = False) -> list[dict]:
    """Liste des 10 bottlenecks Élu (format dict avec rank, zone, voyageurs, etc.).

    Reconstruit le format ``BOTTLENECKS_TOP_10`` mock depuis le DataFrame
    ``load_bottlenecks_summary``.
    """
    # En attendant la vraie table gold.bottlenecks_summary_agg, on utilise
    # les données de load_bottlenecks_summary (MOCK_INFRA_BOTTLENECKS)
    from src.data.data_loader import load_bottlenecks_summary

    df = load_bottlenecks_summary(force_mock=force_mock)
    if df.empty:
        return []

    bottlenecks = []
    for i, row in df.head(10).iterrows():
        bottlenecks.append(
            {
                "rank": int(row.get("bottleneck_id", i + 1)),
                "zone": row.get("road_name", "—"),
                "lines_impacted": ["C3", "C13"],  # approximation mock
                "voyageurs_jour": int(row.get("voyageurs_jour", 5000 + i * 1000)),
                "gain_min": 5 + i,
                "cout_M_euros": round(2.5 - i * 0.15, 2),
                "roi_mois": 18 + i * 3,
                "delai_mois": 6 + i * 2,
                "description": f"Amélioration #{i + 1} du bottleneck {row.get('road_name', '—')}",
            }
        )
    return bottlenecks


def load_amenagements_passes(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Aménagements passés (historique persona Élu).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(elu_mock.MOCK_AMENAGEMENTS_FLAT[:limit])
    from src.data.db_query import get_amenagements_passes

    _require_db_or_raise("gold.amenagements")
    return get_amenagements_passes(limit=limit)


def load_tcl_lines(force_mock: bool = False) -> list[dict]:
    """Liste exhaustive des lignes TCL.

    Sprint VPS-5 — Charge TOUTES les lignes distinctes présentes en DB
    (gold.tcl_vehicle_realtime.line_ref — ~166 lignes historiques TCL)
    plutôt que les 12 lignes du mock. Catégorisation automatique :
    * ``T*`` (T1, T2, T3...) → tram
    * ``M*`` (M_A, M_B, M_C, M_D) → metro
    * reste → bus

    Args:
        force_mock: True pour bypasser la DB et utiliser MOCK_TCL_LINES.

    Returns:
        Liste de dicts {id, name, mode, color, icon} triés par mode puis id.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pro_tcl_mock.MOCK_TCL_LINES

    _require_db_or_raise("gold.tcl_vehicle_realtime")
    # Query DB pour toutes les lignes distinctes
    try:
        rows = execute_query(
            """
            SELECT line_ref, COUNT(*) AS n_vehicles, MAX(recorded_at) AS last_seen
            FROM gold.tcl_vehicle_realtime
            WHERE line_ref IS NOT NULL
            GROUP BY line_ref
            ORDER BY line_ref
            """
        )
    except Exception as e:  # pragma: no cover
        logger.warning("load_tcl_lines DB query failed: %s", e)
        raise DashboardDataError(
            source="gold.tcl_vehicle_realtime",
            detail=f"Query SQL a échoué : {e}",
        ) from e

    if not rows:
        # DB répond mais vide : aucune ligne TCL n'a encore été collectée
        return []

    out: list[dict] = []
    for row in rows:
        line_id = (row.get("line_ref") or "").strip()
        if not line_id:
            continue
        first = line_id[0].upper()
        if first == "T":
            mode, icon, color = "tram", "🚊", "#FFCD00"
        elif first == "M":
            mode, icon, color = "metro", "🚇", "#E2001A"
        else:
            mode, icon, color = "bus", "🚌", "#3498DB"
        out.append(
            {
                "id": line_id,
                "name": f"{'Tram' if mode == 'tram' else 'Métro' if mode == 'metro' else 'Bus'} {line_id}",
                "mode": mode,
                "color": color,
                "icon": icon,
                "n_vehicles": int(row.get("n_vehicles") or 0),
                "last_seen": str(row.get("last_seen")) if row.get("last_seen") else None,
            }
        )

    # Tri : métro d'abord, puis tram, puis bus, alpha à l'intérieur
    mode_order = {"metro": 0, "tram": 1, "bus": 2}
    out.sort(key=lambda x: (mode_order.get(x["mode"], 9), x["id"]))
    return out


def load_lyon_addresses(force_mock: bool = False) -> list[str]:
    """Adresses Lyon pour autocomplete search_bar.

    Référentiel (Sprint VPS-6) : table ``referentiel.lieux_lyon`` (PostgreSQL).
    En mode démo (``LYONFLOW_DEMO_MODE=1``) : fallback mock préservé.

    Cache process (lru_cache 60s) — Sprint VPS-6 hotfix 2026-06-11 :
    sans cache, cette query prend 3.9s sur le VPS (latence réseau +
    21 rows). Avec cache, <0.01s.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _is_demo_mode():
        from src.data.mock.lyon_addresses import get_address_names

        return get_address_names()
    return _load_lyon_addresses_cached()


def load_lyon_addresses_with_coords(force_mock: bool = False) -> list[dict]:
    """Adresses Lyon avec coordonnées GPS complètes.

    Référentiel (cf. load_lyon_addresses). Format dict {name, lon, lat, type}.

    Cache process (lru_cache 60s) — cf. load_lyon_addresses.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _is_demo_mode():
        from src.data.mock.lyon_addresses import LYON_ADDRESSES

        return LYON_ADDRESSES
    return _load_lyon_addresses_with_coords_cached()


# -----------------------------------------------------------------------------
# Cache process-level TTL pour le référentiel lieux (Sprint VPS-6 hotfix)
# -----------------------------------------------------------------------------
# Le widget Mon Trajet appelle load_lyon_addresses_with_coords() plusieurs
# fois par render (search_bar, itinéraire, Vélov). Sans cache, c'est
# 3-4 queries DB de 21 rows à chaque interaction. Avec cache 60s, c'est
# 1 query par minute par process Streamlit (la donnée change très peu).
# -----------------------------------------------------------------------------
import time as _time  # noqa: E402

_LIEUX_CACHE_TTL_S = 60
_lieux_cache: dict[str, tuple[float, object]] = {}


def _load_lyon_addresses_cached() -> list[str]:
    """Cache process TTL 60s pour la liste des noms de lieux."""
    now = _time.monotonic()
    cached = _lieux_cache.get("names")
    if cached is not None and (now - cached[0]) < _LIEUX_CACHE_TTL_S:
        return cached[1]
    _require_db_or_raise("referentiel.lieux_lyon")
    from src.data.db_query import get_lieux_lyon_names

    result = get_lieux_lyon_names()
    _lieux_cache["names"] = (now, result)
    return result


def _load_lyon_addresses_with_coords_cached() -> list[dict]:
    """Cache process TTL 60s pour la liste des lieux avec coords."""
    now = _time.monotonic()
    cached = _lieux_cache.get("coords")
    if cached is not None and (now - cached[0]) < _LIEUX_CACHE_TTL_S:
        return cached[1]
    _require_db_or_raise("referentiel.lieux_lyon")
    from src.data.db_query import get_lieux_lyon_with_coords

    result = get_lieux_lyon_with_coords()
    _lieux_cache["coords"] = (now, result)
    return result


def reset_lieux_cache() -> None:
    """Reset le cache lieux (utile pour les tests)."""
    _lieux_cache.clear()


def load_lieux_transports(lieu_id: int | None = None) -> list[dict]:
    """Dessertes TCL pour un lieu (ou tous les lieux).

    Renvoie la liste des (line_ref, line_mode, stop_name, distance_m, rank)
    pour le(s) lieu(x) demandé(s). Sert au widget itinerary pour calculer
    les trajets multimodaux.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _is_demo_mode():
        # Fallback démo : retourne une liste vide (le widget affichera un
        # message "Mode démo — pas de référentiel transports").
        return []
    _require_db_or_raise("referentiel.lieux_transports")
    from src.data.db_query import get_lieux_transports

    return get_lieux_transports(lieu_id=lieu_id)


def load_cadence_for_line(line_ref: str, day_type: str | None = None, time_bucket: str | None = None) -> list[dict]:
    """Cadence observée pour une ligne TCL.

    Args:
        line_ref: identifiant TCL (ex. ``'M_A'``, ``'T_1'``, ``'C_3'``).
        day_type: filtre optionnel (weekday|saturday|sunday_holiday|vacation).
        time_bucket: filtre optionnel (ex. ``'08:00'``).

    Returns:
        Liste de dicts ``{line_ref, day_type, time_bucket, cadence_min_per_vehicle,
        n_observations, confidence}``.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _is_demo_mode():
        return []
    _require_db_or_raise("referentiel.lieux_calendrier")
    from src.data.db_query import get_cadence_for_line

    return get_cadence_for_line(line_ref=line_ref, day_type=day_type, time_bucket=time_bucket)


# =============================================================================
# MLflow — registry tracking (Sprint 9)
# =============================================================================


def load_spatial_mapping(force_mock: bool = False) -> pd.DataFrame:
    """Mapping nœuds GNN ↔ channel_id (capteurs). Sprint 9 — pour la carte GNN.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_spatial_mapping

    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_SPATIAL_MAPPING)
    _require_db_or_raise("dim_spatial_grid_mapping")
    return get_spatial_mapping()


def load_traffic_predictions_for_map(
    horizon_minutes: int = 60, limit: int = 500, force_mock: bool = False
) -> pd.DataFrame:
    """Prédictions trafic pour la carte GNN (Sprint 9).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_TRAFIC_PREDICTIONS)
    from src.data.db_query import get_traffic_predictions

    _require_db_or_raise("gold.trafic_predictions")
    return get_traffic_predictions(horizon_minutes=horizon_minutes, limit=limit)


def load_mlflow_models(
    experiment: str = "lyonflow-traffic",
    max_results: int = 50,
    force_mock: bool = False,
) -> list[dict]:
    """Liste les modèles trackés dans un experiment MLflow.

    Mode prod (Sprint VPS-6+) : retourne la liste des runs MLflow. Si MLflow
    ne répond pas, lève ``DashboardDataError``.

    Mode démo : retourne ``_FALLBACK_MOCK_MODELS``.

    Raises:
        DashboardDataError: en mode prod, si MLflow ne répond pas.
    """
    from src.ml.mlflow_integration import list_registered_models

    if _maybe_force_mock(force_mock):
        return _FALLBACK_MOCK_MODELS
    if _is_demo_mode():
        return _FALLBACK_MOCK_MODELS

    try:
        runs = list_registered_models(experiment=experiment, max_results=max_results)
    except Exception as e:
        raise DashboardDataError(
            source="mlflow",
            detail=f"MLflow tracking server ne répond pas : {e}",
        ) from e

    if not runs:
        # MLflow répond mais pas de runs : situation légitime
        return []

    # Convertir en format compatible MOCK_MODELS pour les widgets
    out = []
    for r in runs:
        out.append(
            {
                "name": r.get("name", "?"),
                "version": r.get("version", "1.0.0"),
                "stage": r.get("stage", "Production"),
                "metrics": r.get("metrics", {}),
                "trained_at": str(r.get("trained_at", "—")),
                "n_training_samples": int(r.get("params", {}).get("n_samples", 0)),
                "feature_count": int(r.get("params", {}).get("n_features", 0)),
                "drift_status": "ok",
                "note": r.get("tags", {}).get("note", ""),
            }
        )
    return out


# Fallback MLflow models (utilisé quand le serveur est down)
_FALLBACK_MOCK_MODELS: list[dict] = [
    {
        "name": "xgboost_speed_h5",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 1.96, "rmse": 2.45, "r2": 0.947},
        "trained_at": "—",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "ok",
        "note": "MLflow non accessible — fallback mock",
    },
    {
        "name": "xgboost_speed_h60",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 2.43, "rmse": 3.12, "r2": 0.929},
        "trained_at": "—",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "ok",
        "note": "MLflow non accessible — fallback mock",
    },
    {
        "name": "xgboost_speed_h180",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 2.42, "rmse": 3.08, "r2": 0.922},
        "trained_at": "—",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "ok",
        "note": "MLflow non accessible — fallback mock",
    },
    {
        "name": "xgboost_speed_h360",
        "version": "1.2.0",
        "stage": "Production",
        "metrics": {"mae": 2.33, "rmse": 2.97, "r2": 0.917},
        "trained_at": "—",
        "n_training_samples": 1_245_000,
        "feature_count": 14,
        "drift_status": "warning",
        "note": "MLflow non accessible — fallback mock",
    },
    {
        "name": "xgboost_velov_h30",
        "version": "1.0.0",
        "stage": "Production",
        "metrics": {"mae": 4.20, "rmse": 5.31, "r2": 0.331},
        "trained_at": "—",
        "n_training_samples": 13_824,
        "feature_count": 11,
        "drift_status": "ok",
        "note": "MLflow non accessible — fallback mock",
    },
    {
        "name": "xgboost_velov_h60",
        "version": "1.0.0",
        "stage": "Production",
        "metrics": {"mae": 4.31, "rmse": 5.48, "r2": 0.299},
        "trained_at": "—",
        "n_training_samples": 13_824,
        "feature_count": 11,
        "drift_status": "ok",
        "note": "MLflow non accessible — fallback mock",
    },
    {
        "name": "stgcn_gnn_h60",
        "version": "0.3.0",
        "stage": "Staging",
        "metrics": {"mae": 2.78, "rmse": 3.45, "r2": 0.924},
        "trained_at": "—",
        "n_training_samples": 245_000,
        "feature_count": 5,
        "drift_status": "ok",
        "note": "MLflow non accessible — fallback mock",
    },
]


def load_mlflow_experiment_summary(
    experiment: str = "lyonflow-traffic",
    force_mock: bool = False,
) -> dict:
    """Résumé d'un experiment MLflow (nb runs, modeles, etc.).

    Mode prod (Sprint VPS-6+) : interroge MLflow. Si indispo, lève
    ``DashboardDataError``.

    Raises:
        DashboardDataError: en mode prod, si MLflow ne répond pas.
    """
    from src.ml.mlflow_integration import get_experiment_summary

    if _is_demo_mode():
        return {
            "name": experiment,
            "run_count": 0,
            "latest_run_at": None,
            "model_names": [],
            "available": False,
        }
    try:
        return get_experiment_summary(experiment=experiment)
    except Exception as e:
        raise DashboardDataError(
            source="mlflow",
            detail=f"MLflow tracking server ne répond pas : {e}",
        ) from e
