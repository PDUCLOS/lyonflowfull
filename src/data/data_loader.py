"""Couche de chargement pour les widgets dashboard.

Cette couche abstrait le binding widgets ↔ DB. Les widgets appellent
``load_traffic()``, ``load_velov()``, etc. Chaque fonction interroge
PostgreSQL (schéma Gold/Silver) ou MLflow, et lève ``DashboardDataError``
si la source est indisponible. Le widget appelant catch et affiche
``st.error``.

Pattern d'utilisation dans un widget::

    from src.data.data_loader import load_traffic, load_velov
    from src.data.exceptions import DashboardDataError

    def render_X_widget(data=None):
        if data is None:
            try:
                data = load_traffic()
            except DashboardDataError as e:
                st.error(f"Données pipeline indisponibles : {e.source}")
                return
        # ... reste du widget inchangé

Avantages :

* **Un seul point de changement** — pour brancher un widget sur la DB,
  il suffit d'ajouter une fonction ici, pas de toucher au widget.
* **Fail loud** — si la DB a un blip, le widget devient rouge
  immédiatement. Prometheus (Sprint VPS-3) alerte avant les users.
* **Testable** — les tests monkeypatchent ``_is_db_available``.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from src.data._constants import FRESHNESS_LIVE_MAX_S, FRESHNESS_STALE_MAX_S
from src.data.db_query import (
    _is_db_available,
    clean_line_label,
    get_infrastructure_bottlenecks,
    get_latest_traffic,
    get_nearest_velov_stations,
    get_rgpd_audit_log,
    get_rgpd_consents_summary,
    get_traffic_bottlenecks,
    get_traffic_predictions,
    get_velov_predictions,
    get_velov_stations_geo,
)
from src.data.exceptions import DashboardDataError
from src.db.connection import execute_query

logger = logging.getLogger(__name__)


def _require_db_or_raise(source: str) -> None:
    """Vérifie que la DB est dispo, sinon lève ``DashboardDataError``.

    Helper à appeler en début de chaque fonction du data_loader.
    Garantit le comportement fail loud.
    """
    if not _is_db_available():
        raise DashboardDataError(
            source=source,
            detail="PostgreSQL ne répond pas. Vérifier POSTGRES_HOST/PORT/PASSWORD et docker compose ps postgres",
        )


def _coerce_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Convertit les colonnes NUMERIC psycopg2 (``Decimal``, dtype object) en ``float64``.

    Sans coercition, ``df.nlargest()``/``sort_values()``/tris Plotly échouent en
    ``TypeError`` silencieux (cf. fix Sprint 24+ ``bus_traffic_spatial``).
    """
    if not columns:
        return df
    result = df.copy()
    for col in columns:
        if col not in result.columns:
            logger.warning("_coerce_numeric_columns: colonne '%s' absente du DataFrame, ignorée", col)
            continue
        result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


# =============================================================================
# Trafic routier
# =============================================================================


def load_traffic() -> dict[str, Any]:
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
                "predictions": {h_plus_1h: dict},
                "data_age_seconds": int,
                "freshness_status": "live"|"stale"|"stuck",
                "last_computed_at": "ISO8601",
            }

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas ou si
            la table ``gold.traffic_features_live`` est vide (aucun capteur
            n'a remonté de données).
    """
    _require_db_or_raise("traffic_features_live")
    df = get_latest_traffic(limit=1000)
    if df.empty:
        # DB répond vide : on signale explicitement.
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

    # Top 4 jams depuis bottlenecks (Sprint 22+ : lat/lon réels via LATERAL JOIN)
    main_jams = []
    for _, row in bottlenecks_df.head(4).iterrows():
        speed_val = float(row.get("avg_speed") or 0.0) if not pd.isna(row.get("avg_speed")) else 0.0
        # lat/lon viennent maintenant de la query SQL (cf. get_traffic_bottlenecks
        # Sprint 22+). Si lat/lon sont NULL (capteur sans coords), fallback
        # explicite sur le centre Lyon plutôt qu'un hash pseudo-aléatoire.
        lat_jam = float(row["lat"]) if pd.notna(row.get("lat")) else 45.7640
        lon_jam = float(row["lon"]) if pd.notna(row.get("lon")) else 4.8357
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

    # Prédictions — Règle projet (Sprint VPS-6) : H+1h uniquement.
    # Le DAG ``dag_inference_xgboost`` n'insère que ``horizon_h = 1``
    # (HORIZON_MAP = {60: 1}). Conserver les autres horizons dans le
    # dict était du dead code (silent empty). On garde un dict plat avec
    # uniquement la clé H+1h pour rétro-compat widget.
    predictions: dict[str, dict] = {}
    pred_df = get_traffic_predictions(horizon_minutes=60, limit=200)
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
        predictions["h_plus_1h"] = {
            "average_speed_kmh": round(mean_pred, 1),
            "congestion_level": pred_level,
        }

    # Fraîcheur réelle des données (audit #2 : plus de ``data_source:
    # "db_gold"`` hardcodé — on calcule l'âge réel + un status dérivé
    # consommable par le widget).
    last_computed = df["measurement_time"].max()
    now_utc = pd.Timestamp.now(tz="UTC")
    if pd.notna(last_computed):
        if last_computed.tzinfo is None:
            last_computed = last_computed.tz_localize("UTC")
        data_age_s = (now_utc - last_computed).total_seconds()
        if data_age_s < 0:
            data_age_s = 0.0
        if data_age_s < FRESHNESS_LIVE_MAX_S:
            freshness_status = "live"
        elif data_age_s < FRESHNESS_STALE_MAX_S:
            freshness_status = "stale"
        else:
            freshness_status = "stuck"
    else:
        data_age_s = -1.0
        freshness_status = "unknown"

    return {
        "city": "Lyon",
        "timestamp": str(last_computed) if pd.notna(last_computed) else str(now_utc),
        "average_speed_kmh": round(avg_speed, 1),
        "congestion_level": level,
        "congestion_color": color,
        "bottlenecks_count": n_bottlenecks,
        "main_jams": main_jams,
        "predictions": predictions,
        "data_source": "db_gold",
        "data_age_seconds": data_age_s,
        "freshness_status": freshness_status,
        "last_computed_at": last_computed.isoformat() if pd.notna(last_computed) else None,
    }


def load_traffic_timeseries(node_idx: int, hours: int = 4) -> pd.DataFrame:
    """Série temporelle trafic pour un nœud donné.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
            Retourne un DataFrame vide si la DB répond mais n'a pas de série
            pour ce nœud (cas légitime, widget affichera un message vide).
    """
    # Si DB dispo, query (alias de get_traffic_for_node)
    from src.data.db_query import get_traffic_for_node

    _require_db_or_raise("fact_traffic_series")
    return get_traffic_for_node(node_idx=node_idx, hours=hours)


# =============================================================================
# Vélov
# =============================================================================


def load_velov_stations() -> list[dict]:
    """Stations Vélov proches avec dispo actuelle.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
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


def load_nearest_velov_stations(
    lat: float,
    lon: float,
    k: int = 3,
    require_bikes: int = 0,
    require_docks: int = 0,
) -> list[dict]:
    """Top-k stations Vélov les plus proches d'un point GPS.

    Sprint 9+ (2026-06-17) — extrait de l'inline SQL d'Usager_1_Mon_Trajet.py.
    Wrapper cache-friendly au-dessus de ``db_query.get_nearest_velov_stations``.

    Args:
        lat, lon: GPS du point de référence.
        k: nombre de stations.
        require_bikes, require_docks: filtres dispo (0 = pas de filtre).

    Returns:
        Liste de dicts ``[{station_id, name, lat, lon, bikes_available,
        stands_available, distance_m, is_active}, ...]``.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    return get_nearest_velov_stations(
        lat=lat,
        lon=lon,
        k=k,
        require_bikes=require_bikes,
        require_docks=require_docks,
    )


def load_velov_predictions(horizon_minutes: int = 60) -> pd.DataFrame:
    """Prédictions disponibilité Vélov — H+1h uniquement.

    Sprint 22+ : default=60 (avant : 30). Règle projet focus H+1h strict.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
        ValueError: si ``horizon_minutes != 60`` (propagé de ``get_velov_predictions``).
    """
    _require_db_or_raise("velov_predictions")
    return get_velov_predictions(horizon_minutes=horizon_minutes, limit=200)


# =============================================================================
# Bus & infrastructure
# =============================================================================


def load_bus_delays(line_ref: str | None = None, days: int = 7) -> pd.DataFrame:
    """Retards bus agrégés.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_bus_delay_segments

    _require_db_or_raise("bus_delay_segments")
    return get_bus_delay_segments(line_ref=line_ref, days=days)


def load_infra_bottlenecks(top: int = 15) -> pd.DataFrame:
    """Bottlenecks infrastructure avec diagnostic.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("infrastructure_bottlenecks")
    return get_infrastructure_bottlenecks(top=top)


# =============================================================================
# Prédictions & monitoring
# =============================================================================


def load_rgpd_audit(limit: int = 50) -> pd.DataFrame:
    """Logs d'audit RGPD.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("rgpd.audit_log")
    return get_rgpd_audit_log(limit=limit)


def load_rgpd_consents() -> pd.DataFrame:
    """Summary des consents RGPD.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("rgpd.consents")
    return get_rgpd_consents_summary()


# =============================================================================
# Pro TCL — KPIs agrégés
# =============================================================================


def load_line_kpis(line_ids: list[str] | None = None) -> dict:
    """KPIs par ligne (OTP, retard, fréquence, charge).

    Source : vue matérialisée ``gold.mv_line_kpis_live``.

    Raises:
        DashboardDataError: si la vue Gold n'est pas peuplée
            ou si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_line_kpis

    _require_db_or_raise("mv_line_kpis_live")
    return get_line_kpis(line_ids=line_ids)


def load_otp_heatmap_data() -> pd.DataFrame:
    """Données heatmap OTP (ligne × heure).

    Source : vue Gold ``gold.mv_otp_heatmap``.

    Raises:
        DashboardDataError: si la DB ne répond pas.
    """
    from src.data.db_query import get_otp_heatmap

    _require_db_or_raise("mv_otp_heatmap")
    return get_otp_heatmap()


def load_sensor_saturation() -> pd.DataFrame:
    """Saturation + amplitude + statut par capteur (Sprint 22+).

    Source : vue Gold ``gold.mv_sensor_saturation`` (migration 034 (matérialisée)).

    Pour chaque capteur actif, calcule :
    * ``v85_7j`` : 85e percentile des vitesses sur 7j (= vitesse libre
      typique, indicateur engineering standard — option B validée
      par Patrice).
    * ``sat_now_pct`` : vitesse actuelle / v85 * 100.
      > 100% = congestion, < 50% = fluide.
    * ``amp_pct`` : (max_24h - min_24h) / v85 * 100.
      < 2% = capteur stuck (cf. seuil Sprint 22+).
    * ``status`` : 'ok' | 'stale' (> 15 min sans mesure) | 'stuck'
      (amp < 2% ET std < 1 km/h) | 'no_data' (> 7j sans mesure).

    Raises:
        DashboardDataError: si la DB ne répond pas ou si la vue
            migration 034 (matérialisée) n'est pas appliquée.
    """
    from src.data.db_query import get_sensor_saturation

    _require_db_or_raise("mv_sensor_saturation")
    return get_sensor_saturation()


# =============================================================================
# Élu — agrégats ville
# =============================================================================


def load_city_synthesis() -> dict:
    """Indicateurs de synthèse ville (vélov, traffic, bus, météo).

    Mode prod : agrégat multi-tables calculé en SQL (vue ``gold.v_city_synthesis``).
    Sprint 10+ — en attendant, lève ``DashboardDataError``.

    Raises:
        DashboardDataError: en mode prod, car la vue n'est pas encore implémentée.
    """
    raise DashboardDataError(
        source="gold.v_city_synthesis",
        detail="Vue matérialisée non créée. Sprint 10+ : créer gold.v_city_synthesis "
        "puis rebrancher cette fonction sur la vue.",
    )


def load_bottlenecks_summary() -> pd.DataFrame:
    """Résumé bottlenecks pour page Élu.

    Source : ``gold.mv_bus_traffic_spatial`` (MV spatiale 0.001° ≈ 100 m,
    refresh CONCURRENTLY par DAG */15 min). Sprint 22+ — on ne lit plus
    la table ``gold.infrastructure_bottlenecks`` (JOIN global par heure)
    depuis le fix bugs 3/9 du SPEC_FIX_ELU2_BOTTLENECKS.md.

    Raises:
        DashboardDataError: si la DB ne répond pas.
    """
    from src.data.db_query import get_bottlenecks_summary

    _require_db_or_raise("mv_bus_traffic_spatial")
    return get_bottlenecks_summary()


# =============================================================================
# Météo, alertes, segments, buses, kpis, amenagements (Sprint 8)
# =============================================================================


def load_weather_hourly(hours: int = 24) -> pd.DataFrame:
    """Météo horaire pour le widget météo.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_weather_hourly

    _require_db_or_raise("silver.meteo_hourly")
    return get_weather_hourly(hours=hours)


def load_recent_alerts(hours: int = 24, limit: int = 50) -> pd.DataFrame:
    """Alertes récentes (predictions + events).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_recent_alerts

    _require_db_or_raise("gold.alerts")
    return get_recent_alerts(hours=hours, limit=limit)


def load_segments(limit: int = 200) -> pd.DataFrame:
    """Liste des segments routiers.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_segments

    _require_db_or_raise("gold.segments")
    return get_segments(limit=limit)


def load_correlation_matrix(limit: int = 50) -> pd.DataFrame:
    """Matrice de corrélation features Gold.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_correlation_matrix

    _require_db_or_raise("gold.correlation_matrix")
    return get_correlation_matrix(limit=limit)


def load_buses_positions(limit: int = 200) -> pd.DataFrame:
    """Positions temps réel des bus TCL.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_buses_positions

    _require_db_or_raise("tcl_vehicles_clean")
    return get_buses_positions(limit=limit)


def load_kpis_12_months() -> pd.DataFrame:
    """KPIs ville 12 mois (vue matérialisée Gold) — format plat DataFrame.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_kpis_12_months

    _require_db_or_raise("gold.kpis_12_months")
    return get_kpis_12_months()


def load_elu_kpis_dict() -> dict:
    """KPIs 12 mois au format dict attendu par les widgets Élu.

    Reconstitue le format ``{kpi_key: {current, delta_ytd, target_2026, history, ...}}``
    depuis le DataFrame plat. Compatible avec les widgets existants qui
    utilisent l'ancien format KPI_12_MONTHS.

    Returns:
        Dict avec les 5 KPIs principaux (part_modale_tc, ponctualite,
        co2_evite_tonnes, bottlenecks_actifs, satisfaction_pct).
    """
    df = load_kpis_12_months()
    if df.empty:
        # Fallback structure vide
        return {
            "part_modale_tc": {
                "label": "Part modale TC",
                "current": 0,
                "unit": "%",
                "delta_ytd": 0,
                "target_2026": 0,
                "history": [],
            },
            "ponctualite": {
                "label": "Ponctualité",
                "current": 0,
                "unit": "%",
                "delta_ytd": 0,
                "target_2026": 0,
                "history": [],
            },
            "co2_evite_tonnes": {
                "label": "CO₂ évité",
                "current": 0,
                "unit": "t",
                "delta_ytd": 0,
                "target_2026": 0,
                "history": [],
            },
            "bottlenecks_actifs": {
                "label": "Bottlenecks",
                "current": 0,
                "unit": "",
                "delta_ytd": 0,
                "target_2026": 0,
                "history": [],
            },
            "satisfaction_pct": {
                "label": "Satisfaction",
                "current": 0,
                "unit": "%",
                "delta_ytd": 0,
                "target_2026": 0,
                "history": [],
            },
        }

    kpis = {}
    for kpi_key in df["kpi_key"].unique():
        sub = df[df["kpi_key"] == kpi_key].sort_values("month")
        values = sub["value"].tolist()
        target = float(sub["target_value"].iloc[0]) if not sub.empty else 0
        # Map kpi_key → label + unit
        label_map = {
            "part_modale_tc": ("Part modale TC", "%"),
            "ponctualite": ("Ponctualité", "%"),
            "co2_evite_tonnes": ("CO₂ évité", "t"),
            "bottlenecks_actifs": ("Bottlenecks", ""),
            "satisfaction_pct": ("Satisfaction", "%"),
        }
        label, unit = label_map.get(kpi_key, (kpi_key, ""))
        current = values[-1] if values else 0
        delta_ytd = current - values[0] if len(values) > 1 else 0
        # delta_ytd est un delta brut. On adapte.
        kpis[kpi_key] = {
            "label": label,
            "current": current,
            "unit": unit,
            "delta_ytd": delta_ytd,
            "target_2026": target,
            "history": values,
        }
    return kpis


def load_bottlenecks_top() -> list[dict]:
    """Liste des 10 bottlenecks Élu (format dict avec rank, zone, voyageurs, etc.).

    Reconstruit le format ``BOTTLENECKS_TOP_10`` depuis le DataFrame
    ``load_bottlenecks_summary``.

    Utilise ``line_label`` et ``road_label`` (calculés par
    ``get_bottlenecks_summary``).

    Sprint 22+ (2026-06-25) — Fix bugs 1/4/5/7 du SPEC_FIX_ELU2_BOTTLENECKS.md.
    Tous les champs économiques sont désormais dérivés des colonnes DB
    réelles (plus aucune fonction linéaire de l'index ``i``) :

    * **Bug 1 — gain_min** : ``avg_delay_s / 60 * 0.5`` — on suppose qu'on
      peut récupérer la moitié du retard bus en améliorant l'infra.
    * **Bug 1 — cout_M_euros** : mapping ``diagnosis`` → coût d'aménagement
      type (infra=3 M€, operations=0.8 M€, bus_lane_ok=0.3 M€, ok=0.1 M€).
    * **Bug 5 — voyageurs_jour** : estimation depuis ``n_observations``.
      1 observation ≈ 1 passage bus, capacité moyenne ~80 passagers,
      taux d'occupation SYTRAL ~45% → ``n_obs * 36``.
    * **Bug 7 — roi_mois** : calculé avec la formule du ``roi_calculator``
      (valeur_temps=15 €/h, jours_an=250, doublement aller-retour).
      Une seule source de vérité pour les 2 widgets.
    * **Bug 7 — delai_mois** : heuristique ``max(3, int(cout * 6))``
      (1 M€ ≈ 6 mois de travaux). Conservé dans le dict pour rétro-compat
      avec ``top_decisions.py`` mais plus aucune formule hardcodée.
    * **Bug 4 — diagnosis** : ajoutée au dict (les widgets s'en servent
      pour couleur + emoji).
    * **Nouvelles clés** : ``lat``, ``lon``, ``avg_delay_s``,
      ``traffic_speed_kmh`` (utilisées par ``bottleneck_map``).
    """
    from src.data.data_loader import load_bottlenecks_summary
    from src.data.db_query import clean_line_label

    df = load_bottlenecks_summary()
    if df.empty:
        return []

    # Constantes économiques — alignées avec dashboard/components/widgets/elu/roi_calculator.py
    DEFAULT_VALEUR_TEMPS_EUR_H = 15.0  # €/h (valeur du temps usager TCL)
    DEFAULT_JOURS_AN = 250  # jours ouvrés (hors WE + vacances)
    BUS_PASSAGE_CAPACITY = 80  # passagers/bus (capacité moyenne articulé+standard Lyon)
    BUS_OCCUPATION_RATE = 0.45  # 45% taux d'occupation moyen SYTRAL

    # Coût d'aménagement par type de diagnostic (M€)
    COUT_PAR_DIAGNOSTIC = {
        "infra": 3.0,
        "operations": 0.8,
        "bus_lane_ok": 0.3,
        "ok": 0.1,
    }

    bottlenecks = []
    for i, row in df.head(10).iterrows():
        # Sprint 11+ — utilise les colonnes nettoyées si dispo, sinon fallback DB raw
        zone = row.get("road_label") or clean_line_label(row.get("road_name"))
        if not zone or zone == "—":
            zone = clean_line_label(row.get("road_name", "—"))
        lines_impacted_raw = row.get("line_label") or clean_line_label(row.get("line_ref"))

        # ── Lecture des colonnes DB réelles (Bug 1/4/5/6 fix) ──────────────
        avg_delay_s = float(row.get("avg_bus_delay_s", 0) or 0)
        traffic_speed_kmh = float(row.get("avg_traffic_speed_kmh", 0) or 0)
        diagnosis = str(row.get("diagnosis") or "ok")
        n_observations = int(row.get("n_observations", 0) or 0)
        lat = row.get("lat")
        lon = row.get("lng")  # SQL alias lon AS lng

        # ── Dérivations data-driven (plus aucune fonction linéaire de i) ───
        # Bug 5 Option B : 1 obs ≈ 1 bus, ~80 passagers/bus, ~45% occupation
        voyageurs_estimes = int(n_observations * BUS_PASSAGE_CAPACITY * BUS_OCCUPATION_RATE)

        # Bug 1 : gain estimé = demi-retard récupérable si aménagement réalisé
        gain_min = round(avg_delay_s / 60 * 0.5, 1)

        # Bug 1 : coût d'aménagement selon diagnostic
        cout_M_euros = COUT_PAR_DIAGNOSTIC.get(diagnosis, 1.0)

        # Bug 7 Option A : ROI calculé avec formule du roi_calculator
        # gain_annuel = voyageurs * (gain_min/60) * valeur_temps * 2 (aller-retour) * jours_an
        gain_annuel = voyageurs_estimes * (gain_min / 60) * DEFAULT_VALEUR_TEMPS_EUR_H * 2 * DEFAULT_JOURS_AN
        cout_euros = cout_M_euros * 1_000_000
        roi_mois = round(cout_euros / gain_annuel * 12, 1) if gain_annuel > 0 else 999

        # Bug 7 : délai travaux = heuristique 1 M€ ≈ 6 mois, plancher 3 mois
        delai_mois = max(3, int(cout_M_euros * 6))

        # Description lisible selon diagnostic (était "Amélioration #N…" générique)
        description = _build_bottleneck_description(diagnosis, zone, lines_impacted_raw)

        bottlenecks.append(
            {
                # Clés existantes (rétro-compat avec top_decisions.py + autres widgets)
                "rank": int(row.get("bottleneck_id", i + 1)),
                "zone": zone,
                "lines_impacted": [lines_impacted_raw] if lines_impacted_raw else [],
                "voyageurs_jour": voyageurs_estimes,
                "gain_min": gain_min,
                "cout_M_euros": cout_M_euros,
                "roi_mois": roi_mois,
                "delai_mois": delai_mois,
                "description": description,
                # Nouvelles clés (Bug 4 + préparation Bug 2/6)
                "diagnosis": diagnosis,
                "lat": float(lat) if lat is not None else None,
                "lon": float(lon) if lon is not None else None,
                "avg_delay_s": avg_delay_s,
                "traffic_speed_kmh": traffic_speed_kmh,
            }
        )
    return bottlenecks


def _build_bottleneck_description(diagnosis: str, zone: str, line: str) -> str:
    """Construit une description lisible du bottleneck selon son diagnostic.

    Avant : ``"Amélioration #N du bottleneck L66"`` (générique, sans info).
    Maintenant : explique la nature du problème (infra, opérations, etc.)
    pour aider l'élu à arbitrer.
    """
    zone_str = "ce tronçon" if not zone or zone == "—" else zone
    line_str = f" ({line})" if line and line != "—" else ""
    templates = {
        "infra": f"Aménagement d'infrastructure sur {zone_str}{line_str} — voie dédiée, feu tricolore ou reconfiguration",
        "operations": f"Ajustement opérationnel sur {zone_str}{line_str} — signalisation, fréquence ou intermodalité",
        "bus_lane_ok": f"Voie bus fonctionnelle sur {zone_str}{line_str} — surveiller la pérennité",
        "ok": f"Zone {zone_str}{line_str} sous surveillance",
    }
    return templates.get(diagnosis, templates["ok"])


def load_amenagements_passes(limit: int = 50) -> pd.DataFrame:
    """Aménagements passés (historique persona Élu).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_amenagements_passes

    _require_db_or_raise("gold.amenagements")
    return get_amenagements_passes(limit=limit)


def load_tcl_lines() -> list[dict]:
    """Liste exhaustive des lignes TCL.

    Charge TOUTES les lignes distinctes présentes en DB
    (gold.tcl_vehicle_realtime.line_ref). Catégorisation automatique :
    * ``T*`` (T1, T2, T3...) → tram
    * ``M*`` (M_A, M_B, M_C, M_D) → metro
    * reste → bus

    Returns:
        Liste de dicts {id, name, mode, color, icon} triés par mode puis id.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
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
                "name": f"{'Tram' if mode == 'tram' else 'Métro' if mode == 'metro' else 'Bus'} {clean_line_label(line_id)}",
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


def load_lyon_addresses() -> list[str]:
    """Adresses Lyon pour autocomplete search_bar.

    Source : table ``referentiel.lieux_lyon`` (PostgreSQL).
    Cache process TTL 60s.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    return _load_lyon_addresses_cached()


def load_lyon_addresses_with_coords() -> list[dict]:
    """Adresses Lyon avec coordonnées GPS complètes.

    Source : ``referentiel.lieux_lyon``. Format dict {name, lon, lat, type}.
    Cache process TTL 60s.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
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
_lieux_cache: dict[str, tuple[float, list[Any]]] = {}


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
        DashboardDataError: si PostgreSQL ne répond pas.
    """
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
    _require_db_or_raise("referentiel.lieux_calendrier")
    from src.data.db_query import get_cadence_for_line

    return get_cadence_for_line(line_ref=line_ref, day_type=day_type, time_bucket=time_bucket)


def load_transit_itinerary(origin: str, destination: str) -> dict | None:
    """Itinéraire transport en commun entre 2 lieux (Sprint 14, 2026-06-19).

    Wrapper fail-loud autour de ``src.routing.pathfinder_multimodal.plan_transit_trip``.
    Sérialise le ``TransitItinerary`` (dataclass) en dict pour consommation par
    Streamlit cache (``@st.cache_data`` n'accepte pas les dataclasses non
    hashables).

    Args:
        origin: label de lieu (peut être préfixé emoji, ex: ``"Villeurbanne"``).
        destination: idem.

    Returns:
        Dict sérialisable ou ``None`` si O == D ou si l'un des lieux n'existe
        pas. Structure :
        ``{origin_label, destination_label, segments: [dict, ...],
        transfer_hub, n_transfers, total_duration_min, total_walk_m,
        total_delay_min, confidence, source, diagnostics}``.

    Raises:
        DashboardDataError: si PostgreSQL indisponible.
    """
    _require_db_or_raise("referentiel.lieux_lyon")
    from src.routing.pathfinder_multimodal import plan_transit_trip

    itin = plan_transit_trip(origin=origin, destination=destination)
    if itin is None:
        return None
    return {
        "origin_label": itin.origin_label,
        "destination_label": itin.destination_label,
        "segments": [
            {
                "line_ref": s.line_ref,
                "line_mode": s.line_mode,
                "line_label": s.line_label,
                "stop_origin": s.stop_origin,
                "stop_dest": s.stop_dest,
                "distance_walk_to_m": s.distance_walk_to_m,
                "distance_walk_from_m": s.distance_walk_from_m,
                "cadence_min": s.cadence_min,
                "wait_estimate_min": s.wait_estimate_min,
                "delay_avg_min": s.delay_avg_min,
                "duration_estimate_min": s.duration_estimate_min,
                "confidence": s.confidence,
            }
            for s in itin.segments
        ],
        "transfer_hub": itin.transfer_hub,
        "n_transfers": itin.n_transfers,
        "total_duration_min": itin.total_duration_min,
        "total_walk_m": itin.total_walk_m,
        "total_delay_min": itin.total_delay_min,
        "confidence": itin.confidence,
        "source": itin.source,
        "diagnostics": list(itin.diagnostics),
    }


def load_car_itinerary(
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
    origin_label: str = "Origine",
    dest_label: str = "Destination",
    horizon_minutes: int = 60,
) -> dict | None:
    """Itinéraire voiture traffic-aware entre 2 points GPS (Sprint 15+, 2026-06-19).

    Wrapper fail-loud autour de ``src.routing.pathfinder_multimodal.plan_car_trip``.
    Sérialise le dict retourné (déjà un dict, pas une dataclass) — utile pour
    le cache Streamlit et l'uniformisation avec ``load_transit_itinerary`` /
    ``load_velov_itinerary``.

    Args:
        origin_lon, origin_lat: GPS du point de départ.
        dest_lon, dest_lat: GPS du point d'arrivée.
        origin_label, dest_label: labels affichés.
        horizon_minutes: H+0 (maintenant, défaut 60 = H+1h pour focus Sprint 8+).

    Returns:
        Dict sérialisable avec clés : ``origin_label``, ``destination_label``,
        ``total_length_m``, ``total_duration_min``, ``average_speed_kmh``,
        ``horizon_minutes``, ``segments`` (list[dict]), ``source``.
        ``source == "unavailable"`` si le graphe routier n'a pas pu calculer
        un itinéraire (DB up mais graphe incomplet). ``None`` seulement si
        DB indispo (``DashboardDataError`` levée dans ce cas).

    Raises:
        DashboardDataError: si PostgreSQL indisponible (politique Sprint 8).
    """
    _require_db_or_raise("silver.trafic_boucles_clean")
    from src.routing.pathfinder_multimodal import plan_car_trip

    result = plan_car_trip(
        origin_lon=origin_lon,
        origin_lat=origin_lat,
        dest_lon=dest_lon,
        dest_lat=dest_lat,
        origin_label=origin_label,
        dest_label=dest_label,
        horizon_minutes=horizon_minutes,
    )
    return result


def load_velov_itinerary(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    origin_label: str = "Origine",
    dest_label: str = "Destination",
) -> dict | None:
    """Itinéraire Vélov + marche entre 2 points GPS (Sprint 15+, 2026-06-19).

    Wrapper fail-loud autour de ``src.routing.pathfinder_multimodal.plan_velov_trip``.
    Sérialise la dataclass ``VelovItinerary`` en dict pour consommation par
    Streamlit cache (``@st.cache_data`` n'accepte pas les dataclasses non
    hashables — même contrainte que ``load_transit_itinerary``).

    Args:
        origin_lat, origin_lon: GPS du point de départ.
        dest_lat, dest_lon: GPS du point d'arrivée.
        origin_label, dest_label: labels affichés.

    Returns:
        Dict sérialisable avec clés : ``origin_label``, ``destination_label``,
        ``total_distance_m``, ``total_duration_min``, ``source`` ("db" en prod),
        ``segments`` (list[dict 11 champs]), ``origin_alternatives``,
        ``dest_alternatives``, ``origin_neighbors``, ``dest_neighbors``,
        ``diagnostics``, ``feasible`` (bool).

    Raises:
        DashboardDataError: si PostgreSQL indisponible (politique Sprint 8).
    """
    _require_db_or_raise("silver.velov_clean")
    from src.routing.pathfinder_multimodal import plan_velov_trip

    itin = plan_velov_trip(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        origin_label=origin_label,
        dest_label=dest_label,
    )
    if itin is None:
        return None
    return {
        "origin_label": itin.origin_label,
        "destination_label": itin.destination_label,
        "total_distance_m": itin.total_distance_m,
        "total_duration_min": itin.total_duration_min,
        "source": itin.source,
        "feasible": itin.feasible,
        "segments": [
            {
                "mode": s.mode,
                "from_label": s.from_label,
                "to_label": s.to_label,
                "from_lon": s.from_lon,
                "from_lat": s.from_lat,
                "to_lon": s.to_lon,
                "to_lat": s.to_lat,
                "distance_m": s.distance_m,
                "duration_min": s.duration_min,
                "n_bikes_depart": s.n_bikes_depart,
                "n_docks_arrive": s.n_docks_arrive,
                "n_bikes_mechanical": s.n_bikes_mechanical,
                "n_bikes_electrical": s.n_bikes_electrical,
                "notes": s.notes,
            }
            for s in itin.segments
        ],
        "origin_alternatives": list(itin.origin_alternatives),
        "dest_alternatives": list(itin.dest_alternatives),
        "origin_neighbors": list(itin.origin_neighbors),
        "dest_neighbors": list(itin.dest_neighbors),
        "diagnostics": list(itin.diagnostics),
    }


# =============================================================================
# MLflow — registry tracking (Sprint 9)
# =============================================================================


def load_spatial_mapping() -> pd.DataFrame:
    """Mapping nœuds spatiaux ↔ channel_id (capteurs). Sprint 9 — pour la carte trafic.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_spatial_mapping

    _require_db_or_raise("dim_spatial_grid_mapping")
    return get_spatial_mapping()


def load_traffic_predictions_for_map(horizon_minutes: int = 60, limit: int = 500) -> pd.DataFrame:
    """Prédictions trafic pour la carte (Sprint 9).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("gold.trafic_predictions")
    from src.data.db_query import get_traffic_predictions

    return get_traffic_predictions(horizon_minutes=horizon_minutes, limit=limit)


def load_traffic_live_vs_predicted(limit: int = 2000) -> pd.DataFrame:
    """Live capteurs + prédictions H+1h par segment (ratio + delta)."""
    _require_db_or_raise("gold.traffic_features_live")
    from src.data.db_query import get_traffic_live_vs_predicted

    return get_traffic_live_vs_predicted(limit=limit)


def load_traffic_combined_for_map() -> pd.DataFrame:
    """Vue unifiée trafic temps réel pour la carte dashboard.

    Combine 3 sources par ordre de priorité :
    1. ``gold_live`` — capteurs Grand Lyon < 5 min (le plus frais)
    2. ``gold_pred`` — prédictions XGBoost H+1h
    3. ``tomtom`` — trafic temps réel TomTom (zones hors couverture boucles)

    Source : ``gold.v_traffic_combined`` (vue SQL).

    Returns:
        DataFrame avec colonnes ``channel_id, lat, lon, speed_kmh,
        computed_at, source, confidence``. ``source`` ∈ {gold_live,
        gold_pred, tomtom} indique la priorité.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("gold.v_traffic_combined")
    from src.data.db_query import get_traffic_combined

    return get_traffic_combined()


def get_tomtom_health() -> dict:
    """Renvoie l'état du connecteur TomTom (Sprint VPS-6).

    Pour les healthchecks dashboard / monitoring. Ne lève jamais
    d'exception : renvoie un dict avec les compteurs (quota, cache size,
    clé configurée ou non).
    """
    try:
        from src.ingestion.tomtom_traffic import health as tomtom_health

        return tomtom_health()
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def load_tomtom_coherence(limit: int = 500) -> pd.DataFrame:
    """Cohérence TomTom ↔ capteurs Grand Lyon (Sprint 13+, 2026-06-18).

    Vue ``gold.v_coherence_tomtom_vs_grandlyon`` (migration 14). Pour
    chaque tuile TomTom (12 tuiles Lyon, 0.02°), trouve les capteurs
    Grand Lyon à < 200 m et calcule le delta de vitesse.

    Returns:
        DataFrame avec colonnes ``tile_key, channel_id, site_name,
        distance_m, tomtom_speed_kmh, gl_speed_kmh, delta_kmh,
        ratio_diff, tomtom_confidence, fetched_at, status``.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("gold.v_coherence_tomtom_vs_grandlyon")
    from src.data.db_query import get_tomtom_coherence

    return get_tomtom_coherence(limit=limit)


def load_tomtom_gl_drift(limit: int = 200) -> pd.DataFrame:
    """Capteurs Grand Lyon suspectés HS (Sprint 13+, 2026-06-18).

    Vue ``gold.v_tomtom_gl_drift`` : capteurs avec >= 60% des paires
    TomTom proches en drift (delta > 20 km/h) sur 24h.

    Returns:
        DataFrame avec colonnes ``channel_id, site_name, n_pairs,
        n_ok, n_minor_drift, n_drift, drift_ratio, avg_abs_delta_kmh,
        max_abs_delta_kmh, sensor_health``.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("gold.v_tomtom_gl_drift")
    from src.data.db_query import get_tomtom_gl_drift

    return get_tomtom_gl_drift(limit=limit)


# =============================================================================
# Grille multimodale (Sprint 15+, 2026-06-19) — Axe 1 du SPEC_OPTIMISATION_INTERDEPENDANCES
# =============================================================================
# Vue matérialisée gold.mv_multimodal_grid (migration 17).
# Fail loud via _require_db_or_raise, pas de fallback mock (politique Sprint 8).
# =============================================================================


def load_multimodal_grid(limit: int = 5000) -> pd.DataFrame:
    """Grille multimodale temps réel (Sprint 15+, 2026-06-19).

    Vue matérialisée ``gold.mv_multimodal_grid`` (migration 17) qui
    fusionne trafic + TCL + Vélov + météo sur une grille spatiale 0.01°
    (~1 km) Lyon. Permet au widget ``multimodal_heatmap`` de visualiser
    l'état multimodal du réseau par cellule.

    Args:
        limit: nb max de cellules retournées (défaut 5000 — couvre Lyon
            intra-muros + banlieue proche).

    Returns:
        DataFrame avec colonnes ``lat, lon, avg_speed_kmh, pct_congestion,
        n_sensors, avg_delay_sec, pct_delayed, n_vehicles, bikes_available,
        docks_available, n_stations, temperature_c, rain_mm,
        score_multimodal, diagnosis, computed_at``.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas ou
            si la vue matérialisée n'existe pas encore (migration 17 non
            appliquée). Lève aussi si la vue est vide de façon prolongée
            (> 30 min) — probablement le DAG refresh qui n'a pas tourné.
    """
    _require_db_or_raise("gold.mv_multimodal_grid")
    from src.data.db_query import get_multimodal_grid

    df = get_multimodal_grid(limit=limit)
    if df.empty:
        # DB répond mais vue vide : situation anormale, on signale.
        raise DashboardDataError(
            source="gold.mv_multimodal_grid",
            detail="Vue matérialisée vide. Vérifier que le DAG "
            "transform_silver_to_gold a bien tourné (tâche "
            "refresh_mv_multimodal_grid). Si oui, attendre 1 cycle "
            "(10 min) après l'application de la migration 17.",
        )
    return df


def load_multimodal_grid_diagnosis_counts() -> pd.DataFrame:
    """Distribution des diagnostics dominants (Sprint 15+, 2026-06-19).

    Pour les KPI cards du widget ``multimodal_heatmap`` : compte les
    cellules par diagnostic et calcule le score moyen.

    Returns:
        DataFrame ``{diagnosis, n_cells, avg_score, pct_cells}``.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas ou vue vide.
    """
    _require_db_or_raise("gold.mv_multimodal_grid")
    from src.data.db_query import get_multimodal_grid_diagnosis_counts

    df = get_multimodal_grid_diagnosis_counts()
    if df.empty:
        raise DashboardDataError(
            source="gold.mv_multimodal_grid",
            detail="Vue matérialisée vide — pas de diagnostic à agréger. Vérifier le DAG refresh_mv_multimodal_grid.",
        )
    return df


def load_bus_traffic_spatial(
    line_ref: str | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    """Corrélation bus × trafic spatialisée (Sprint 15+, Axe 3, 2026-06-19).

    Vue matérialisée ``gold.mv_bus_traffic_spatial`` (migration 18). Chaque
    ligne = 1 triplet (line_ref, heure, zone 0.001°) avec le retard bus ET
    la vitesse trafic de la MÊME zone géographique.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas ou MV vide.
    """
    _require_db_or_raise("gold.mv_bus_traffic_spatial")
    from src.data.db_query import get_bus_traffic_spatial

    df = get_bus_traffic_spatial(line_ref=line_ref, limit=limit)
    if df.empty:
        raise DashboardDataError(
            source="gold.mv_bus_traffic_spatial",
            detail="Vue matérialisée vide. Vérifier que la migration 18 "
            "a été appliquée et que le DAG refresh a tourné (*/15 min).",
        )
    return df


def load_bus_traffic_spatial_diagnosis_counts(
    line_ref: str | None = None,
) -> pd.DataFrame:
    """Distribution des diagnostics spatialisés (Sprint 15+, Axe 3).

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas ou MV vide.
    """
    _require_db_or_raise("gold.mv_bus_traffic_spatial")
    from src.data.db_query import get_bus_traffic_spatial_diagnosis_counts

    df = get_bus_traffic_spatial_diagnosis_counts(line_ref=line_ref)
    if df.empty:
        raise DashboardDataError(
            source="gold.mv_bus_traffic_spatial",
            detail="Vue matérialisée vide — pas de diagnostic spatialisé. Vérifier migration 18 + DAG refresh.",
        )
    return df


def load_network_health_score() -> pd.DataFrame:
    """Score de sante reseau 0-100 temps reel (Sprint 15+, Axe 5).

    Appelle ``gold.fn_network_health_score()`` (migration 019). Retourne
    1 ligne avec score, composantes, disponibilite sources, diagnostic.

    Raises:
        DashboardDataError: si PostgreSQL ne repond pas ou si la fonction
            SQL n'existe pas encore (migration 019 non appliquee).
    """
    _require_db_or_raise("gold.fn_network_health_score()")
    from src.data.db_query import get_network_health_score

    df = get_network_health_score()
    if df.empty:
        raise DashboardDataError(
            source="gold.fn_network_health_score()",
            detail="Fonction SQL ne retourne aucune ligne. Verifier migration 019 appliquee.",
        )
    return df


# =============================================================================
# Sprint 17 Axe 2 — Propagation de congestion (migration 024 v3)
# =============================================================================
# Vue matérialisée gold.mv_congestion_propagation_pairs : index des paires
# de capteurs adjacents (K=2 grid via gold.dim_spatial_adjacency) avec lat/lon
# des 2 nœuds. PAS de CORR calculée ici (trop coûteux en SQL — testé : 4 min
# timeout). Le widget propagation_map.py calcule les CORR en Python
# (pandas/numpy, vectorisé) depuis gold.traffic_features_live (6h × 5min).
# Voir docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md §3.
# =============================================================================


def load_congestion_propagation_pairs() -> pd.DataFrame:
    """Paires de capteurs adjacents (Sprint 17 Axe 2, migration 024 v3).

    Vue matérialisée ``gold.mv_congestion_propagation_pairs`` (~50k paires
    K=2 grid) avec lat/lon des 2 nœuds (propriétés ``properties_twgid``
    du mapping dim_spatial). Sert de base au widget ``propagation_map``
    (Folium avec flèches directionnelles) pour calculer les lag
    cross-corrélations en Python.

    Returns:
        DataFrame avec colonnes ``node_a, lat_a, lon_a, node_b, lat_b, lon_b``.
        ``node_a`` et ``node_b`` sont des ``properties_twgid`` (string
        integer) — pas des channel_id LYO. Le widget doit passer par
        ``gold.mv_twgid_to_lyo`` pour récupérer les channel_id live.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas ou si la vue
            matérialisée n'existe pas (migration 024 non appliquée).
    """
    _require_db_or_raise("gold.mv_congestion_propagation_pairs")
    from src.data.db_query import get_congestion_propagation_pairs

    df = get_congestion_propagation_pairs()
    if df.empty:
        raise DashboardDataError(
            source="gold.mv_congestion_propagation_pairs",
            detail="Vue matérialisée vide. Vérifier que la migration 024 "
            "a été appliquée et que le DAG "
            "refresh_congestion_propagation a tourné (*/30 min).",
        )
    return df


def load_traffic_speeds_for_propagation(hours: int = 6) -> pd.DataFrame:
    """Séries temporelles vitesse par channel_id (Sprint 17 Axe 2).

    Charge les ``speed_kmh`` depuis ``gold.traffic_features_live`` sur
    les ``hours`` dernières heures, JOINées avec ``gold.mv_twgid_to_lyo``
    pour que chaque ligne porte le ``properties_twgid`` (clé de la MV
    paires) ET le ``channel_id`` LYO (clé de traffic_features_live).

    Cadence 5 min → ~72 points / capteur / 6h.

    Returns:
        DataFrame ``properties_twgid, channel_id, computed_at, speed_kmh``.
        Un capteur peut apparaître plusieurs fois (1 par timestamp).

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("gold.traffic_features_live + gold.mv_twgid_to_lyo")
    query = """
        SELECT
            mv.properties_twgid,
            t.channel_id,
            t.computed_at,
            t.speed_kmh
        FROM gold.traffic_features_live t
        JOIN gold.mv_twgid_to_lyo mv ON mv.channel_id = t.channel_id
        WHERE t.computed_at >= NOW() - make_interval(hours => %s)
          AND t.speed_kmh IS NOT NULL
          AND t.speed_kmh > 0
        ORDER BY t.computed_at DESC
    """
    from src.data.db_query import _df_from_query

    df = _df_from_query(query, (hours,))
    if df.empty:
        raise DashboardDataError(
            source="gold.traffic_features_live + gold.mv_twgid_to_lyo",
            detail=(
                f"Aucune mesure de vitesse sur les {hours}h glissantes. "
                "Vérifier que le DAG transform_silver_to_gold tourne bien "
                "(tâche refresh_traffic_features_live, */5 min) ET que "
                "gold.mv_twgid_to_lyo est peuplée (script "
                "build_mv_twgid_to_lyo.py)."
            ),
        )
    return df


def load_mlflow_models(
    experiment: str = "lyonflow-traffic",
    max_results: int = 50,
) -> list[dict]:
    """Liste les modèles trackés dans un experiment MLflow.

    Sprint VPS-6+ (2026-06-11) — retourne la liste des runs MLflow. Si MLflow
    ne répond pas, lève ``DashboardDataError``.

    Raises:
        DashboardDataError: si MLflow ne répond pas.
    """
    from src.ml.mlflow_integration import list_registered_models

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

    # Conversion des runs MLflow en format dict consommé par les widgets
    # (Sprint 9+ : plus de référence à MOCK_MODELS — fallback viré).
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


def load_mlflow_experiment_summary(experiment: str) -> dict:
    """Résumé d'un experiment MLflow (nb runs, modeles, etc.).

    Note Sprint 22+ : ``experiment`` est désormais obligatoire. Le default
    global ``"lyonflow-traffic"`` a été supprimé (cf.
    ``src/ml/mlflow_integration.py``) — chaque caller doit spécifier
    explicitement l'expérience dédiée (``"xgboost_speed"`` ou
    ``"xgboost_velov"``).

    Si MLflow est indisponible, lève ``DashboardDataError``.

    Raises:
        DashboardDataError: si MLflow ne répond pas.
    """
    from src.ml.mlflow_integration import get_experiment_summary

    try:
        return get_experiment_summary(experiment=experiment)
    except Exception as e:
        raise DashboardDataError(
            source="mlflow",
            detail=f"MLflow tracking server ne répond pas : {e}",
        ) from e
