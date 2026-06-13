"""Test e2e Sprint 12+ (2026-06-13) : focus H+1h pour le trafic, H+30min pour le Vélov.

Sprint 12+ — Patrice : "tout en H+30min pour Vélov, les autres H+1h".

- **Trafic** : focus H+1h strict (60 min). Les widgets n'exposent QUE H+1h,
  plus de choix 0/30/60/180/360.
- **Vélov** : focus H+30min (30 min) uniquement. Le widget de carte garde
  un toggle Maintenant / H+30min mais plus de H+1h.
- **Bus** : pas de prédiction unitaire (phase analyse), concerne le trafic.

Sprint 8+ : test historique vérifiait que tout était H+1h.
Sprint 12+ : adaptation — Vélov = H+30min, le reste = H+1h.

Voir `CLAUDE.md` (4 Piliers ML) et `SPRINT_VPS-8_REPORT.md` pour le contexte.
"""

from __future__ import annotations

import inspect
from pathlib import Path

# =============================================================================
# Vélov — H+30min only (Sprint 12+)
# =============================================================================


def test_velov_map_selectbox_h30min_only():
    """Le selectbox horizon du widget velov_map expose uniquement H+30min.

    Sprint 12+ — Vélov n'a plus H+1h. Toggle Maintenant / H+30min uniquement.
    """
    from dashboard.components.widgets.usager.velov_map import render_velov_map

    src = inspect.getsource(render_velov_map)
    # Le selectbox ne doit proposer QUE H+30min (et Maintenant)
    assert '"Prédiction H+30min"' in src, "velov_map doit exposer 'Prédiction H+30min'"
    # Pas d'option H+1h
    assert "Prédiction H+1h" not in src, "velov_map expose encore 'H+1h' — Vélov doit être H+30min only"
    assert "labels = {60:" not in src, "labels Vélov ne doit pas contenir l'option 60 (H+1h)"
    # Plus de pred_60 dans le widget
    assert "pred_60" not in src, "velov_map utilise encore pred_60 (H+1h) — doit être viré"
    # pred_30 doit rester
    assert "predicted_bikes_30" in src, "velov_map doit garder predicted_bikes_30 (H+30min)"


def test_velov_widget_uses_pred_30():
    """velov_widget doit utiliser pred_30 (H+30min) — pas pred_60."""
    from dashboard.components.widgets.usager.velov_widget import render_velov_widget

    src = inspect.getsource(render_velov_widget)
    assert "pred_60" not in src, "velov_widget utilise encore pred_60 (H+1h)"
    assert "pred_30" in src, "velov_widget doit utiliser pred_30 (H+30min)"
    assert "H+30" in src, "velov_widget doit afficher 'H+30min' en UI"


# =============================================================================
# Trafic — H+1h strict (Sprint 8+)
# =============================================================================


def test_traffic_widget_one_card_h1h():
    """traffic_widget affiche 1 seule card prédiction (H+1h), pas 3."""
    from dashboard.components.widgets.usager.traffic_widget import render_traffic_widget

    src = inspect.getsource(render_traffic_widget)
    # Avant : 3 cards (H+30, H+1h, H+3h)
    assert "h_plus_30min" not in src, "traffic_widget expose encore H+30min"
    assert "h_plus_3h" not in src, "traffic_widget expose encore H+3h"
    # Après : 1 card H+1h
    assert "h_plus_1h" in src, "traffic_widget doit afficher H+1h"
    # Format card unique (focus)
    assert "font-size:1.6rem" in src, "Card H+1h doit être plus grosse (focus)"


def test_itinerary_default_h1h():
    """render_itinerary_result a horizon_minutes=60 par défaut (H+1h)."""
    from dashboard.components.widgets.usager.itinerary import render_itinerary_result

    sig = inspect.signature(render_itinerary_result)
    default = sig.parameters["horizon_minutes"].default
    assert default == 60, f"itinerary default doit être 60 (H+1h), trouvé {default}"


def test_gnn_map_horizons_h1h_only():
    """gnn_map._DEFAULT_HORIZONS = (60,) uniquement."""
    from dashboard.components.widgets.pro_tcl.gnn_map import _DEFAULT_HORIZONS

    assert _DEFAULT_HORIZONS == (60,), f"gnn_map._DEFAULT_HORIZONS doit être (60,), trouvé {_DEFAULT_HORIZONS}"


def test_model_monitoring_horizons_h1h_only():
    """model_monitoring.horizons = [60] uniquement (pas 6 horizons)."""
    repo_root = Path(__file__).parents[2]
    with open(repo_root / "dashboard/components/widgets/pro_tcl/model_monitoring.py") as f:
        src_mm = f.read()
    assert "horizons = [60]" in src_mm, "model_monitoring doit utiliser horizons = [60]"
    assert "horizons = [5, 15, 30, 60, 180, 360]" not in src_mm, (
        "model_monitoring expose encore 6 horizons — doit être H+1h only"
    )


def test_usager_mon_trajet_selectbox_h1h():
    """Page Mon Trajet : selectbox horizon = [60] uniquement."""
    repo_root = Path(__file__).parents[2]
    with open(repo_root / "dashboard/pages/Usager_1_Mon_Trajet.py") as f:
        src = f.read()
    assert "[0, 30, 60, 180, 360]" not in src, (
        "Usager_1_Mon_Trajet expose encore [0, 30, 60, 180, 360] — doit être [60]"
    )
    assert "horizon_minutes=60" in src, "Mon Trajet doit appeler render_traffic_map_compact(horizon_minutes=60)"


def test_pro_pcc_live_selectbox_h1h():
    """Page Pro PCC Live : render_traffic_map horizon_default=60."""
    repo_root = Path(__file__).parents[2]
    with open(repo_root / "dashboard/pages/Pro_1_PCC_Live.py") as f:
        src = f.read()
    assert "horizon_default=60" in src, "Pro PCC Live doit utiliser horizon_default=60"
    assert "horizon_default=30" not in src, "Pro PCC Live utilise encore horizon_default=30"


def test_usager_files_h1h():
    """Page Usager_4_Files : load_traffic_predictions_for_map(horizon_minutes=60)."""
    repo_root = Path(__file__).parents[2]
    with open(repo_root / "dashboard/pages/Usager_4_Files.py") as f:
        src = f.read()
    assert "horizon_minutes=60" in src, "Usager_4_Files doit utiliser horizon_minutes=60"
    assert "horizon_minutes=30" not in src or "# Sprint" in src.split("horizon_minutes=30")[0][-200:], (
        "Usager_4_Files utilise encore horizon_minutes=30"
    )


# =============================================================================
# Data cache — Trafic = 60, Vélov = 30 (Sprint 12+)
# =============================================================================


def test_data_cache_defaults_split_h1h_h30min():
    """Sprint 12+ — Trafic = 60, Vélov = 30 (deux politiques différentes)."""
    from dashboard.components.data_cache import (
        cached_traffic_predictions_for_map,
        cached_velov_predictions,
    )

    sig_velov = inspect.signature(cached_velov_predictions)
    sig_traffic = inspect.signature(cached_traffic_predictions_for_map)
    # Vélov = H+30min uniquement
    assert sig_velov.parameters["horizon_minutes"].default == 30, (
        f"cached_velov_predictions default doit être 30 (H+30min), "
        f"trouvé {sig_velov.parameters['horizon_minutes'].default}"
    )
    # Trafic = H+1h strict
    assert sig_traffic.parameters["horizon_minutes"].default == 60, (
        f"cached_traffic_predictions_for_map default doit être 60 (H+1h), "
        f"trouvé {sig_traffic.parameters['horizon_minutes'].default}"
    )
