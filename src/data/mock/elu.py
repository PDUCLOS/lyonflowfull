"""Mock data pour le persona Élu.

KPIs 12 mois, 10 bottlenecks, aménagements passés, projets planifiés.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# -----------------------------------------------------------------------------
# 5 KPIs sur 12 mois glissants
# -----------------------------------------------------------------------------
KPI_12_MONTHS = {
    "part_modale_tc": {
        "label": "Part modale transports en commun",
        "unit": "%",
        "current": 32.0,
        "delta_ytd": 1.4,
        "target_2026": 35.0,
        "history": [29.8, 30.1, 30.4, 30.5, 30.7, 30.8, 31.0, 31.2, 31.5, 31.7, 31.9, 32.0],
    },
    "ponctualite_reseau": {
        "label": "Ponctualité réseau TCL",
        "unit": "%",
        "current": 87.0,
        "delta_ytd": -0.3,
        "target_2026": 90.0,
        "history": [88.2, 88.0, 87.9, 87.7, 87.5, 87.4, 87.3, 87.2, 87.1, 87.0, 87.0, 87.0],
    },
    "co2_evite": {
        "label": "CO₂ évité (tonnes/an)",
        "unit": "t",
        "current": 12400,
        "delta_ytd": 8.0,
        "target_2026": 18000,
        "history": [9800, 10100, 10400, 10800, 11100, 11400, 11600, 11800, 12000, 12200, 12300, 12400],
    },
    "bottlenecks_actifs": {
        "label": "Bottlenecks actifs",
        "unit": "",
        "current": 14,
        "delta_ytd": -4,
        "target_2026": 8,
        "history": [22, 21, 20, 19, 18, 18, 17, 16, 16, 15, 14, 14],
    },
    "satisfaction_usager": {
        "label": "Satisfaction usager (/10)",
        "unit": "/10",
        "current": 7.2,
        "delta_ytd": 0.1,
        "target_2026": 7.8,
        "history": [6.8, 6.9, 7.0, 7.0, 7.0, 7.1, 7.1, 7.1, 7.1, 7.2, 7.2, 7.2],
    },
}


# -----------------------------------------------------------------------------
# 10 Bottlenecks avec ROI
# -----------------------------------------------------------------------------
BOTTLENECKS_TOP_10 = [
    {
        "rank": 1,
        "zone": "Rue Garibaldi",
        "lines_impacted": ["T1", "C3", "C13", "M D"],
        "voyageurs_jour": 120000,
        "gain_min": 7,
        "cout_M_euros": 2.3,
        "description": "Couloir bus dédié entre Saxe et Part-Dieu + feu tricolores prioritaires",
        "delai_mois": 6,
    },
    {
        "rank": 2,
        "zone": "Cours Lafayette",
        "lines_impacted": ["T1", "C3"],
        "voyageurs_jour": 85000,
        "gain_min": 4,
        "cout_M_euros": 1.1,
        "description": "Voie de bus en site propre entre Place Guichard et Part-Dieu",
        "delai_mois": 4,
    },
    {
        "rank": 3,
        "zone": "Carrefour Part-Dieu",
        "lines_impacted": ["T1", "T3", "T4", "C3"],
        "voyageurs_jour": 210000,
        "gain_min": 12,
        "cout_M_euros": 8.5,
        "description": "Réaménagement carrefour + passage souterrain bus",
        "delai_mois": 18,
    },
    {
        "rank": 4,
        "zone": "Quai Claude Bernard",
        "lines_impacted": ["T1", "C5", "C18"],
        "voyageurs_jour": 62000,
        "gain_min": 3,
        "cout_M_euros": 1.8,
        "description": "Piste cyclable + voie bus sur le quai",
        "delai_mois": 8,
    },
    {
        "rank": 5,
        "zone": "Av. Berthelot",
        "lines_impacted": ["T2", "C12"],
        "voyageurs_jour": 48000,
        "gain_min": 2,
        "cout_M_euros": 1.1,
        "description": "Piste cyclable bidirectionnelle + recalibrage chaussée",
        "delai_mois": 5,
    },
    {
        "rank": 6,
        "zone": "Cours Vitton",
        "lines_impacted": ["C6", "C11"],
        "voyageurs_jour": 38000,
        "gain_min": 3,
        "cout_M_euros": 0.9,
        "description": "Couloir bus partagé avec vélos (Pays-Bas style)",
        "delai_mois": 4,
    },
    {
        "rank": 7,
        "zone": "Pont Lafayette",
        "lines_impacted": ["C3", "C13", "C14"],
        "voyageurs_jour": 72000,
        "gain_min": 5,
        "cout_M_euros": 2.7,
        "description": "Restructuration des voies + priorisation bus aux feux",
        "delai_mois": 10,
    },
    {
        "rank": 8,
        "zone": "Place Bellecour",
        "lines_impacted": ["M A", "M C", "T1", "T2"],
        "voyageurs_jour": 95000,
        "gain_min": 4,
        "cout_M_euros": 3.2,
        "description": "Reconfiguration accès métro + piétonnisation partielle",
        "delai_mois": 12,
    },
    {
        "rank": 9,
        "zone": "Av. Jean Jaurès",
        "lines_impacted": ["C7", "C25"],
        "voyageurs_jour": 28000,
        "gain_min": 2,
        "cout_M_euros": 0.7,
        "description": "Voie bus + aménagement cyclable",
        "delai_mois": 4,
    },
    {
        "rank": 10,
        "zone": "Gare de Vaise",
        "lines_impacted": ["M D", "C14", "C6"],
        "voyageurs_jour": 41000,
        "gain_min": 3,
        "cout_M_euros": 1.5,
        "description": "Pôle d'échanges multimodal (PEM) — réaménagement accès bus",
        "delai_mois": 14,
    },
]


def _compute_roi(b: dict) -> float:
    """Calcule le ROI en mois : coût (M€) × 1M / (gain voyageurs × valeur temps).

    Hypothèse conservatrice : valeur du temps = 12€/h, 1 trajet/jour
    (les bilans are round-trip mais on compte 1× le gain car l'usager
    bénéficie du gain dans un seul sens en moyenne), 250 jours ouvrés/an.
    ROI en mois = coût / gain_annuel × 12
    """
    valeur_temps_h = 12.0
    gain_annuel = (
        b["voyageurs_jour"]
        * (b["gain_min"] / 60)
        * valeur_temps_h
        * 1  # gain sur 1 trajet (aller)
        * 250  # jours ouvrés/an
    )
    cout = b["cout_M_euros"] * 1_000_000
    if gain_annuel == 0:
        return 999
    return round(cout / gain_annuel * 12, 0)


# Calculer ROI pour tous les bottlenecks
for b in BOTTLENECKS_TOP_10:
    b["roi_mois"] = _compute_roi(b)


# -----------------------------------------------------------------------------
# 5 aménagements passés (avant/après)
# -----------------------------------------------------------------------------
AMENAGEMENTS_PASSES = [
    {
        "id": "bonnel_2023",
        "nom": "Couloir bus Rue de Bonnel",
        "annee": 2023,
        "cout_M_euros": 1.8,
        "avant": {
            "trafic_vp_jour": 12400,
            "frequentation_bus": 8200,
            "ponctualite": 73.0,
            "co2_kg_voy": 1.2,
        },
        "apres": {
            "trafic_vp_jour": 9800,
            "frequentation_bus": 11400,
            "ponctualite": 87.0,
            "co2_kg_voy": 0.8,
        },
    },
    {
        "id": "garibaldi_2024",
        "nom": "Piste cyclable Garibaldi (sud)",
        "annee": 2024,
        "cout_M_euros": 0.6,
        "avant": {
            "trafic_vp_jour": 9200,
            "frequentation_velo": 850,
            "accidents_velo_an": 12,
        },
        "apres": {
            "trafic_vp_jour": 7800,
            "frequentation_velo": 2400,
            "accidents_velo_an": 3,
        },
    },
    {
        "id": "bellecour_2023",
        "nom": "Réaménagement Place Bellecour (accès métro)",
        "annee": 2023,
        "cout_M_euros": 3.2,
        "avant": {
            "frequentation_metraversant": 38000,
            "temps_correspondance_min": 7.5,
        },
        "apres": {
            "frequentation_metraversant": 41500,
            "temps_correspondance_min": 4.2,
        },
    },
    {
        "id": "t6_2025",
        "nom": "Extension Tram T6 (Debourg → Hôpitaux Est)",
        "annee": 2025,
        "cout_M_euros": 18.0,
        "avant": {
            "frequentation_t6": 22000,
            "temps_parcours_min": 28,
        },
        "apres": {
            "frequentation_t6": 34000,
            "temps_parcours_min": 16,
        },
    },
    {
        "id": "zfe_2025",
        "nom": "ZFE (Zone Faibles Émissions) durcissement",
        "annee": 2025,
        "cout_M_euros": 0.4,
        "avant": {
            "vehicules_critair_4_5": 38000,
            "qualite_air_no2": 38,
        },
        "apres": {
            "vehicules_critair_4_5": 12000,
            "qualite_air_no2": 28,
        },
    },
]


# -----------------------------------------------------------------------------
# 5 projets planifiés
# -----------------------------------------------------------------------------
PROJETS_PLANIFIES = [
    {
        "id": "t9_nord",
        "nom": "Tram T9 nord (La Doua → Caluire)",
        "horizon": "2028",
        "cout_M_euros": 145,
        "statut": "Études",
        "voyageurs_attendus_jour": 65000,
    },
    {
        "id": "m_e_prolong",
        "nom": "Prolongement M E (Alaï → Tassin)",
        "horizon": "2030",
        "cout_M_euros": 980,
        "statut": "Concertation",
        "voyageurs_attendus_jour": 95000,
    },
    {
        "id": "poles_multimodaux",
        "nom": "6 pôles d'échanges multimodaux",
        "horizon": "2027",
        "cout_M_euros": 78,
        "statut": "Études",
        "voyageurs_attendus_jour": 180000,
    },
    {
        "id": "voie_bus_pont",
        "nom": "Voie bus Pont Lafayette",
        "horizon": "2026",
        "cout_M_euros": 2.7,
        "statut": "Trvx",
        "voyageurs_attendus_jour": 72000,
    },
    {
        "id": "zfe_v2",
        "nom": "ZFE v2 (Crit'Air 3 inclus)",
        "horizon": "2027",
        "cout_M_euros": 0.8,
        "statut": "Décision",
        "voyageurs_attendus_jour": 0,
    },
]


# -----------------------------------------------------------------------------
# Données pour data_loader (Sprint 6 — binding widgets)
# -----------------------------------------------------------------------------
_NOW = datetime.now(UTC)


SYNTHESIS_DATA: dict = {
    "city": "Lyon",
    "date": _NOW.date().isoformat(),
    "traffic": {
        "average_speed_kmh": 23,
        "congestion_level": "modéré",
        "bottlenecks_count": 14,
    },
    "velov": {
        "stations_operational": 446,
        "stations_total": 458,
        "bikes_available": 1823,
    },
    "bus": {
        "otp_pct": 87.3,
        "delays_count": 23,
        "on_time_count": 158,
    },
    "meteo": {
        "temperature_c": 18,
        "rain_mm": 0.0,
        "condition": "Ensoleillé",
    },
    "air_quality": {
        "pm2_5": 12,
        "pm10": 22,
        "no2": 28,
        "o3": 56,
        "index_label": "Bon",
    },
    "data_source": "mock",
}
"""Indicateurs de synthèse ville pour load_city_synthesis."""


BOTTLENECKS_LIST: list[dict] = [
    {
        "bottleneck_id": i + 1,
        "segment_id": f"SEG_{i:04d}",
        "road_name": ["Cours Lafayette", "Pont de la Guillotière", "Av. Berthelot",
                       "Quai Claude Bernard", "Cours Vitton", "Rue de la République",
                       "Périphérique Nord", "Cours Gambetta"][i % 8],
        "congestion_level": ["dense", "bloqué", "modéré", "dense", "fluide"][i % 5],
        "impact_score": round(8.5 - (i * 0.3), 2),
        "lat": 45.75 + (i % 10) * 0.005,
        "lng": 4.83 + (i // 10) * 0.005,
    }
    for i in range(20)
]
"""Bottlenecks résumé pour load_bottlenecks_summary."""


# Sprint 8 — Fallbacks pour data_loader

MOCK_KPIS_12_MONTHS_FLAT: list[dict] = []
# Aplatir KPI_12_MONTHS (dict de dicts) en format DataFrame
for kpi_key, kpi_data in {
    "part_modale_tc": 18.5,
    "ponctualite": 87.2,
    "co2_evite_tonnes": 12450,
    "bottlenecks_actifs": 14,
    "satisfaction_pct": 78.3,
}.items():
    for month_idx in range(12):
        MOCK_KPIS_12_MONTHS_FLAT.append(
            {
                "kpi_key": kpi_key,
                "month": (datetime.now(UTC).replace(day=1) - timedelta(days=30 * (11 - month_idx))).date(),
                "value": kpi_data + (month_idx - 6) * 0.5,
                "delta_pct": round((month_idx - 6) * 0.3, 2),
                "target_value": kpi_data * 1.05,
            }
        )


MOCK_AMENAGEMENTS_FLAT: list[dict] = [
    {
        "amenagement_id": i + 1,
        "name": f"Aménagement #{i + 1}",
        "zone": ["Part-Dieu", "Confluence", "Vaise", "Presqu'île", "Gerland"][i % 5],
        "type": ["Piste cyclable", "Bus lane", "Tramway", "Zone piétonne"][i % 4],
        "cout_eur": 250_000 + (i * 87_000) % 2_000_000,
        "date_debut": (datetime.now(UTC) - timedelta(days=365 * (3 - i % 3))).date(),
        "date_fin": (datetime.now(UTC) - timedelta(days=365 * (2 - i % 3))).date(),
        "impact_part_modale_tc": round(1.5 + (i * 0.3) % 5, 1),
        "impact_congestion_pct": round(-8.0 + (i * 1.2) % 10, 1),
        "impact_co2_tonnes_an": 200 + (i * 50) % 1500,
        "description": f"Description aménagement #{i + 1}",
    }
    for i in range(15)
]
