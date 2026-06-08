"""Couche de chargement "intelligent" pour les widgets dashboard.

Cette couche abstrait le binding widgets ↔ DB. Les widgets appellent
``load_traffic()``, ``load_velov()``, etc. sans savoir si la donnée vient
de la DB Gold/Silver ou des mocks ``src.data.mock``.

Pattern d'utilisation dans un widget::

    from src.data.data_loader import load_traffic, load_velov

    def render_X_widget(data=None):
        if data is None:
            data = load_traffic()  # DB or mock fallback
        # ... reste du widget inchangé

Avantages:

* **Un seul point de changement** — pour brancher un widget sur la DB,
  il suffit d'ajouter une fonction ici, pas de toucher au widget.
* **Cache transparent** — la détection DB-down est cachée, pas de
  re-ping à chaque render.
* **Testable** — les tests monkeypatchent ``src.data.data_loader._is_db_available``.
* **Mode démo forcé** — ``load_X(force_mock=True)`` permet de démontrer
  sans dépendre de la DB (utile pour screenshots, démos commerciales).

C'est la couche d'abstraction qui implémente le pattern "Offline-First
Dashboard" du Sprint 6 — un widget marche dans 100% des cas, DB ou pas.
"""

from __future__ import annotations

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
from src.data.mock import elu as elu_mock
from src.data.mock import pro_tcl as pro_tcl_mock
from src.data.mock import usager as usager_mock


def _maybe_force_mock(force_mock: bool) -> bool:
    """Retourne True si on doit utiliser le mock (DB down OU force_mock)."""
    if force_mock:
        return True
    return not _is_db_available()


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
    """
    if _maybe_force_mock(force_mock):
        return usager_mock.MOCK_TRAFFIC

    df = get_latest_traffic(limit=200)
    if df.empty:
        return usager_mock.MOCK_TRAFFIC

    avg_speed = float(df["speed_kmh"].mean()) if not df.empty else 0.0
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
        main_jams.append(
            {
                "road": f"Channel {row['channel_id']}",
                "lat": 45.75 + (int(row["node_idx"]) % 10) * 0.005,  # approx
                "lon": 4.83 + (int(row["node_idx"]) % 10) * 0.005,
                "speed_kmh": float(row["avg_speed"]),
                "delay_min": max(0, int((30 - float(row["avg_speed"])) / 5)),
                "severity": "high"
                if float(row["avg_speed"]) < 15
                else "medium"
                if float(row["avg_speed"]) < 25
                else "low",
            }
        )

    # Prédictions
    predictions: dict[str, dict] = {"h_plus_30min": {}, "h_plus_1h": {}, "h_plus_3h": {}}
    for horizon, key in [(30, "h_plus_30min"), (60, "h_plus_1h"), (180, "h_plus_3h")]:
        pred_df = get_traffic_predictions(horizon_minutes=horizon, limit=200)
        if not pred_df.empty:
            mean_pred = float(pred_df["predicted_speed"].mean())
            if mean_pred >= 35:
                pred_level = "fluide"
            elif mean_pred >= 25:
                pred_level = "modéré"
            elif mean_pred >= 15:
                pred_level = "dense"
            else:
                pred_level = "bloqué"
            predictions[key] = {"average_speed_kmh": round(mean_pred, 1), "congestion_level": pred_level}

    # Fallback si pas de prédictions
    for key in ("h_plus_30min", "h_plus_1h", "h_plus_3h"):
        if not predictions[key]:
            predictions[key] = usager_mock.MOCK_TRAFFIC["predictions"].get(key, {})

    return {
        "city": "Lyon",
        "timestamp": str(pd.Timestamp.now(tz="UTC")),
        "average_speed_kmh": round(avg_speed, 1),
        "congestion_level": level,
        "congestion_color": color,
        "bottlenecks_count": n_bottlenecks,
        "main_jams": main_jams,
        "predictions": predictions,
        "data_source": "db_gold" if not force_mock else "mock",
    }


def load_traffic_timeseries(node_idx: int, hours: int = 4, force_mock: bool = False) -> pd.DataFrame:
    """Série temporelle trafic pour un nœud donné."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_TRAFFIC_TIMESERIES)
    # Si DB dispo, query (alias de get_traffic_for_node)
    from src.data.db_query import get_traffic_for_node

    return get_traffic_for_node(node_idx=node_idx, hours=hours)


# =============================================================================
# Vélov
# =============================================================================


def load_velov_stations(force_mock: bool = False) -> list[dict]:
    """Stations Vélov proches avec dispo actuelle."""
    if _maybe_force_mock(force_mock):
        return usager_mock.VELOV_STATIONS

    df = get_velov_stations_geo()
    if df.empty:
        return usager_mock.VELOV_STATIONS

    return [
        {
            "id": int(row.get("station_id", i)),
            "name": row.get("station_name", f"Station {i}"),
            "lat": float(row["lat"]),
            "lon": float(row["lng"]),
            "bikes_available": int(row.get("bikes_available", 0)),
            "stands_available": int(row.get("docks_available", 0)),
            "distance_m": 0,
            "is_operational": bool(row.get("is_operational", True)),
        }
        for i, row in df.iterrows()
    ]


def load_velov_predictions(horizon_minutes: int = 30, force_mock: bool = False) -> pd.DataFrame:
    """Prédictions disponibilité Vélov."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame([p for p in usager_mock.MOCK_VELOV_PREDICTIONS if p["horizon_minutes"] == horizon_minutes])
    return get_velov_predictions(horizon_minutes=horizon_minutes, limit=200)


# =============================================================================
# Bus & infrastructure
# =============================================================================


def load_bus_delays(line_ref: str | None = None, days: int = 7, force_mock: bool = False) -> pd.DataFrame:
    """Retards bus agrégés."""
    if _maybe_force_mock(force_mock):
        df = pd.DataFrame(usager_mock.MOCK_BUS_DELAYS)
        if line_ref:
            df = df[df["line_ref"] == line_ref]
        return df
    from src.data.db_query import get_bus_delay_segments

    return get_bus_delay_segments(line_ref=line_ref, days=days)


def load_infra_bottlenecks(top: int = 15, force_mock: bool = False) -> pd.DataFrame:
    """Bottlenecks infrastructure avec diagnostic."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_INFRA_BOTTLENECKS[:top])
    return get_infrastructure_bottlenecks(top=top)


# =============================================================================
# Prédictions & monitoring
# =============================================================================


def load_predictions_vs_actuals(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Backtesting prédictions vs réalité."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_PREDICTIONS_VS_ACTUALS[:limit])
    return get_predictions_vs_actuals(limit=limit)


def load_rgpd_audit(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Logs d'audit RGPD."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_RGPD_AUDIT[:limit])
    return get_rgpd_audit_log(limit=limit)


def load_rgpd_consents(force_mock: bool = False) -> pd.DataFrame:
    """Summary des consents RGPD."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_RGPD_CONSENTS_SUMMARY)
    return get_rgpd_consents_summary()


# =============================================================================
# Pro TCL (mock-only pour l'instant — ces KPIs sont des agrégats calculés)
# =============================================================================


def load_line_kpis(line_ids: list[str] | None = None, force_mock: bool = False) -> dict:
    """KPIs par ligne (OTP, retard, fréquence, charge).

    Note: les KPIs ligne sont des agrégats complexes (jointures Silver+Gold).
    En attendant la vue SQL, on garde le mock pro_tcl.LINE_KPIS comme source
    principale. Le binding DB viendra Sprint 7+ avec la création d'une vue
    matérialisée ``gold.mv_line_kpis_live``.
    """
    return pro_tcl_mock.LINE_KPIS


def load_otp_heatmap_data(force_mock: bool = False) -> pd.DataFrame:
    """Données heatmap OTP (ligne × heure).

    OTP_GRID mock structure: ``{line_id: {date_str: [otp_h0, otp_h1, ...]}}``.
    On aplatit en DataFrame ``[line_id, date, hour, otp_pct]``.
    """
    grid = pro_tcl_mock.OTP_GRID
    rows = []
    for line_id, by_date in grid.items():
        for date_str, hourly in by_date.items():
            for hour, otp in enumerate(hourly):
                rows.append({"line_id": line_id, "date": date_str, "hour": hour, "otp_pct": float(otp)})
    return pd.DataFrame(rows)


# =============================================================================
# Élu (mock-only — agrégats ville)
# =============================================================================


def load_city_synthesis(force_mock: bool = False) -> dict:
    """Indicateurs de synthèse ville (vélov, traffic, bus, météo)."""
    return elu_mock.SYNTHESIS_DATA


def load_bottlenecks_summary(force_mock: bool = False) -> pd.DataFrame:
    """Résumé bottlenecks pour page Élu."""
    return pd.DataFrame(elu_mock.BOTTLENECKS_LIST)


# =============================================================================
# Météo, alertes, segments, buses, kpis, amenagements (Sprint 8)
# =============================================================================


def load_weather_hourly(hours: int = 24, force_mock: bool = False) -> pd.DataFrame:
    """Météo horaire pour le widget météo."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_WEATHER_HOURLY)
    from src.data.db_query import get_weather_hourly

    return get_weather_hourly(hours=hours)


def load_recent_alerts(hours: int = 24, limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Alertes récentes (predictions + events)."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_RECENT_ALERTS[:limit])
    from src.data.db_query import get_recent_alerts

    return get_recent_alerts(hours=hours, limit=limit)


def load_segments(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Liste des segments routiers."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_SEGMENTS[:limit])
    from src.data.db_query import get_segments

    return get_segments(limit=limit)


def load_correlation_matrix(limit: int = 50, force_mock: bool = False) -> pd.DataFrame:
    """Matrice de corrélation features Gold."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_CORRELATION_MATRIX[:limit])
    from src.data.db_query import get_correlation_matrix

    return get_correlation_matrix(limit=limit)


def load_buses_positions(limit: int = 200, force_mock: bool = False) -> pd.DataFrame:
    """Positions temps réel des bus TCL."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(pro_tcl_mock.MOCK_BUSES_POSITIONS[:limit])
    from src.data.db_query import get_buses_positions

    return get_buses_positions(limit=limit)


def load_kpis_12_months(force_mock: bool = False) -> pd.DataFrame:
    """KPIs ville 12 mois (vue matérialisée Gold) — format plat DataFrame."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(elu_mock.MOCK_KPIS_12_MONTHS_FLAT)
    from src.data.db_query import get_kpis_12_months

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
    """Aménagements passés (historique persona Élu)."""
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(elu_mock.MOCK_AMENAGEMENTS_FLAT[:limit])
    from src.data.db_query import get_amenagements_passes

    return get_amenagements_passes(limit=limit)


def load_tcl_lines(force_mock: bool = False) -> list[dict]:
    """Liste des lignes TCL (données quasi-statiques)."""
    # Pas de DB query ici — données statiques Grand Lyon
    return pro_tcl_mock.MOCK_TCL_LINES


def load_lyon_addresses(force_mock: bool = False) -> list[str]:
    """Adresses mock Lyon (pour autocomplete search_bar).

    Source unifiée : src.data.mock.lyon_addresses.LYON_ADDRESSES.
    Format dict {name, lon, lat, type} — on extrait juste les noms ici.
    """
    from src.data.mock.lyon_addresses import get_address_names

    return get_address_names()


def load_lyon_addresses_with_coords(force_mock: bool = False) -> list[dict]:
    """Adresses mock Lyon avec coordonnées GPS complètes.

    Pour composants qui ont besoin de lat/lon (carte, marker).
    """
    from src.data.mock.lyon_addresses import LYON_ADDRESSES

    return LYON_ADDRESSES


# =============================================================================
# MLflow — registry tracking (Sprint 9)
# =============================================================================


def load_spatial_mapping(force_mock: bool = False) -> pd.DataFrame:
    """Mapping nœuds GNN ↔ channel_id (capteurs). Sprint 9 — pour la carte GNN."""
    from src.data.db_query import get_spatial_mapping

    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_SPATIAL_MAPPING)
    return get_spatial_mapping()


def load_traffic_predictions_for_map(
    horizon_minutes: int = 60, limit: int = 500, force_mock: bool = False
) -> pd.DataFrame:
    """Prédictions trafic pour la carte GNN (Sprint 9).

    Wrapper autour de get_traffic_predictions avec fallback mock.
    """
    if _maybe_force_mock(force_mock):
        return pd.DataFrame(usager_mock.MOCK_TRAFIC_PREDICTIONS)
    from src.data.db_query import get_traffic_predictions

    return get_traffic_predictions(horizon_minutes=horizon_minutes, limit=limit)


def load_mlflow_models(
    experiment: str = "lyonflow-traffic",
    max_results: int = 50,
    force_mock: bool = False,
) -> list[dict]:
    """Liste les modèles trackés dans un experiment MLflow.

    Si MLflow indispo, retourne une liste mock (fallback transparent).
    """
    from src.ml.mlflow_integration import list_registered_models

    if _maybe_force_mock(force_mock):
        return _FALLBACK_MOCK_MODELS

    runs = list_registered_models(experiment=experiment, max_results=max_results)
    if not runs:
        # Fallback mock si pas de runs ou serveur down
        return _FALLBACK_MOCK_MODELS

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
    """Résumé d'un experiment MLflow (nb runs, modeles, etc.)."""
    from src.ml.mlflow_integration import get_experiment_summary

    if _maybe_force_mock(force_mock):
        return {
            "name": experiment,
            "run_count": 0,
            "latest_run_at": None,
            "model_names": [],
            "available": False,
        }
    return get_experiment_summary(experiment=experiment)
