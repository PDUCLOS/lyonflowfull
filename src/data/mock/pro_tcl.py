"""Mock data Lyon pour le persona Pro TCL.

Données réalistes : 10 lignes TCL, 5 segments/ligne, OTP 7j×24h, KPIs.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

_NOW = datetime.now(UTC)

# -----------------------------------------------------------------------------
# 10 lignes TCL
# -----------------------------------------------------------------------------
TCL_LINES_PRO = [
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
]

# -----------------------------------------------------------------------------
# Segments par ligne (5 par ligne) avec classification bus × trafic
# -----------------------------------------------------------------------------
SEGMENTS_DATA = [
    # (line_id, segment_name, lat, lon, bus_state, traffic_state, diagnosis)
    ("C3", "Part-Dieu → Saxe", 45.7607, 4.8589, "delayed", "jammed", "infra"),
    ("C3", "Saxe → Place Guichard", 45.7496, 4.8461, "delayed", "fluid", "operations"),
    ("C3", "Guichard → Jean Macé", 45.7456, 4.8417, "on_time", "fluid", "ok"),
    ("C3", "Jean Macé → Guillotière", 45.7431, 4.8408, "delayed", "jammed", "infra"),
    ("C3", "Guillotière → Terminus", 45.7324, 4.8325, "on_time", "jammed", "bus_lane_ok"),

    ("C13", "Vaise → Gorge de Loup", 45.7798, 4.8058, "on_time", "fluid", "ok"),
    ("C13", "Gorge de Loup → Échangeur", 45.7722, 4.8059, "delayed", "jammed", "infra"),
    ("C13", "Échangeur → Terreaux", 45.7673, 4.8343, "on_time", "fluid", "ok"),
    ("C13", "Terreaux → Hôtel de Ville", 45.7672, 4.8342, "delayed", "jammed", "infra"),
    ("C13", "Hôtel de Ville → Part-Dieu", 45.7622, 4.8462, "delayed", "jammed", "infra"),

    ("T1", "Hôtel de Ville → Perrache", 45.7672, 4.8342, "delayed", "jammed", "infra"),
    ("T1", "Perrache → Confluence", 45.7405, 4.8165, "on_time", "fluid", "ok"),
    ("T1", "Debourg → Mermoz", 45.7324, 4.8545, "on_time", "jammed", "bus_lane_ok"),
    ("T1", "Mermoz → Université", 45.7310, 4.8700, "delayed", "jammed", "infra"),
    ("T1", "Université → La Doua", 45.7800, 4.8800, "on_time", "fluid", "ok"),

    ("T3", "Part-Dieu → Villette", 45.7607, 4.8589, "on_time", "jammed", "bus_lane_ok"),
    ("T3", "Villette → Mermoz", 45.7310, 4.8700, "delayed", "fluid", "operations"),
    ("T3", "Mermoz → Bachut", 45.7290, 4.8700, "delayed", "jammed", "infra"),
    ("T3", "Bachut → Meyzieu", 45.7680, 4.9890, "on_time", "fluid", "ok"),
    ("T3", "Meyzieu → Terminus", 45.7690, 5.0030, "on_time", "fluid", "ok"),

    ("M_A", "Perrache → Ampère", 45.7480, 4.8340, "on_time", "fluid", "ok"),
    ("M_A", "Ampère → Bellecour", 45.7575, 4.8324, "on_time", "fluid", "ok"),
    ("M_A", "Bellecour → Hôtel de Ville", 45.7672, 4.8342, "on_time", "jammed", "ok"),
    ("M_A", "Hôtel de Ville → Foch", 45.7693, 4.8369, "on_time", "fluid", "ok"),
    ("M_A", "Foch → Part-Dieu", 45.7607, 4.8589, "delayed", "jammed", "infra"),
]

SEGMENTS = [
    {
        "line_id": s[0],
        "name": s[1],
        "lat": s[2],
        "lon": s[3],
        "bus_state": s[4],
        "traffic_state": s[5],
        "diagnosis": s[6],
        "delay_min": random.randint(0, 12) if s[4] == "delayed" else 0,
    }
    for s in SEGMENTS_DATA
]

# Couleurs par diagnostic
DIAGNOSIS_COLORS = {
    "ok": "#4CAF50",
    "infra": "#E74C3C",      # rouge — bottleneck infrastructure
    "operations": "#FF9800", # orange — problème exploitation
    "bus_lane_ok": "#2196F3" # bleu — voie bus fonctionne
}

DIAGNOSIS_LABELS = {
    "ok": "✅ OK",
    "infra": "🔴 Infrastructure",
    "operations": "🟡 Exploitation",
    "bus_lane_ok": "🔵 Voie bus OK",
}


# -----------------------------------------------------------------------------
# OTP par ligne × heure (7 jours × 24h)
# -----------------------------------------------------------------------------
def _generate_otp_grid(line_id: str, base_otp: float) -> dict:
    """Génère une grille OTP ligne × heure sur 7 jours."""
    random.seed(hash(line_id) % 1000)
    grid = {}
    for day_offset in range(7):
        date = (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        grid[date] = []
        for hour in range(24):
            # Heures de pointe : OTP plus bas
            if 7 <= hour <= 9 or 17 <= hour <= 19:
                otp = base_otp - random.uniform(5, 15)
            elif 10 <= hour <= 16:
                otp = base_otp - random.uniform(0, 5)
            else:
                otp = base_otp - random.uniform(0, 2)
            otp = max(60.0, min(98.0, otp))
            grid[date].append(round(otp, 1))
    return grid


# OTP moyen par ligne (entre 75% et 92%)
LINE_BASE_OTP = {
    "M_A": 91.5, "M_B": 89.8, "M_C": 87.2, "M_D": 85.4,
    "T1": 82.3, "T2": 84.1, "T3": 79.6, "T6": 86.7,
    "C3": 76.4, "C13": 78.9,
}

OTP_GRID = {line_id: _generate_otp_grid(line_id, base_otp)
            for line_id, base_otp in LINE_BASE_OTP.items()}


# -----------------------------------------------------------------------------
# KPIs par ligne
# -----------------------------------------------------------------------------
def _generate_line_kpis(line_id: str) -> dict:
    base = LINE_BASE_OTP.get(line_id, 85.0)
    random.seed(hash(line_id + "kpi") % 1000)
    return {
        "line_id": line_id,
        "otp_pct": round(base + random.uniform(-2, 2), 1),
        "avg_delay_min": round(random.uniform(0.5, 4.5), 1),
        "frequency_min": random.choice([3, 4, 5, 6, 7, 8, 10]),
        "load_pct": round(random.uniform(35, 92), 0),
        "trend": random.choice(["up", "down", "stable"]),
        "trend_delta": round(random.uniform(-3, 3), 1),
    }


LINE_KPIS = {line_id: _generate_line_kpis(line_id) for line_id in LINE_BASE_OTP}


# -----------------------------------------------------------------------------
# Bus positions (mock pour network_map)
# -----------------------------------------------------------------------------
def _generate_bus_positions(line_id: str, n_buses: int = 5) -> list:
    """Génère N positions de bus pour une ligne."""
    line_segs = [s for s in SEGMENTS if s["line_id"] == line_id]
    if not line_segs:
        return []
    random.seed(hash(line_id + "buses") % 1000)
    buses = []
    for i in range(n_buses):
        seg = random.choice(line_segs)
        delay = random.randint(0, 8) if random.random() < 0.4 else 0
        buses.append({
            "bus_id": f"{line_id}_BUS_{i+1:03d}",
            "line_id": line_id,
            "lat": seg["lat"] + random.uniform(-0.005, 0.005),
            "lon": seg["lon"] + random.uniform(-0.005, 0.005),
            "delay_min": delay,
            "segment": seg["name"],
        })
    return buses


ALL_BUSES = []
for line_id in LINE_BASE_OTP:
    ALL_BUSES.extend(_generate_bus_positions(line_id, n_buses=6))


# -----------------------------------------------------------------------------
# Alertes prédites (Ticker PCC)
# -----------------------------------------------------------------------------
PREDICTED_ALERTS = [
    {
        "id": "pred_1",
        "line": "T3",
        "line_icon": "🚊",
        "line_color": "#9B59B6",
        "type": "predicted_delay",
        "severity": "warning",
        "title": "T3 La Doua — ralentissement attendu 17h35",
        "predicted_at": "17:35",
        "intensity": 7,
        "description": "Bouchon secteur La Doua → Bachut (12 min de retard prévues)",
        "recommendation": "Renforcer fréquence T3 entre 17h20 et 17h50",
    },
    {
        "id": "pred_2",
        "line": "C13",
        "line_icon": "🚌",
        "line_color": "#1ABC9C",
        "type": "predicted_saturation",
        "severity": "warning",
        "title": "C13 saturation prévue 17h42",
        "predicted_at": "17:42",
        "intensity": 8,
        "description": "Charge >95% prévue sur Hôtel de Ville → Part-Dieu",
        "recommendation": "Activer M B en doublure sur le tronçon",
    },
    {
        "id": "pred_3",
        "line": "T1",
        "line_icon": "🚊",
        "line_color": "#FFCD00",
        "type": "bottleneck",
        "severity": "critical",
        "title": "Bottleneck Rue Garibaldi — incident détecté",
        "predicted_at": "maintenant",
        "intensity": 9,
        "description": "4 lignes impactées (T1, C3, C13, M D)",
        "recommendation": "Couloir bus dédié — ROI 18 mois",
    },
    {
        "id": "pred_4",
        "line": "M_A",
        "line_icon": "🚇",
        "line_color": "#E2001A",
        "type": "predicted_delay",
        "severity": "info",
        "title": "M_A — affluence exceptionnelle Hôtel de Ville",
        "predicted_at": "18:05",
        "intensity": 5,
        "description": "Sortie de conférence Centre Congrès",
        "recommendation": "Préparer plan de délestage",
    },
]


# -----------------------------------------------------------------------------
# Top bottlenecks (vue PCC Live)
# -----------------------------------------------------------------------------
TOP_BOTTLENECKS = [
    {"rank": 1, "zone": "Rue Garibaldi", "lines": ["T1", "C3", "C13", "M_D"],
     "voyageurs_jour": 120000, "gain_min": 7, "cout_M_euros": 2.3, "roi_mois": 18},
    {"rank": 2, "zone": "Cours Lafayette", "lines": ["T1", "C3"],
     "voyageurs_jour": 85000, "gain_min": 4, "cout_M_euros": 1.1, "roi_mois": 12},
    {"rank": 3, "zone": "Carrefour Part-Dieu", "lines": ["T1", "T3", "T4", "C3"],
     "voyageurs_jour": 210000, "gain_min": 12, "cout_M_euros": 4.5, "roi_mois": 24},
    {"rank": 4, "zone": "Quai Claude Bernard", "lines": ["T1", "C5", "C18"],
     "voyageurs_jour": 62000, "gain_min": 3, "cout_M_euros": 1.8, "roi_mois": 15},
    {"rank": 5, "zone": "Av. Berthelot", "lines": ["T2", "C12"],
     "voyageurs_jour": 48000, "gain_min": 2, "cout_M_euros": 1.1, "roi_mois": 12},
]


# Sprint 8 — Fallbacks pour data_loader

MOCK_RECENT_ALERTS: list[dict] = [
    {
        "alert_id": f"alert_{i:04d}",
        "alert_time": _NOW - timedelta(minutes=10 * i),
        "severity": ["high", "medium", "low", "info"][i % 4],
        "line_ref": ["M_A", "M_B", "T1", "C3", "C13"][i % 5],
        "title": f"Alerte #{i}",
        "description": f"Description de l'alerte #{i}",
        "action": f"Action recommandée #{i}",
    }
    for i in range(20)
]
"""Alertes récentes pour fallback get_recent_alerts."""


MOCK_SEGMENTS: list[dict] = [
    {
        "segment_id": f"SEG_{i:04d}",
        "channel_id": f"CH_{(i % 8) + 1:04d}",
        "importance_code": ["high", "medium", "low"][i % 3],
        "longueur_m": 200 + (i * 37) % 800,
        "lat_start": 45.75 + (i % 10) * 0.005,
        "lng_start": 4.83 + (i // 10) * 0.005,
        "lat_end": 45.75 + (i % 10) * 0.005 + 0.002,
        "lng_end": 4.83 + (i // 10) * 0.005 + 0.003,
    }
    for i in range(50)
]
"""Segments routiers pour fallback get_segments."""


MOCK_CORRELATION_MATRIX: list[dict] = [
    {
        "feature_x": ["speed_kmh", "temperature_c", "rain_mm", "hour_sin"][i % 4],
        "feature_y": ["hour_cos", "speed_lag_1", "is_vacances", "rolling_mean_5min"][i % 4],
        "correlation": round(((i * 13) % 100) / 100.0 - 0.5, 3),
        "p_value": 0.01 + (i % 10) * 0.005,
        "n_samples": 1000 + i * 50,
    }
    for i in range(40)
]
"""Matrice de corrélation pour fallback get_correlation_matrix."""


MOCK_BUSES_POSITIONS: list[dict] = [
    {
        "vehicle_ref": f"BUS_{i:04d}",
        "line_ref": ["C3", "C13", "C14", "T1", "T2"][i % 5],
        "lat": 45.75 + (i % 20) * 0.002,
        "lng": 4.83 + (i // 20) * 0.002,
        "bearing": (i * 37) % 360,
        "delay_seconds": (i * 7) % 120 - 30,
        "recorded_at": _NOW - timedelta(seconds=i * 5),
    }
    for i in range(50)
]
"""Positions temps réel bus pour fallback get_buses_positions."""


MOCK_TCL_LINES: list[dict] = [
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
"""Lignes TCL pour le sélecteur de ligne."""
