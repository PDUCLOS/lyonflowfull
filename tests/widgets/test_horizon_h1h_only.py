"""Test e2e Sprint 8+ (2026-06-12) : vérifier que les widgets sont H+1h-only.

Vérifie que tous les widgets et pages dashboard n'exposent QUE H+1h
(60 min) pour les prédictions, conformément à la consigne de
Patrice : "met tout à 1H".

Avant (Sprint 7-) : les sélecteurs proposaient [0, 30, 60, 180, 360]
ou [5, 15, 30, 60, 180, 360] — choix imposé à l'utilisateur.
Après (Sprint 8+) : focus H+1h strict, plus de choix.

Voir `SPRINT_VPS-8_REPORT.md` pour le contexte.
"""

from __future__ import annotations

import inspect


def test_velov_map_selectbox_h1h_only():
    """Le selectbox horizon du widget velov_map expose uniquement H+1h."""
    from dashboard.components.widgets.usager.velov_map import render_velov_map

    src = inspect.getsource(render_velov_map)
    # Le selectbox ne doit proposer QUE H+1h
    assert 'labels = {60: "Prédiction H+1h"}' in src, "velov_map selectbox doit être {60: 'Prédiction H+1h'} uniquement"
    # Pas d'option 0 ou 30 dans le dict labels
    assert "labels = {0:" not in src, "labels ne doit pas contenir l'option 0 (Maintenant)"
    assert "labels = {30:" not in src, "labels ne doit pas contenir l'option 30 (H+30min)"


def test_traffic_widget_one_card_h1h():
    """traffic_widget affiche 1 seule card prédiction (H+1h), pas 3."""
    from dashboard.components.widgets.usager.traffic_widget import render_traffic_widget

    src = inspect.getsource(render_traffic_widget)
    # Avant : 3 cards (H+30, H+1h, H+3h)
    assert "h_plus_30min" not in src, "traffic_widget expose encore H+30min"
    assert "h_plus_3h" not in src, "traffic_widget expose encore H+3h"
    # Après : 1 card H+1h
    assert "h_plus_1h" in src, "traffic_widget doit afficher H+1h"
    # Format card unique
    assert "font-size:1.6rem" in src, "Card H+1h doit être plus grosse (focus)"


def test_velov_widget_uses_pred_60():
    """velov_widget doit utiliser pred_60 (H+1h), pas pred_30 (H+30min)."""
    from dashboard.components.widgets.usager.velov_widget import render_velov_widget

    src = inspect.getsource(render_velov_widget)
    assert "pred_30" not in src, "velov_widget utilise encore pred_30 (H+30min)"
    assert "pred_60" in src, "velov_widget doit utiliser pred_60 (H+1h)"
    assert "H+1h" in src, "velov_widget doit afficher 'H+1h' en UI"


def test_itinerary_default_h1h():
    """render_itinerary_result : H+1h strict (pas de param horizon_minutes — calculé en interne)."""
    from dashboard.components.widgets.usager.itinerary import render_itinerary_result

    sig = inspect.signature(render_itinerary_result)
    # Plus de paramètre horizon_minutes : la requête passe par pgr_ksp qui
    # consomme directement gold.trafic_predictions. Le widget applique
    # implicitement H+1h via compute_itinerary_alternatives().
    assert "horizon_minutes" not in sig.parameters, (
        "render_itinerary_result ne doit plus exposer horizon_minutes — H+1h est strict"
    )
    src = inspect.getsource(render_itinerary_result)
    # Sanity check : aucune référence à 30/180/360 min dans la signature
    for forbidden in ("30,", "180,", "360,"):
        assert forbidden not in src, f"itinerary contient encore {forbidden!r} (autre horizon que H+1h)"


def test_minutes_to_hours_fails_loud():
    """_minutes_to_hours : fail loud si horizon != 60 (règle focus H+1h)."""
    from src.data.db_query import _minutes_to_hours

    # Cas OK
    assert _minutes_to_hours(60) == 1

    # Cas KO : tout autre horizon doit lever ValueError
    for bad in (5, 15, 30, 120, 180, 360):
        try:
            _minutes_to_hours(bad)
        except ValueError as e:
            assert "60" in str(e) and "H+1h" in str(e), f"ValueError message doit mentionner 60/H+1h, got: {e}"
        else:
            raise AssertionError(f"_minutes_to_hours({bad}) aurait dû lever ValueError (règle H+1h strict)")


def test_load_traffic_predictions_h1h_only():
    """data_loader.load_traffic() ne contient plus que H+1h dans le dict predictions."""
    from src.data import data_loader

    src = inspect.getsource(data_loader.load_traffic)
    # Avant : boucle 3 horizons, dict initialisé avec 3 clés
    assert "h_plus_30min" not in src, "load_traffic construit encore h_plus_30min"
    assert "h_plus_3h" not in src, "load_traffic construit encore h_plus_3h"
    assert "(30, " not in src, "load_traffic boucle encore sur (30, ...)"
    assert "(180, " not in src, "load_traffic boucle encore sur (180, ...)"
    # Doit contenir H+1h
    assert "h_plus_1h" in src, "load_traffic doit construire h_plus_1h"
    # Doit calculer la fraîcheur réelle
    assert "freshness_status" in src, "load_traffic doit calculer freshness_status"
    assert "data_age_seconds" in src, "load_traffic doit propager data_age_seconds"


def test_gnn_map_horizons_h1h_only():
    """gnn_map._DEFAULT_HORIZONS = (60,) uniquement."""
    from dashboard.components.widgets.pro_tcl.gnn_map import _DEFAULT_HORIZONS

    assert _DEFAULT_HORIZONS == (60,), f"gnn_map._DEFAULT_HORIZONS doit être (60,), trouvé {_DEFAULT_HORIZONS}"


def test_model_monitoring_horizons_h1h_only():
    """model_monitoring.horizons = [60] uniquement (pas 6 horizons)."""
    with open("/Users/patriceduclos/Documents/Lyonfull/dashboard/components/widgets/pro_tcl/model_monitoring.py") as f:
        src_mm = f.read()
    assert "horizons = [60]" in src_mm, "model_monitoring doit utiliser horizons = [60]"
    assert "horizons = [5, 15, 30, 60, 180, 360]" not in src_mm, (
        "model_monitoring expose encore 6 horizons — doit être H+1h only"
    )


def test_usager_mon_trajet_selectbox_h1h():
    """Page Mon Trajet : selectbox horizon = [60] uniquement."""
    with open("/Users/patriceduclos/Documents/Lyonfull/dashboard/pages/Usager_1_Mon_Trajet.py") as f:
        src = f.read()
    assert "[0, 30, 60, 180, 360]" not in src, (
        "Usager_1_Mon_Trajet expose encore [0, 30, 60, 180, 360] — doit être [60]"
    )
    assert "horizon_minutes=60" in src, "Mon Trajet doit appeler render_traffic_map_compact(horizon_minutes=60)"


def test_pro_pcc_live_selectbox_h1h():
    """Page Pro PCC Live : render_traffic_map horizon_default=60."""
    with open("/Users/patriceduclos/Documents/Lyonfull/dashboard/pages/Pro_1_PCC_Live.py") as f:
        src = f.read()
    assert "horizon_default=60" in src, "Pro PCC Live doit utiliser horizon_default=60"
    assert "horizon_default=30" not in src, "Pro PCC Live utilise encore horizon_default=30"


def test_data_cache_defaults_h1h():
    """cached_velov_predictions et cached_traffic_predictions_for_map defaults = 60."""
    from dashboard.components.data_cache import (
        cached_traffic_predictions_for_map,
        cached_velov_predictions,
    )

    sig1 = inspect.signature(cached_velov_predictions)
    sig2 = inspect.signature(cached_traffic_predictions_for_map)
    assert sig1.parameters["horizon_minutes"].default == 60, (
        f"cached_velov_predictions default doit être 60, trouvé {sig1.parameters['horizon_minutes'].default}"
    )
    assert sig2.parameters["horizon_minutes"].default == 60, (
        f"cached_traffic_predictions_for_map default doit être 60, trouvé {sig2.parameters['horizon_minutes'].default}"
    )
