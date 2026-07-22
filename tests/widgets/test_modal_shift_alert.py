"""Tests unitaires — widget modal_shift_alert (Axe 4, v0.9.0).

Couvre :
* Constantes ANOMALY_Z_THRESHOLD, ALERT_LEVEL_LABELS, ALERT_LEVEL_COLORS.
* _format_z_score : None/NaN, z < seuil, seuil ≤ z < 0, z ≥ 0.
* _count_anomalies : df vide, pas de colonne anomaly_detected, comptage
  des TRUE (anomalies report modal).
* _count_critical_lines : df vide, pas de colonne alert_level, comptage
  des critical et warning (lignes TC en alerte).
"""

from __future__ import annotations

import pandas as pd

from dashboard.components.widgets.pro_tcl.modal_shift_alert import (
    ALERT_LEVEL_COLORS,
    ALERT_LEVEL_LABELS,
    ANOMALY_Z_THRESHOLD,
    _count_anomalies,
    _count_critical_lines,
    _format_z_score,
)

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------


class TestConstants:
    """Cohérence des constantes module-level avec la migration_023."""

    EXPECTED_LEVELS = {"critical", "warning", "ok"}

    def test_seuil_z_score_negatif_2(self) -> None:
        """Le seuil doit être -2.0 (2 écarts-types, convention métier)."""
        assert ANOMALY_Z_THRESHOLD == -2.0

    def test_labels_couvre_3_niveaux(self) -> None:
        assert set(ALERT_LEVEL_LABELS.keys()) == self.EXPECTED_LEVELS

    def test_colors_couvre_3_niveaux(self) -> None:
        assert set(ALERT_LEVEL_COLORS.keys()) == self.EXPECTED_LEVELS

    def test_colors_sont_hex(self) -> None:
        for color in ALERT_LEVEL_COLORS.values():
            assert color.startswith("#") and len(color) == 7
            int(color[1:], 16)

    def test_labels_non_vides(self) -> None:
        for label in ALERT_LEVEL_LABELS.values():
            assert label.strip(), "label vide"


# -----------------------------------------------------------------------------
# _format_z_score
# -----------------------------------------------------------------------------


class TestFormatZScore:
    """Format z-score : rouge si < seuil, jaune si négatif mais >= seuil, vert sinon."""

    def test_none_retourne_tiret(self) -> None:
        assert _format_z_score(None) == "—"

    def test_nan_retourne_tiret(self) -> None:
        assert _format_z_score(float("nan")) == "—"

    def test_z_sous_seuil_rouge(self) -> None:
        """z < -2 → Alerte (anomalie confirmée)."""
        out = _format_z_score(-2.5)
        assert "Alerte" in out
        assert "-2.50" in out

    def test_z_au_seuil_jaune(self) -> None:
        """z == -2 (à la limite) → Attention (vigilance, pas anomalie)."""
        out = _format_z_score(-2.0)
        assert "Attention" in out
        assert "-2.00" in out

    def test_z_negatif_jaune(self) -> None:
        """-2 < z < 0 → Attention (vigilance, pas anomalie)."""
        out = _format_z_score(-0.5)
        assert "Attention" in out
        assert "-0.50" in out

    def test_z_zero_vert(self) -> None:
        """z = 0 → OK +0.00 (baseline)."""
        out = _format_z_score(0.0)
        assert "OK" in out
        assert "+0.00" in out

    def test_z_positif_vert(self) -> None:
        """z > 0 → OK +X.XX (plus de vélos que d'habitude, pas une alarme)."""
        out = _format_z_score(1.5)
        assert "OK" in out
        assert "+1.50" in out


# -----------------------------------------------------------------------------
# _count_anomalies
# -----------------------------------------------------------------------------


class TestCountAnomalies:
    """Compte les stations Vélov en alarme (anomaly_detected = TRUE)."""

    def test_df_vide_retourne_zero(self) -> None:
        assert _count_anomalies(pd.DataFrame()) == 0

    def test_colonne_manquante_retourne_zero(self) -> None:
        df = pd.DataFrame({"station_id": [1, 2, 3]})
        assert _count_anomalies(df) == 0

    def test_compte_les_true(self) -> None:
        df = pd.DataFrame({"anomaly_detected": [True, False, True, True, False, False]})
        assert _count_anomalies(df) == 3

    def test_que_des_false(self) -> None:
        df = pd.DataFrame({"anomaly_detected": [False, False, False]})
        assert _count_anomalies(df) == 0

    def test_que_des_true(self) -> None:
        df = pd.DataFrame({"anomaly_detected": [True, True]})
        assert _count_anomalies(df) == 2

    def test_accepte_valeurs_truthy(self) -> None:
        """La somme booléenne accepte aussi 1/0 (cast automatique pandas)."""
        df = pd.DataFrame({"anomaly_detected": [1, 0, 1, 0, 1]})
        assert _count_anomalies(df) == 3


# -----------------------------------------------------------------------------
# _count_critical_lines
# -----------------------------------------------------------------------------


class TestCountCriticalLines:
    """Compte les lignes TC en alerte (critical + warning)."""

    def test_df_vide_retourne_zero_zero(self) -> None:
        n_critical, n_warning = _count_critical_lines(pd.DataFrame())
        assert n_critical == 0
        assert n_warning == 0

    def test_colonne_manquante_retourne_zero_zero(self) -> None:
        df = pd.DataFrame({"transit_line": ["T1", "M_A"]})
        n_critical, n_warning = _count_critical_lines(df)
        assert n_critical == 0
        assert n_warning == 0

    def test_compte_critical_et_warning(self) -> None:
        df = pd.DataFrame(
            {
                "alert_level": [
                    "critical",  # 1 critical
                    "critical",  # 2 critical
                    "warning",  # 1 warning
                    "ok",  # ignoré
                    "ok",  # ignoré
                ]
            }
        )
        n_critical, n_warning = _count_critical_lines(df)
        assert n_critical == 2
        assert n_warning == 1

    def test_que_des_ok(self) -> None:
        df = pd.DataFrame({"alert_level": ["ok", "ok", "ok"]})
        n_critical, n_warning = _count_critical_lines(df)
        assert n_critical == 0
        assert n_warning == 0

    def test_que_des_critical(self) -> None:
        df = pd.DataFrame({"alert_level": ["critical", "critical", "critical"]})
        n_critical, n_warning = _count_critical_lines(df)
        assert n_critical == 3
        assert n_warning == 0

    def test_mix_complet(self) -> None:
        """Mix réaliste : 1 critical, 2 warning, 3 ok, 1 unknown (ignoré)."""
        df = pd.DataFrame({"alert_level": ["critical", "warning", "warning", "ok", "ok", "ok", "unknown"]})
        n_critical, n_warning = _count_critical_lines(df)
        assert n_critical == 1
        assert n_warning == 2
