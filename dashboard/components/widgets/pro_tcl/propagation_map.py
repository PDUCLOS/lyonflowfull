"""Widget — Carte de propagation de congestion (Axe 2, Sprint 17, 2026-06-20).

Analyse comment la congestion se propage entre capteurs routiers adjacents
de Lyon (K=2 grid via ``gold.dim_gnn_adjacency``).

Architecture (cf. ``docs/SPEC_OPTIMISATION_INTERDEPENDANCES.md`` §3) :

1. **MV ``gold.mv_congestion_propagation_pairs``** (migration 024 v3) :
   stocke ~50k paires de nœuds adjacents (K=2 grid) avec lat/lon. PAS
   de CORR calculée en SQL (testé : 4 min timeout).
2. **Widget** : charge la MV + les séries temporelles ``speed_kmh`` sur
   6h glissantes depuis ``gold.traffic_features_live`` (JOIN via
   ``gold.mv_twgid_to_lyo`` pour le mapping ``properties_twgid`` ↔
   ``channel_id`` LYO).
3. **CORR en Python** : pour chaque paire, on calcule la corrélation
   croisée laggée sur la fenêtre 6h × 5min (~72 points) pour détecter
   la DIRECTION de propagation.

Convention de lag (utilisée dans tout le module, NE PAS INVERTER) :

    lag = +k  ⇔  A[t+k] = B[t] (avec forte corrélation)
             ⇔  la valeur actuelle de B prédit la valeur future de A
             ⇔  **B est l'indicateur leader de A** (B "lead" A de k steps)
             ⇔  En termes de propagation : la congestion apparaît
                 d'abord en B, puis en A (k × 5 min plus tard).
             ⇔  Sur la carte, la flèche pointe de B vers A.

    lag = -k  ⇔  A[t-k] = B[t]
             ⇔  A est l'indicateur leader de B (A "lead" B de k steps)
             ⇔  Flèche de A vers B.

    lag = 0   ⇔  synchrone (pas de direction claire).

4. **Visualisation Folium** : carte centrée Lyon avec ``AntPath``
   animées (les "fourmis"流动 le long de la ligne, direction visible
   par le sens du flux). Couleur par intensité, popup avec détail
   (CORR, lag, source/destination de la propagation).
5. **KPI banner** : nb paires analysées, paires corrélées (|CORR| > 0.5),
   paires avec direction claire (|lag| > 0).
6. **Tableau top N** : tri par |CORR| DESC, direction lisible
   (← ou →) + lag en minutes.

Si DB indispo → fail loud via ``DashboardDataError``. Si vue vide
(DAG refresh pas encore passé) → message d'attente explicite.

Performance :
* 50k paires totales, on filtre à celles où BOTH nœuds ont ≥ 30 obs
  (réduit à ~2000-5000 paires en pratique).
* CORR vectorisé via numpy sur des paires filtrées : < 5s pour 1000 paires.
* Widget button-gated (cf. ``deferred_render``) pour éviter de plomber
  l'auto-refresh 30s.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np
import pandas as pd
import streamlit as st

if TYPE_CHECKING:
    import folium

from dashboard.components.data_cache import (
    cached_congestion_propagation_pairs,
    cached_traffic_speeds_for_propagation,
)
from src.data.exceptions import DashboardDataError

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------

# Seuils de classification
CORR_THRESHOLDS: Final[dict[str, float]] = {
    "strong": 0.7,
    "medium": 0.5,
    "weak": 0.3,
}

# Couleurs par intensité de corrélation
CORR_COLORS: Final[dict[str, str]] = {
    "strong": "#F44336",  # rouge — propagation nette
    "medium": "#FF9800",  # orange — propagation modérée
    "weak": "#FFC107",  # ambre — corrélation faible
    "noise": "#9E9E9E",  # gris — pas de propagation claire
}

# Min observations par capteur pour qu'une paire soit analysable
MIN_OBS_PER_SENSOR: Final[int] = 30

# Max paires affichées sur la carte (perf + lisibilité Folium)
MAX_PAIRS_DISPLAYED: Final[int] = 200


def _corr_to_color(corr: float) -> str:
    """|CORR| → couleur hex.

    Sémantique : plus la couleur est chaude, plus la propagation est nette.
    """
    if pd.isna(corr):
        return CORR_COLORS["noise"]
    ac = abs(float(corr))
    if ac >= CORR_THRESHOLDS["strong"]:
        return CORR_COLORS["strong"]
    if ac >= CORR_THRESHOLDS["medium"]:
        return CORR_COLORS["medium"]
    if ac >= CORR_THRESHOLDS["weak"]:
        return CORR_COLORS["weak"]
    return CORR_COLORS["noise"]


def _corr_to_label(corr: float) -> str:
    """|CORR| → libellé FR."""
    if pd.isna(corr):
        return "—"
    ac = abs(float(corr))
    if ac >= CORR_THRESHOLDS["strong"]:
        return "Forte"
    if ac >= CORR_THRESHOLDS["medium"]:
        return "Moyenne"
    if ac >= CORR_THRESHOLDS["weak"]:
        return "Faible"
    return "Bruit"


# -----------------------------------------------------------------------------
# Calcul CORR (fonction pure, testable sans DB)
# -----------------------------------------------------------------------------


def compute_propagation_correlations(
    pairs_df: pd.DataFrame,
    speeds_df: pd.DataFrame,
    max_lag_steps: int = 3,
    min_obs: int = MIN_OBS_PER_SENSOR,
) -> pd.DataFrame:
    """Calcule la corrélation croisée laggée pour chaque paire de capteurs.

    Sprint 17 Axe 2 — voir docstring du module. Fonction **pure** (pas
    d'I/O) : prend deux DataFrames en entrée, retourne les CORR. Testable
    en unitaire avec des données synthétiques (cf. tests/widgets/pro_tcl/).

    Args:
        pairs_df: ``node_a, lat_a, lon_a, node_b, lat_b, lon_b`` (sortie
            de ``load_congestion_propagation_pairs()``).
        speeds_df: ``properties_twgid, channel_id, computed_at, speed_kmh``
            (sortie de ``load_traffic_speeds_for_propagation()``).
        max_lag_steps: nb max de pas de lag à scanner (5 min × lag).
            Défaut 3 = ±15 min. Assez pour détecter la propagation H+1
            typique d'un bouchon (formation lente).
        min_obs: nb min d'observations communes par paire pour la
            considérer analysable. Défaut 30 (~2.5h sur 6h glissantes).

    Returns:
        DataFrame avec colonnes :
            ``node_a, node_b, lat_a, lon_a, lat_b, lon_b, correlation,
            best_lag_steps, best_lag_minutes, n_points, intensity``.
        ``correlation`` = meilleur Pearson r sur les lags scannés (signe
        conservé). ``best_lag_steps`` = lag qui maximise |r| (positif
        si A lead B, négatif si B lead A). ``intensity`` ∈ {strong,
        medium, weak, noise} pour la couleur/legende.

    Notes perf :
        * Pivot large (T × P) puis numpy ops vectorisées.
        * Filtrage agressif : on garde seulement les paires où BOTH
          nœuds ont ≥ min_obs observations (sinon CORR non significatif).
        * Boucle Python sur les paires filtrées (typiquement 1-5k après
          filtre), pas sur les 50k initiales.

    Convention de signe du lag (cf. docstring du module) :
        * ``best_lag_steps > 0`` → B est l'indicateur leader de A
          (B "lead" A). Source de propagation = B.
        * ``best_lag_steps < 0`` → A est l'indicateur leader de B
          (A "lead" B). Source de propagation = A.
        * ``best_lag_steps == 0`` → synchrone, pas de direction claire.
    """
    if pairs_df.empty or speeds_df.empty:
        return pd.DataFrame(
            columns=[
                "node_a",
                "node_b",
                "lat_a",
                "lon_a",
                "lat_b",
                "lon_b",
                "correlation",
                "best_lag_steps",
                "best_lag_minutes",
                "n_points",
                "intensity",
            ]
        )

    # Pivot large : index=timestamp, columns=properties_twgid, values=speed_kmh
    wide = speeds_df.pivot_table(
        index="computed_at",
        columns="properties_twgid",
        values="speed_kmh",
        aggfunc="mean",
    ).sort_index()

    # On ne garde que les paires où BOTH nœuds ont assez d'obs
    obs_counts = wide.count()  # Series indexed by properties_twgid
    valid = obs_counts[obs_counts >= min_obs].index
    cand = pairs_df[
        pairs_df["node_a"].isin(valid) & pairs_df["node_b"].isin(valid)
    ].copy()

    if cand.empty:
        return pd.DataFrame(
            columns=[
                "node_a",
                "node_b",
                "lat_a",
                "lon_a",
                "lat_b",
                "lon_b",
                "correlation",
                "best_lag_steps",
                "best_lag_minutes",
                "n_points",
                "intensity",
            ]
        )

    results = []
    nodes_in_wide = set(wide.columns)
    for _, row in cand.iterrows():
        a, b = row["node_a"], row["node_b"]
        if a not in nodes_in_wide or b not in nodes_in_wide:
            continue
        s_a = wide[a]
        s_b = wide[b]
        # Drop NaN sur les deux simultanément
        mask = s_a.notna() & s_b.notna()
        n_pts = int(mask.sum())
        if n_pts < min_obs:
            continue
        a_vals = s_a[mask].to_numpy(dtype=float)
        b_vals = s_b[mask].to_numpy(dtype=float)

        # Centre les séries (moyenne nulle, pas de normalisation std ici)
        a_d = a_vals - a_vals.mean()
        b_d = b_vals - b_vals.mean()
        a_ss = float(np.dot(a_d, a_d))  # sum of squares
        b_ss = float(np.dot(b_d, b_d))
        if a_ss == 0 or b_ss == 0:
            continue  # série constante, r indéfini
        denom_full = np.sqrt(a_ss * b_ss)
        n = len(a_d)

        # Scan lags -L..+L
        # Convention (cf. docstring du module) :
        #   lag = +k  ⇔  on compare A[t+k] vs B[t]
        #               ⇔  B "lead" A (B prédit A, flèche de B vers A)
        #   lag = -k  ⇔  on compare A[t-k] vs B[t]
        #               ⇔  A "lead" B (A prédit B, flèche de A vers B)
        best_r, best_lag = 0.0, 0
        for lag in range(-max_lag_steps, max_lag_steps + 1):
            if lag < 0:
                # A "lead" B : A[t-k] ≈ B[t] ⇔ A[lag:n] vs B[0:n+lag]
                # On veut comparer a[0:n+lag] vs b[0:n+lag] (décalés
                # de k positions, A en avance). Codage : aa = a[0:n+lag]
                # (les k premières valeurs de A), bb = b[k:n] (les n-k
                # dernières valeurs de B). On translate en indices
                # positifs : aa = a_d[: n+lag], bb = b_d[-lag:n].
                aa = a_d[: n + lag]
                bb = b_d[-lag:n]
            elif lag > 0:
                # B "lead" A : A[t+k] ≈ B[t] ⇔ A[k:n] vs B[0:n-k]
                aa = a_d[lag:n]
                bb = b_d[: n - lag]
            else:
                aa = a_d
                bb = b_d
            # Pearson r normal : dot(aa, bb) / sqrt(ss_aa * ss_bb)
            # Note : ss_aa, ss_bb changent quand on slice, donc on
            # recalcule. Pour un lag petit vs n, c'est très proche de
            # l'approximation "ss_full" — mais on fait la version propre.
            num = float(np.dot(aa, bb))
            ss_a = float(np.dot(aa, aa))
            ss_b = float(np.dot(bb, bb))
            if ss_a == 0 or ss_b == 0:
                continue
            r = num / np.sqrt(ss_a * ss_b)
            # Bornage numérique (le slice peut donner |r| > 1 sur des
            # cas dégénérés, on clamp pour la propreté)
            r = float(np.clip(r, -1.0, 1.0))
            if abs(r) > abs(best_r):
                best_r, best_lag = r, lag

        results.append(
            {
                "node_a": a,
                "node_b": b,
                "lat_a": float(row["lat_a"]),
                "lon_a": float(row["lon_a"]),
                "lat_b": float(row["lat_b"]),
                "lon_b": float(row["lon_b"]),
                "correlation": best_r,
                "best_lag_steps": best_lag,
                "best_lag_minutes": best_lag * 5,
                "n_points": n_pts,
            }
        )

    if not results:
        return pd.DataFrame(
            columns=[
                "node_a",
                "node_b",
                "lat_a",
                "lon_a",
                "lat_b",
                "lon_b",
                "correlation",
                "best_lag_steps",
                "best_lag_minutes",
                "n_points",
                "intensity",
            ]
        )

    out = pd.DataFrame(results)
    out["intensity"] = out["correlation"].apply(
        lambda r: (
            "strong"
            if abs(r) >= CORR_THRESHOLDS["strong"]
            else "medium"
            if abs(r) >= CORR_THRESHOLDS["medium"]
            else "weak"
            if abs(r) >= CORR_THRESHOLDS["weak"]
            else "noise"
        )
    )
    return out.sort_values("correlation", key=lambda s: s.abs(), ascending=False).reset_index(
        drop=True
    )


# -----------------------------------------------------------------------------
# Visualisation Folium
# -----------------------------------------------------------------------------


def _popup_html(row: pd.Series) -> str:
    """HTML pour le popup Folium d'une paire (détail propagation).

    Convention (cf. docstring du module) :
        * lag > 0 : B "lead" A (B est la source, A la destination).
        * lag < 0 : A "lead" B (A est la source, B la destination).
    """
    corr = float(row.get("correlation", 0) or 0)
    lag = int(row.get("best_lag_steps", 0) or 0)
    lag_min = int(row.get("best_lag_minutes", 0) or 0)
    n_pts = int(row.get("n_points", 0) or 0)
    intensity = str(row.get("intensity", "noise"))
    color = CORR_COLORS.get(intensity, CORR_COLORS["noise"])

    if lag > 0:
        direction = f"B → A ({lag_min} min d'avance pour B)"
        arrow = "→"
    elif lag < 0:
        direction = f"A → B ({-lag_min} min d'avance pour A)"
        arrow = "←"
    else:
        direction = "↔ (synchrone, pas de direction claire)"
        arrow = "↔"

    label = _corr_to_label(corr)
    return (
        f"<div style='font-family:system-ui;min-width:240px;'>"
        f"<div style='font-weight:700;font-size:1.05rem;color:{color};'>"
        f"Propagation {label} (r = {corr:+.2f})</div>"
        f"<div style='margin:0.3rem 0;color:#333;'>{arrow} {direction}</div>"
        f"<hr style='margin:0.4rem 0;'>"
        f"<div style='font-size:0.85rem;'>"
        f"<b>Capteur A</b> : {row.get('node_a', '?')}<br/>"
        f"<b>Capteur B</b> : {row.get('node_b', '?')}<br/>"
        f"<b>Points analysés</b> : {n_pts}<br/>"
        f"<b>Distance (vol d'oiseau)</b> : "
        f"{_haversine_m(row.get('lat_a', 0), row.get('lon_a', 0), row.get('lat_b', 0), row.get('lon_b', 0)):.0f} m"
        f"</div></div>"
    )


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance haversine en mètres (pour info dans le popup)."""
    r_earth = 6_371_000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return float(2 * r_earth * np.arcsin(np.sqrt(a)))


def _build_folium_map(corr_df: pd.DataFrame) -> folium.Map:
    """Construit la carte Folium avec AntPath animées par paire.

    AntPath = "fourmis"流动 le long de la ligne, direction visible par
    le sens du flux. La flèche va de la SOURCE (capteur lead) vers la
    DESTINATION (capteur follow) :
        * lag > 0 : B "lead" A → flèche de B vers A
        * lag < 0 : A "lead" B → flèche de A vers B
        * lag == 0 : flèche arbitraire A → B (synchrone)

    Couleur par intensité, épaisseur par |CORR|.
    """
    import folium
    from folium.plugins import AntPath

    m = folium.Map(
        location=[45.760, 4.835],
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )

    for _, row in corr_df.iterrows():
        lat_a = float(row["lat_a"])
        lon_a = float(row["lon_a"])
        lat_b = float(row["lat_b"])
        lon_b = float(row["lon_b"])
        corr = float(row["correlation"])
        lag = int(row.get("best_lag_steps", 0) or 0)
        color = _corr_to_color(corr)
        # Épaisseur 2-6 px selon |CORR|
        weight = max(2.0, min(6.0, abs(corr) * 6))

        # Direction de la flèche : source → destination (cf. docstring).
        # lag > 0 = B "lead" A → B est source, A destination
        # lag < 0 = A "lead" B → A est source, B destination
        if lag > 0:
            locations = [(lat_b, lon_b), (lat_a, lon_a)]  # B → A
        else:
            locations = [(lat_a, lon_a), (lat_b, lon_b)]  # A → B (lag<0 ou 0)

        # AntPath : ants_count pour densité, delay pour vitesse
        AntPath(
            locations=locations,
            color=color,
            weight=weight,
            opacity=0.75,
            delay=800,
            dash_array=[10, 20],
            pulse_color="#FFFFFF",
            popup=folium.Popup(_popup_html(row), max_width=320),
        ).add_to(m)

    # Légende manuelle (colorée par intensité)
    legend_html = """
    <div style="
        position: fixed; bottom: 30px; left: 30px; z-index: 9999;
        background: white; padding: 10px 14px; border: 2px solid #444;
        border-radius: 6px; font-family: system-ui; font-size: 0.85rem;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
      <div style="font-weight:700;margin-bottom:6px;">Propagation (|r|)</div>
      <div><span style="display:inline-block;width:18px;height:3px;
        background:#F44336;margin-right:6px;"></span>Forte (≥ 0.7)</div>
      <div><span style="display:inline-block;width:18px;height:3px;
        background:#FF9800;margin-right:6px;"></span>Moyenne (≥ 0.5)</div>
      <div><span style="display:inline-block;width:18px;height:3px;
        background:#FFC107;margin-right:6px;"></span>Faible (≥ 0.3)</div>
      <div><span style="display:inline-block;width:18px;height:3px;
        background:#9E9E9E;margin-right:6px;"></span>Bruit (&lt; 0.3)</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def _render_kpi_banner(corr_df: pd.DataFrame) -> None:
    """Bandeau 4 KPI cards : Paires analysées / Corrélées / Directionnelle / Lag moyen."""
    if corr_df.empty:
        st.info("Aucune paire analysable (pas assez d'observations communes).")
        return
    n_total = len(corr_df)
    n_strong = int((corr_df["intensity"] == "strong").sum())
    n_medium = int((corr_df["intensity"] == "medium").sum())
    n_directional = int((corr_df["best_lag_steps"] != 0).sum())

    cards = [
        (
            "Paires analysées",
            n_total,
            "#1976D2",
            "capteurs adjacents K=2 grid",
        ),
        (
            "Forte propagation",
            n_strong,
            CORR_COLORS["strong"],
            f"|r| ≥ {CORR_THRESHOLDS['strong']:.1f}",
        ),
        (
            "Moyenne",
            n_medium,
            CORR_COLORS["medium"],
            f"|r| ≥ {CORR_THRESHOLDS['medium']:.1f}",
        ),
        (
            "Directionnelle",
            n_directional,
            "#7B1FA2",
            "lag ≠ 0 (lead A ou B)",
        ),
    ]
    cols = st.columns(4)
    for col, (label, n, color, sub) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div style="background:var(--bg-card);border-left:4px solid {color};
                            border-radius:6px;padding:0.8rem;margin:0.4rem 0;">
                    <div class="lyf-detail" style="opacity:0.8;">{label}</div>
                    <div style="font-size:1.8rem;font-weight:700;margin:0.2rem 0;">
                        {n} <span style="font-size:0.8rem;font-weight:400;">paires</span>
                    </div>
                    <div class="lyf-sublabel" style="opacity:0.6;">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_top_pairs(corr_df: pd.DataFrame, top_n: int = 20) -> None:
    """Tableau top N paires par |CORR| (direction + lag lisibles)."""
    if corr_df.empty:
        return
    plot_df = corr_df.head(top_n).copy()
    if plot_df.empty:
        st.info("Aucune paire à afficher.")
        return

    rows = []
    for _, r in plot_df.iterrows():
        lag = int(r.get("best_lag_steps", 0) or 0)
        lag_min = int(r.get("best_lag_minutes", 0) or 0)
        if lag > 0:
            direction = f"B→A +{lag_min}min (B lead)"
        elif lag < 0:
            direction = f"A→B +{abs(lag_min)}min (A lead)"
        else:
            direction = "↔ synchrone"
        rows.append(
            {
                "Paire": f"{r['node_a']} ↔ {r['node_b']}",
                "r": round(float(r["correlation"]), 2),
                "Intensité": _corr_to_label(r["correlation"]),
                "Direction propagation": direction,
                "Distance (m)": int(
                    _haversine_m(
                        r["lat_a"], r["lon_a"], r["lat_b"], r["lon_b"]
                    )
                ),
                "N obs": int(r["n_points"]),
            }
        )
    df_disp = pd.DataFrame(rows)

    def _color_intensity(val: str) -> str:
        return {
            "Forte": f"background-color: {CORR_COLORS['strong']}; color: white; font-weight: 600;",
            "Moyenne": f"background-color: {CORR_COLORS['medium']}; color: white; font-weight: 600;",
            "Faible": f"background-color: {CORR_COLORS['weak']}; color: black; font-weight: 600;",
            "Bruit": f"background-color: {CORR_COLORS['noise']}; color: white; font-weight: 600;",
        }.get(val, "")

    st.dataframe(
        df_disp.style.map(_color_intensity, subset=["Intensité"]),
        use_container_width=True,
        hide_index=True,
    )


# -----------------------------------------------------------------------------
# Widget entry point
# -----------------------------------------------------------------------------


def render_propagation_map(
    hours_window: int = 6,
    max_pairs: int = MAX_PAIRS_DISPLAYED,
    max_lag_steps: int = 3,
    height: int = 500,
) -> None:
    """Affiche la carte de propagation de congestion (Axe 2, Sprint 17).

    Sprint 17 (2026-06-20). Si DB indispo → fail loud via DashboardDataError.
    Si vue matérialisée pas encore alimentée → message d'attente explicite.

    Args:
        hours_window: nb d'heures glissantes pour la fenêtre de calcul
            CORR (défaut 6h, soit ~72 points à cadence 5 min).
        max_pairs: nb max de paires affichées sur la carte (perf Folium).
        max_lag_steps: nb de pas de lag scannés pour la corrélation
            croisée (défaut 3 = ±15 min).
        height: hauteur de l'iframe Folium en pixels.
    """
    try:
        pairs_df = cached_congestion_propagation_pairs()
        speeds_df = cached_traffic_speeds_for_propagation(hours=hours_window)
    except DashboardDataError as e:
        st.error(f"⚠️ {e}")
        return

    if pairs_df.empty or speeds_df.empty:
        st.info(
            "Données propagation pas encore disponibles. Le DAG "
            "`refresh_congestion_propagation` doit tourner (tâche "
            "`refresh_mv_congestion_propagation_pairs`, toutes les 30 min). "
            "Causes possibles : (1) DAG en attente de son 1er cycle, "
            "(2) `migration_024_congestion_propagation.sql` non appliquée, "
            "(3) `gold.mv_twgid_to_lyo` non peuplée (lancer "
            "`scripts/maintenance/build_mv_twgid_to_lyo.py`)."
        )
        return

    # Calcul CORR (pur Python, vectorisé, ~5s pour 5k paires)
    with st.spinner(
        f"Calcul des corrélations croisées sur {hours_window}h × "
        f"{len(pairs_df)} paires…"
    ):
        corr_df = compute_propagation_correlations(
            pairs_df=pairs_df,
            speeds_df=speeds_df,
            max_lag_steps=max_lag_steps,
        )

    if corr_df.empty:
        st.info(
            f"Aucune paire analysable (les deux nœuds doivent avoir ≥ "
            f"{MIN_OBS_PER_SENSOR} observations communes sur la fenêtre). "
            "Augmenter la fenêtre temporelle ou attendre que le pipeline "
            "Bronze→Silver se stabilise."
        )
        return

    # Bandeau KPI
    _render_kpi_banner(corr_df)

    st.markdown("---")

    # Carte Folium + tableau top paires
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(
            f"##### Carte de propagation — top {min(max_pairs, len(corr_df))} "
            f"paires par |r|"
        )
        # On garde les N meilleures pour la carte (perf)
        plot_df = corr_df.head(max_pairs)
        fmap = _build_folium_map(plot_df)
        import streamlit.components.v1 as components

        components.html(fmap.get_root().render(), height=height)
    with col2:
        st.markdown("##### Top 20 paires par |r|")
        _render_top_pairs(corr_df, top_n=20)

    st.caption(
        f"Données : `gold.mv_congestion_propagation_pairs` (migration 024 v3) "
        f"JOIN `gold.traffic_features_live` × `gold.mv_twgid_to_lyo` sur "
        f"fenêtre {hours_window}h glissantes. CORR = Pearson r scan laggé "
        f"(±{max_lag_steps} pas = ±{max_lag_steps * 5} min). Direction = "
        f"le capteur dont la série lead. Refresh DAG toutes les 30 min. "
        f"Seuil min obs : {MIN_OBS_PER_SENSOR} points par paire."
    )
