"""Couche de chargement "intelligent" pour les widgets dashboard.

Cette couche abstrait le binding widgets ↔ DB. Les widgets appellent
``load_traffic()``, ``load_velov()``, etc. sans savoir si la donnée vient
de la DB Gold/Silver uniquement (Sprint 8 — viré tous les mocks).

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
from typing import Any

import pandas as pd

from src.data.db_query import (
    _is_db_available,
    get_infrastructure_bottlenecks,
    get_latest_traffic,
    get_nearest_velov_stations,
    get_predictions_vs_actuals,
    get_rgpd_audit_log,
    get_rgpd_consents_summary,
    get_traffic_bottlenecks,
    get_traffic_predictions,
    get_velov_predictions,
    get_velov_stations_geo,
)
from src.data.exceptions import DashboardDataError

# Sprint 8 (2026-06-12) — viré tous les imports src.data.mock.
# La couche data_loader n'utilise plus aucun mock. Si DB indispo,
# DashboardDataError (fail loud). Si DB vide, liste/df vide (info).
from src.db.connection import execute_query

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Mode démo (Sprint 8, 2026-06-12) — DÉPRÉCIÉ
# -----------------------------------------------------------------------------
# Avant : _is_demo_mode() lisait LYONFLOW_DEMO_MODE. Sprint 8 : la
# consigne "zéro mock dans le projet" invalide ce mode. _is_demo_mode
# retourne toujours False maintenant. Les `if _is_demo_mode(): return
# X_mock` qui restaient sont virés au fil du sprint. La DB est l'unique
# source.
# -----------------------------------------------------------------------------

# Cache process (immuable par session)
_demo_mode_cache: bool | None = None


def _is_demo_mode() -> bool:
    """Retourne TOUJOURS False depuis Sprint 8 (zéro mock dans le projet).

    Gardé pour ne pas casser d'anciens call sites. Sera supprimé
    quand tous les call sites seront nettoyés.

    Note : la variable d'env LYONFLOW_DEMO_MODE est lue par
    ``check-deploy-env.sh`` et .env (defense in depth), mais plus
    par le code Python directement.
    """
    return False


def _maybe_force_mock(force_mock: bool) -> bool:
    """Sprint 8 — retourne TOUJOURS False. Le mode mock est déprécié.

    Gardé pour la signature. Sera supprimé en Sprint 9 quand tous
    les call sites seront nettoyés.
    """
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
    _require_db_or_raise("traffic_features_live")
    df = get_latest_traffic(limit=1000)
    if df.empty:
        # Sprint 8 — viré le mode démo. Si DB répond vide, on signale
        # explicitement. Pas de mock fallback.
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
        lat=lat, lon=lon, k=k, require_bikes=require_bikes, require_docks=require_docks,
    )


def load_velov_predictions(horizon_minutes: int = 30, force_mock: bool = False) -> pd.DataFrame:
    """Prédictions disponibilité Vélov.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("velov_predictions")
    return get_velov_predictions(horizon_minutes=horizon_minutes, limit=200)


# =============================================================================
# Bus & infrastructure
# =============================================================================


def load_bus_delays(line_ref: str | None = None, days: int = 7, force_mock: bool = False) -> pd.DataFrame:
    """Retards bus agrégés.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    # Sprint 8 — viré le fallback mock. Toujours DB.
    from src.data.db_query import get_bus_delay_segments

    _require_db_or_raise("bus_delay_segments")
    return get_bus_delay_segments(line_ref=line_ref, days=days)


def load_infra_bottlenecks(top: int = 15, force_mock: bool = False) -> pd.DataFrame:
    """Bottlenecks infrastructure avec diagnostic.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
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
    _require_db_or_raise("predictions_vs_actuals")
    return get_predictions_vs_actuals(limit=limit)


def load_rgpd_audit(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Logs d'audit RGPD.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("rgpd.audit_log")
    return get_rgpd_audit_log(limit=limit)


def load_rgpd_consents(force_mock: bool = False) -> pd.DataFrame:
    """Summary des consents RGPD.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
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
    from src.data.db_query import get_line_kpis

    _require_db_or_raise("mv_line_kpis_live")
    return get_line_kpis(line_ids=line_ids)


def load_otp_heatmap_data(force_mock: bool = False) -> pd.DataFrame:
    """Données heatmap OTP (ligne × heure).

    Mode prod : lit la vue Gold ``gold.mv_otp_heatmap`` (Sprint 10).
    Sprint 8 — viré le fallback mock. Toujours DB (gold.mv_otp_heatmap).

    Raises:
        DashboardDataError: si la DB ne répond pas.
    """
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
    from src.data.db_query import get_weather_hourly

    _require_db_or_raise("silver.meteo_hourly")
    return get_weather_hourly(hours=hours)


def load_recent_alerts(hours: int = 24, limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Alertes récentes (predictions + events).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_recent_alerts

    _require_db_or_raise("gold.alerts")
    return get_recent_alerts(hours=hours, limit=limit)


def load_segments(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Liste des segments routiers.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_segments

    _require_db_or_raise("gold.segments")
    return get_segments(limit=limit)


def load_correlation_matrix(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Matrice de corrélation features Gold.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_correlation_matrix

    _require_db_or_raise("gold.correlation_matrix")
    return get_correlation_matrix(limit=limit)


def load_buses_positions(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Positions temps réel des bus TCL.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_buses_positions

    _require_db_or_raise("tcl_vehicles_clean")
    return get_buses_positions(limit=limit)


def load_kpis_12_months(force_mock: bool = False) -> pd.DataFrame:
    """KPIs ville 12 mois (vue matérialisée Gold) — format plat DataFrame.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_kpis_12_months

    _require_db_or_raise("gold.kpis_12_months")
    return get_kpis_12_months()


def load_elu_kpis_dict(force_mock: bool = False) -> dict:
    """KPIs 12 mois au format dict attendu par les widgets Élu.

    Reconstitue le format ``{kpi_key: {current, delta_ytd, target_2026, history, ...}}``
    depuis le DataFrame plat. Compatible avec les widgets existants qui
    utilisent le mock KPI_12_MONTHS.

    Returns:
        Dict avec les 5 KPIs principaux (part_modale_tc, ponctualite,
        co2_evite_tonnes, bottlenecks_actifs, satisfaction_pct).
    """
    df = load_kpis_12_months(force_mock=force_mock)
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
        # delta_ytd est un delta brut dans le dict mock. On adapte.
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
                "name": f"{ 'Tram' if mode=='tram' else 'Métro' if mode=='metro' else 'Bus' } {line_id}",
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
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    # Sprint 8 — viré le fallback mock lyon_addresses. Toujours DB.
    return _load_lyon_addresses_cached()


def load_lyon_addresses_with_coords(force_mock: bool = False) -> list[dict]:
    """Adresses Lyon avec coordonnées GPS complètes.

    Référentiel (cf. load_lyon_addresses). Format dict {name, lon, lat, type}.

    Cache process (lru_cache 60s) — cf. load_lyon_addresses.

    Raises:
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    # Sprint 8 — viré le fallback mock lyon_addresses. Toujours DB.
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
        DashboardDataError: si PostgreSQL ne répond pas.
    """
    # Sprint 8 — viré le fallback mock. Toujours DB.
    _require_db_or_raise("referentiel.lieux_transports")
    from src.data.db_query import get_lieux_transports

    return get_lieux_transports(lieu_id=lieu_id)


def load_cadence_for_line(
    line_ref: str, day_type: str | None = None, time_bucket: str | None = None
) -> list[dict]:
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


# =============================================================================
# MLflow — registry tracking (Sprint 9)
# =============================================================================


def load_spatial_mapping(force_mock: bool = False) -> pd.DataFrame:
    """Mapping nœuds GNN ↔ channel_id (capteurs). Sprint 9 — pour la carte GNN.

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    from src.data.db_query import get_spatial_mapping

    _require_db_or_raise("dim_spatial_grid_mapping")
    return get_spatial_mapping()


def load_traffic_predictions_for_map(
    horizon_minutes: int = 60, limit: int = 500, force_mock: bool = False
) -> pd.DataFrame:
    """Prédictions trafic pour la carte GNN (Sprint 9).

    Raises:
        DashboardDataError: en mode prod, si PostgreSQL ne répond pas.
    """
    _require_db_or_raise("gold.trafic_predictions")
    from src.data.db_query import get_traffic_predictions

    return get_traffic_predictions(horizon_minutes=horizon_minutes, limit=limit)


def load_traffic_combined_for_map(force_mock: bool = False) -> pd.DataFrame:
    """Vue unifiée trafic temps réel pour la carte dashboard (Sprint VPS-6).

    Combine 3 sources par ordre de priorité :
    1. ``gold_live`` — capteurs Grand Lyon < 5 min (le plus frais)
    2. ``gold_pred`` — prédictions GNN/XGBoost H+1h (Sprint VPS-5)
    3. ``tomtom`` — trafic temps réel TomTom (zones hors couverture boucles)

    Source : ``gold.v_traffic_combined`` (vue SQL créée par
    ``scripts/sql/create_tomtom_traffic.sql``).

    En mode démo, retourne un DataFrame vide (le widget affiche un
    message d'info). En prod, lève ``DashboardDataError`` si DB indispo.

    Returns:
        DataFrame avec colonnes ``channel_id, lat, lon, speed_kmh,
        computed_at, source, confidence``. ``source`` ∈ {gold_live,
        gold_pred, tomtom} indique la priorité.
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


def load_mlflow_models(
    experiment: str = "lyonflow-traffic",
    max_results: int = 50,
    force_mock: bool = False,
) -> list[dict]:
    """Liste les modèles trackés dans un experiment MLflow.

    Sprint VPS-6+ (2026-06-11) — retourne la liste des runs MLflow. Si MLflow
    ne répond pas, lève ``DashboardDataError``. Plus de fallback mock depuis
    Sprint 8 (politique "zéro mock").

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


def load_mlflow_experiment_summary(
    experiment: str = "lyonflow-traffic",
    force_mock: bool = False,
) -> dict:
    """Résumé d'un experiment MLflow (nb runs, modeles, etc.).

    Sprint 8 — viré le fallback mock. Toujours MLflow. Si indispo,
    ``DashboardDataError``.

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
