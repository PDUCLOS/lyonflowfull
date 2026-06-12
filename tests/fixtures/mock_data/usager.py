"""Mock data Lyon pour le persona Usager.

Données réalistes basées sur les vraies stations/lignes de Lyon :
- Lignes TCL : C3, C13, C14, T1, T2, T3, T6, M A, M B, M C, M D
- Stations Vélov' : Part-Dieu, Bellecour, Hôtel de Ville, Saxe, etc.
- Adresses : Vrai-ish lyonnais (Place Bellecour, Cours Lafayette, etc.)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# -----------------------------------------------------------------------------
# Lignes TCL avec icônes et couleurs
# -----------------------------------------------------------------------------
TCL_LINES = [
    {"id": "M_A", "name": "Métro A", "mode": "metro", "color": "#E2001A", "icon": "🚇"},
    {"id": "M_B", "name": "Métro B", "mode": "metro", "color": "#0064B0", "icon": "🚇"},
    {"id": "M_C", "name": "Métro C", "mode": "metro", "color": "#FF6600", "icon": "🚇"},
    {"id": "M_D", "name": "Métro D", "mode": "metro", "color": "#00A88E", "icon": "🚇"},
    {"id": "T1", "name": "Tram T1", "mode": "tram", "color": "#FFCD00", "icon": "🚊"},
    {"id": "T2", "name": "Tram T2", "mode": "tram", "color": "#A4D65E", "icon": "🚊"},
    {"id": "T3", "name": "Tram T3", "mode": "tram", "color": "#9B59B6", "icon": "🚊"},
    {"id": "T6", "name": "Tram T6", "mode": "tram", "color": "#E67E22", "icon": "🚊"},
    {"id": "C3", "name": "Bus C3", "mode": "bus", "color": "#3498DB", "icon": "🚌"},
    {"id": "C13", "name": "Bus C13", "mode": "bus", "color": "#1ABC9C", "icon": "🚌"},
    {"id": "C14", "name": "Bus C14", "mode": "bus", "color": "#16A085", "icon": "🚌"},
    {"id": "C17", "name": "Bus C17", "mode": "bus", "color": "#27AE60", "icon": "🚌"},
]

# -----------------------------------------------------------------------------
# Adresses lyonnaises de référence
# -----------------------------------------------------------------------------
LyonAddresses = [
    "Part-Dieu, Lyon",
    "Place Bellecour, Lyon",
    "Hôtel de Ville, Lyon",
    "Vieux Lyon",
    "Presqu'île, Lyon",
    "Confluence, Lyon",
    "Croix-Rousse, Lyon",
    "Place des Terreaux, Lyon",
    "Opéra, Lyon",
    "Parc de la Tête d'Or, Lyon",
    "Université Lyon 3, Lyon",
    "Place Jean Macé, Lyon",
    "Saxe-Gambetta, Lyon",
    "Guillotière, Lyon",
    "Mermoz, Lyon",
    "Monplaisir, Lyon",
    "Gerland, Lyon",
    "Vaise, Lyon",
]


# -----------------------------------------------------------------------------
# Itinéraires de test
# -----------------------------------------------------------------------------
MOCK_TRIP_RESULTS = {
    "default": {
        "origin": "Villeurbanne",
        "destination": "Part-Dieu",
        "departure": "maintenant",
        "options": [
            {
                "rank": 1,
                "recommended": True,
                "mode": "transit",
                "mode_label": "Métro A",
                "mode_icon": "🚇",
                "duration_min": 18,
                "duration_text": "18 min",
                "cost_eur": 1.90,
                "co2_g": 30,
                "wait_min": 3,
                "transfers": 0,
                "confidence_pct": 78,
                "confidence_text": "78% de chances d'arriver à 8h47",
                "steps": [
                    {"mode": "walk", "duration_min": 4, "from": "Domicile", "to": "Métro A — République"},
                    {"mode": "metro", "line": "M_A", "duration_min": 11, "from": "République", "to": "Part-Dieu"},
                    {"mode": "walk", "duration_min": 3, "from": "Métro A — Part-Dieu", "to": "Bureau"},
                ],
                "why": [
                    "Trafic prédit fluide sur tout le trajet",
                    "T3 à l'heure, M A fréquence 4 min",
                    "12 Vélov dispo à Part-Dieu à 8h47",
                ],
            },
            {
                "rank": 2,
                "mode": "bike",
                "mode_label": "Vélov",
                "mode_icon": "🚲",
                "duration_min": 22,
                "duration_text": "22 min",
                "cost_eur": 0.0,
                "co2_g": 0,
                "wait_min": 0,
                "transfers": 0,
                "confidence_pct": 65,
                "confidence_text": "65% — pluie fine prévue",
                "why": "Pluvieux, mais stations Vélov bien fournies",
            },
            {
                "rank": 3,
                "mode": "car",
                "mode_label": "Voiture",
                "mode_icon": "🚗",
                "duration_min": 24,
                "duration_text": "24 min",
                "cost_eur": 4.20,
                "co2_g": 1800,
                "wait_min": 0,
                "transfers": 0,
                "confidence_pct": 82,
                "confidence_text": "82%",
                "why": "Cours Lafayette bouché à 8h15 (moyenne 18 km/h)",
            },
        ],
    }
}


# -----------------------------------------------------------------------------
# Stations Vélov réelles (extrait)
# -----------------------------------------------------------------------------
VELOV_STATIONS = [
    {
        "id": 1001,
        "name": "Part-Dieu - Vivier Merle",
        "lat": 45.7607,
        "lon": 4.8589,
        "bikes_available": 12,
        "stands_available": 18,
        "distance_m": 0,
    },
    {
        "id": 1002,
        "name": "Bellecour - Place",
        "lat": 45.7575,
        "lon": 4.8324,
        "bikes_available": 7,
        "stands_available": 23,
        "distance_m": 1200,
    },
    {
        "id": 1003,
        "name": "Hôtel de Ville - Louis Pradel",
        "lat": 45.7672,
        "lon": 4.8342,
        "bikes_available": 15,
        "stands_available": 11,
        "distance_m": 900,
    },
    {
        "id": 1004,
        "name": "Saxe - Gambetta",
        "lat": 45.7496,
        "lon": 4.8461,
        "bikes_available": 4,
        "stands_available": 22,
        "distance_m": 1800,
    },
    {
        "id": 1005,
        "name": "Place des Terreaux",
        "lat": 45.7673,
        "lon": 4.8343,
        "bikes_available": 9,
        "stands_available": 17,
        "distance_m": 850,
    },
    {
        "id": 1006,
        "name": "Vaise - Gare",
        "lat": 45.7798,
        "lon": 4.8058,
        "bikes_available": 18,
        "stands_available": 8,
        "distance_m": 3400,
    },
    {
        "id": 1007,
        "name": "Confluence - Pôle de loisirs",
        "lat": 45.7405,
        "lon": 4.8165,
        "bikes_available": 22,
        "stands_available": 4,
        "distance_m": 2800,
    },
    {
        "id": 1008,
        "name": "Monplaisir - Lumière",
        "lat": 45.7440,
        "lon": 4.8607,
        "bikes_available": 6,
        "stands_available": 20,
        "distance_m": 2100,
    },
]


# -----------------------------------------------------------------------------
# Alertes types
# -----------------------------------------------------------------------------
MOCK_ALERTS = [
    {
        "id": "alert_1",
        "line": "T3",
        "line_icon": "🚊",
        "line_color": "#9B59B6",
        "title": "T3 retardé 6 min",
        "description": "Sur le trajet Mermoz → Part-Dieu (17h42)",
        "impact": "5 min de retard à l'arrivée",
        "action": "Pars à 18h24 au lieu de 18h18",
        "action_type": "delay_departure",
        "severity": "warning",
        "timestamp": "2026-06-05T15:30:00+02:00",
    },
    {
        "id": "alert_2",
        "line": "C13",
        "line_icon": "🚌",
        "line_color": "#1ABC9C",
        "title": "C13 bientôt plein",
        "description": "Entre Saxe et Part-Dieu (18h05)",
        "impact": "Saturation prévue >95%",
        "action": "Prends le M B à 18h03 (5 min de marche)",
        "action_type": "alternative_route",
        "severity": "info",
        "timestamp": "2026-06-05T15:32:00+02:00",
    },
    {
        "id": "alert_3",
        "line": "T1",
        "line_icon": "🚊",
        "line_color": "#FFCD00",
        "title": "T1 — chantier Presqu'île",
        "description": "Voie unique entre Hôtel de Ville et Perrache jusqu'au 15/06",
        "impact": "Fréquence réduite de 6 à 9 min en heure de pointe",
        "action": "Anticipe de 3 min tes trajets T1 après 17h",
        "action_type": "info",
        "severity": "info",
        "timestamp": "2026-06-05T08:00:00+02:00",
    },
]


# -----------------------------------------------------------------------------
# Météo mock
# -----------------------------------------------------------------------------
MOCK_WEATHER = {
    "city": "Lyon",
    "timestamp": "2026-06-05T15:30:00+02:00",
    "temp_c": 18,
    "feels_like_c": 17,
    "condition": "Pluie fine",
    "condition_icon": "🌦",
    "rain_mm_h": 0.4,
    "wind_kmh": 12,
    "humidity_pct": 78,
    "velov_advice": "Vélov déconseillé (pluie > 0.1mm/h)",
    "cycling_score": 0.4,  # 0 = mauvais, 1 = parfait
    "next_3h": [
        {"hour": 16, "condition": "Pluie fine", "icon": "🌦", "temp_c": 18, "rain_mm_h": 0.3},
        {"hour": 17, "condition": "Couvert", "icon": "☁️", "temp_c": 17, "rain_mm_h": 0.0},
        {"hour": 18, "condition": "Couvert", "icon": "☁️", "temp_c": 17, "rain_mm_h": 0.0},
    ],
}


# -----------------------------------------------------------------------------
# Trafic routier mock
# -----------------------------------------------------------------------------
MOCK_TRAFFIC = {
    "city": "Lyon",
    "timestamp": "2026-06-05T15:30:00+02:00",
    "average_speed_kmh": 23,
    "congestion_level": "modéré",  # fluide | modéré | dense | bloqué
    "congestion_color": "#FF9800",
    "bottlenecks_count": 14,
    "main_jams": [
        {"road": "Cours Lafayette", "lat": 45.7542, "lon": 4.8411, "speed_kmh": 14, "delay_min": 8, "severity": "high"},
        {
            "road": "Quai Claude Bernard",
            "lat": 45.7513,
            "lon": 4.8360,
            "speed_kmh": 18,
            "delay_min": 5,
            "severity": "medium",
        },
        {"road": "Av. Berthelot", "lat": 45.7450, "lon": 4.8501, "speed_kmh": 22, "delay_min": 3, "severity": "low"},
        {
            "road": "Périphérique Nord",
            "lat": 45.7890,
            "lon": 4.8820,
            "speed_kmh": 35,
            "delay_min": 2,
            "severity": "low",
        },
    ],
    "predictions": {
        "h_plus_30min": {"average_speed_kmh": 19, "congestion_level": "dense"},
        "h_plus_1h": {"average_speed_kmh": 24, "congestion_level": "modéré"},
        "h_plus_3h": {"average_speed_kmh": 38, "congestion_level": "fluide"},
    },
    "data_source": "mock",
}


# -----------------------------------------------------------------------------
# Favoris
# -----------------------------------------------------------------------------
MOCK_FAVORITES = [
    {
        "id": "fav_1",
        "name": "🏠 Maison → 💼 Boulot",
        "origin": "Villeurbanne",
        "destination": "Part-Dieu",
        "usual_mode": "M A",
        "usual_duration_min": 22,
        "next_departure": "08:42",
        "alert_subscribed": True,
    },
    {
        "id": "fav_2",
        "name": "💼 Boulot → 🏠 Maison",
        "origin": "Part-Dieu",
        "destination": "Villeurbanne",
        "usual_mode": "M A",
        "usual_duration_min": 22,
        "next_departure": "18:15",
        "alert_subscribed": True,
    },
    {
        "id": "fav_3",
        "name": "🏠 Maison → 🛒 Carrefour",
        "origin": "Villeurbanne",
        "destination": "Bron",
        "usual_mode": "C17",
        "usual_duration_min": 35,
        "next_departure": "10:30",
        "alert_subscribed": False,
    },
    {
        "id": "fav_4",
        "name": "💼 Boulot → 🏋️ Salle de sport",
        "origin": "Part-Dieu",
        "destination": "Confluence",
        "usual_mode": "T1",
        "usual_duration_min": 18,
        "next_departure": "19:20",
        "alert_subscribed": True,
    },
]


# -----------------------------------------------------------------------------
# Mock data pour les requêtes DB Gold (fallback offline)
# -----------------------------------------------------------------------------
# Ces structures miment la sortie de src.data.db_query quand la DB est down.
# Elles permettent aux widgets de s'afficher correctement en dev / démo.

_NOW = datetime.now(UTC)


def _gen_traffic_features(n: int = 100) -> list[dict]:
    """Génère N mesures trafic réalistes pour fallback."""
    base_time = _NOW
    nodes = [
        (1, "Cours Lafayette", 1, "high"),
        (2, "Quai Claude Bernard", 2, "medium"),
        (3, "Av. Berthelot", 3, "low"),
        (4, "Périphérique Nord", 4, "low"),
        (5, "Pont de la Guillotière", 5, "high"),
        (6, "Rue de la République", 6, "medium"),
        (7, "Av. Jean Jaurès", 7, "low"),
        (8, "Cours Vitton", 8, "low"),
    ]
    rows = []
    for i in range(n):
        node_idx, _road, ch, imp = nodes[i % len(nodes)]
        ts = base_time - timedelta(minutes=5 * i)
        speed = max(5.0, 45.0 - (i % 12) * 2.5 + (i % 3) * 1.2)
        rows.append(
            {
                "measurement_time": ts,
                "node_idx": node_idx,
                "channel_id": f"CH_{ch:04d}",
                "speed_kmh": round(speed, 2),
                "importance_code": imp,
            }
        )
    return rows


MOCK_TRAFFIC_FEATURES: list[dict] = _gen_traffic_features(100)
"""Mesures trafic pour fallback db_query.get_latest_traffic."""


MOCK_TRAFFIC_TIMESERIES: list[dict] = [
    {
        "measurement_time": _NOW - timedelta(minutes=5 * i),
        "speed_kmh": 35.0 + (i % 7) * 1.5,
        "speed_lag_1": 33.0 + (i % 5) * 1.2,
        "speed_lag_2": 32.0 + (i % 4) * 1.0,
        "speed_delta_1": 2.0 + (i % 3) * 0.3,
        "rolling_mean_5min": 34.0 + (i % 6) * 1.1,
        "hour_sin": 0.5,
        "hour_cos": 0.866,
        "temperature_c": 18.0,
        "rain_mm": 0.0,
        "is_vacances": False,
    }
    for i in range(48)
]
"""Time series trafic pour un nœud (48 * 5min = 4h)."""


MOCK_VELOV_STATIONS_GEO: list[dict] = [
    {
        "station_id": f"VELOV_{i:04d}",
        "station_name": f"Station {i}",
        "bikes_available": 5 + (i * 3) % 18,
        "docks_available": 25 - (i * 3) % 18,
        "lat": 45.75 + (i % 10) * 0.005,
        "lng": 4.83 + (i % 10) * 0.005,
        "is_operational": True,
    }
    for i in range(1, 31)
]
"""30 stations Vélov mock pour get_velov_stations_geo."""


MOCK_TRAFIC_PREDICTIONS: list[dict] = [
    {
        "prediction_timestamp": _NOW,
        "target_timestamp": _NOW + timedelta(minutes=60),
        "horizon_minutes": 60,
        "node_idx": (i % 8) + 1,
        "model_name": "xgboost" if i % 2 == 0 else "stgcn",
        "model_version": "v1.0",
        "predicted_speed": round(30.0 + (i % 12), 2),
        "confidence_low": round(25.0 + (i % 12), 2),
        "confidence_high": round(35.0 + (i % 12), 2),
        "actual_speed": None,
    }
    for i in range(50)
]
"""Prédictions trafic pour fallback get_traffic_predictions."""


MOCK_BUS_DELAYS: list[dict] = [
    {
        "date": (_NOW - timedelta(days=i % 7)).date(),
        "hour": i % 24,
        "line_ref": ["C3", "C13", "C14", "T1", "T2"][i % 5],
        "segment_id": f"SEG_{i:04d}",
        "avg_delay_seconds": 30.0 + (i * 7) % 180,
        "n_observations": 5 + (i % 10),
    }
    for i in range(40)
]
"""Retards bus agrégés pour fallback get_bus_delay_segments."""


MOCK_INFRA_BOTTLENECKS: list[dict] = [
    {
        "bottleneck_id": i + 1,
        "segment_id": f"SEG_{i:04d}",
        "line_refs": [["C3", "13"], ["T1"], ["C14"]][i % 3],
        "diagnosis": ["infra", "operations", "bus_lane_ok", "ok"][i % 4],
        "impact_score": round(8.5 - (i * 0.3), 2),
        "voyageurs_jour": 5000 + (i * 1500) % 30000,
        "lat": 45.75 + (i % 10) * 0.005,
        "lng": 4.83 + (i % 10) * 0.005,
    }
    for i in range(15)
]
"""Bottlenecks infrastructure pour fallback get_infrastructure_bottlenecks."""


MOCK_RGPD_AUDIT: list[dict] = [
    {
        "event_time": _NOW - timedelta(hours=i),
        "actor": f"user_{i % 5}",
        "action": ["login", "data_access", "consent_update", "dsr_request"][i % 4],
        "resource_type": ["user", "report", "consent", "dsr"][i % 4],
        "resource_id": f"res_{i:04d}",
        "ip_address": f"10.0.0.{i % 255}",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    }
    for i in range(20)
]
"""Audit log RGPD pour fallback get_rgpd_audit_log."""


MOCK_BRONZE_COUNTS: list[dict] = [
    {
        "source": "Grand Lyon boucles (pvotrafic)",
        "table": "bronze.trafic_boucles",
        "n_rows": 12_400,
        "last_fetch": _NOW - timedelta(minutes=2),
    },
    {"source": "Vélo'v GBFS", "table": "bronze.velov", "n_rows": 458, "last_fetch": _NOW - timedelta(minutes=3)},
    {
        "source": "TCL SIRI Lite",
        "table": "bronze.tcl_vehicles",
        "n_rows": 587,
        "last_fetch": _NOW - timedelta(minutes=4),
    },
    {"source": "Open-Meteo weather", "table": "bronze.meteo", "n_rows": 24, "last_fetch": _NOW - timedelta(minutes=8)},
    {
        "source": "Open-Meteo air quality",
        "table": "bronze.air_quality",
        "n_rows": 7,
        "last_fetch": _NOW - timedelta(minutes=10),
    },
    {
        "source": "Grand Lyon chantiers",
        "table": "bronze.chantiers",
        "n_rows": 345,
        "last_fetch": _NOW - timedelta(hours=3),
    },
]
"""Counts des sources Bronze pour fallback get_bronze_source_counts."""


MOCK_TRAFFIC_BOTTLENECKS: list[dict] = [
    {
        "node_idx": i + 1,
        "channel_id": f"CH_{(i % 8) + 1:04d}",
        "avg_speed": round(8.0 + (i * 0.7), 2),
        "min_speed": round(3.0 + (i * 0.3), 2),
        "observations": 12 + (i % 10),
    }
    for i in range(20)
]
"""Top 20 nœuds congestionnés pour fallback get_traffic_bottlenecks."""


MOCK_PREDICTIONS_VS_ACTUALS: list[dict] = [
    {
        "horizon_minutes": [5, 15, 30, 60, 180, 360][i % 6],
        "model_name": ["xgboost", "stgcn"][i % 2],
        "predicted_speed": round(30.0 + (i % 12), 2),
        "actual_speed": round(31.0 + (i % 11), 2),
        "error_kmh": round((i % 5) - 2, 2),
        "error_pct": round(((i % 10) - 5) * 0.5, 2),
    }
    for i in range(100)
]
"""Comparaisons prédictions vs réalité pour fallback get_predictions_vs_actuals."""


MOCK_RGPD_DSR: list[dict] = [
    {
        "request_id": f"dsr-{i:04d}",
        "user_identifier": f"user_{i:04d}",
        "request_type": ["access", "deletion", "portability", "rectification"][i % 4],
        "status": ["pending", "in_progress", "completed", "rejected"][i % 4],
        "requested_at": _NOW - timedelta(days=i % 30),
        "completed_at": _NOW - timedelta(days=i % 30, hours=-12) if i % 2 == 0 else None,
        "notes": f"Auto-generated DSR {i}",
    }
    for i in range(15)
]
"""DSR RGPD pour fallback get_rgpd_data_subject_requests."""


MOCK_RGPD_PURGE: list[dict] = [
    {
        "schema_name": schema,
        "table_name": table,
        "rows_purged": 1000 + (i * 500),
        "retention_days": 30,
        "purged_at": _NOW - timedelta(days=i % 30),
    }
    for i, (schema, table) in enumerate(
        [
            ("bronze", "trafic_boucles"),
            ("bronze", "velov"),
            ("bronze", "tcl_vehicles"),
            ("bronze", "meteo"),
        ]
    )
]
"""Historique purges RGPD pour fallback get_rgpd_purge_history."""


MOCK_RGPD_CONSENTS_SUMMARY: list[dict] = [
    {"consent_type": "analytics", "granted_count": 142, "denied_count": 28, "total": 170},
    {"consent_type": "tracking", "granted_count": 89, "denied_count": 81, "total": 170},
    {"consent_type": "marketing", "granted_count": 51, "denied_count": 119, "total": 170},
    {"consent_type": "all", "granted_count": 38, "denied_count": 132, "total": 170},
]
"""Summary des consents pour fallback get_rgpd_consents_summary."""


MOCK_SPATIAL_MAPPING: list[dict] = [
    {
        "node_idx": i + 1,
        "channel_id": f"CH_{(i % 8) + 1:04d}",
        "matrix_i": (i % 8),
        "matrix_j": (i // 8),
        "h3_id": f"8c2ba4{i:08x}",
        "lat": 45.75 + (i % 10) * 0.005,
        "lng": 4.83 + (i // 10) * 0.005,
    }
    for i in range(20)
]
"""Mapping spatial pour fallback get_spatial_mapping (20 nœuds mock)."""


MOCK_GNN_ADJACENCY: list[dict] = [
    {"node_u": i + 1, "node_v": (i + 1) % 20 + 1, "is_connected": True, "distance_m": 100.0 + (i * 50) % 500}
    for i in range(40)
]
"""Arêtes GNN pour fallback get_gnn_adjacency (K=2 grid_disk simplifié)."""


MOCK_VELOV_PREDICTIONS: list[dict] = [
    {
        "prediction_timestamp": _NOW,
        "target_timestamp": _NOW + timedelta(minutes=horizon),
        "horizon_minutes": horizon,
        "station_id": f"VELOV_{i:04d}",
        "station_id_encoded": i,
        "predicted_bikes": 5 + (i * 3) % 18,
        "confidence_low": max(0, 5 + (i * 3) % 18 - 3),
        "confidence_high": 5 + (i * 3) % 18 + 3,
    }
    for horizon in (30, 60)
    for i in range(50)
]
"""Prédictions Vélov pour fallback get_velov_predictions."""


# Météo — déjà MOCK_WEATHER plus haut (24h forecast). On ajoute aussi
# le format hourly pour matcher get_weather_hourly()
MOCK_WEATHER_HOURLY: list[dict] = [
    {
        "measurement_time": _NOW - timedelta(hours=i),
        "temperature_c": 18.0 - (i % 8) * 0.5,
        "rain_mm": 0.0 if i % 4 else 1.5,
        "wind_kmh": 12.0 + (i % 5) * 1.2,
        "humidity_pct": 60 + (i % 7) * 3,
        "condition_label": ["Ensoleillé", "Nuageux", "Pluvieux", "Brouillard"][i % 4],
    }
    for i in range(24)
]
"""Météo horaire pour fallback get_weather_hourly (24h)."""


# Adresses mock Lyon — déjà LyonAddresses plus haut, on garde pour le data_loader
LYON_ADDRESSES_MOCK: list[str] = [
    "Part-Dieu, Lyon",
    "Place Bellecour, Lyon",
    "Hôtel de Ville, Lyon",
    "Vieux Lyon",
    "Presqu'île, Lyon",
    "Confluence, Lyon",
    "Croix-Rousse, Lyon",
    "Place des Terreaux, Lyon",
    "Opéra, Lyon",
    "Parc de la Tête d'Or, Lyon",
    "Université Lyon 3, Lyon",
    "Place Jean Macé, Lyon",
    "Saxe-Gambetta, Lyon",
    "Guillotière, Lyon",
    "Mermoz, Lyon",
    "Monplaisir, Lyon",
    "Gerland, Lyon",
    "Vaise, Lyon",
]
